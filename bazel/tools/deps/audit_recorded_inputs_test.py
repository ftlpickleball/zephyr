# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for audit_recorded_inputs.py."""

import json
import os
import tempfile
import unittest

import audit_recorded_inputs as audit


def _inputs(*lines):
    return [audit.parse_input(line) for line in lines]


class ParseTest(unittest.TestCase):
    def test_parse_file_input(self):
        i = audit.parse_input("FILE:@@//a/b.txt 0123abcd\n")
        self.assertEqual(i, audit.Input("FILE", "@@//a/b.txt", "0123abcd"))
        self.assertEqual(i.location, "main")
        self.assertFalse(i.starts_batch)

    def test_locations(self):
        self.assertEqual(audit.parse_input("FILE:@@foo+//x ENOENT").location, "external")
        self.assertEqual(audit.parse_input("DIRENTS:/abs/dir 00").location, "absolute")
        self.assertEqual(audit.parse_input("ENV:HOME \\0").location, "")
        self.assertIsNone(audit.parse_input("ENV:HOME \\0").value)

    def test_unescape(self):
        i = audit.parse_input("FILE:@@//with\\sspace/a\\\\b DIR")
        self.assertEqual(i.path, "@@//with space/a\\b")

    def test_skips_non_input_lines(self):
        self.assertIsNone(audit.parse_input("c440c928254bc78da827fa3c209c67c7\n"))
        self.assertIsNone(audit.parse_input("\n"))


class BatchTest(unittest.TestCase):
    def test_external_inputs_start_batches(self):
        inputs = _inputs(
            "REPO_MAPPING:,foo +foo DIR",
            "FILE:@@//a x",
            "FILE:@@foo+//.git ENOENT",
            "FILE:@@//b y",
            "ENV:X \\0",
            "FILE:@@bar+//.git ENOENT",
        )
        batches = audit.split_into_batches(inputs)
        self.assertEqual([len(b) for b in batches], [2, 3, 1])

    def test_guarded_dirents_pass(self):
        entry = audit.Entry(
            "e",
            _inputs(
                "FILE:@@//d DIR",
                "FILE:@@bazel_tools//tools/BUILD abc",
                "DIRENTS:@@//d 123",
                "FILE:@@//d/f 456",
            ),
        )
        self.assertEqual(audit.check_entry(entry, max_batches=10), [])

    def test_dirents_in_same_batch_as_file_fails(self):
        entry = audit.Entry("e", _inputs("FILE:@@//d DIR", "DIRENTS:@@//d 123"))
        problems = audit.check_entry(entry, max_batches=10)
        self.assertEqual(len(problems), 1)
        self.assertIn("DIRENTS", problems[0])

    def test_dirents_without_file_fails(self):
        entry = audit.Entry(
            "e", _inputs("FILE:@@bazel_tools//tools/BUILD abc", "DIRENTS:@@//d 123")
        )
        self.assertEqual(len(audit.check_entry(entry, max_batches=10)), 1)

    def test_dirtree_and_batch_limit_fail(self):
        entry = audit.Entry(
            "e",
            _inputs(
                "FILE:@@a+//x 1",
                "FILE:@@b+//x 2",
                "DIRTREE:@@//tree 3",
            ),
        )
        problems = audit.check_entry(entry, max_batches=1)
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("DIRTREE" in p for p in problems))
        self.assertTrue(any("2 batches" in p for p in problems))

    def test_external_dirents_fails(self):
        entry = audit.Entry(
            "e",
            _inputs(
                "FILE:@@foo+//d DIR",
                "FILE:@@bazel_tools//tools/BUILD abc",
                "DIRENTS:@@foo+//d 123",
            ),
        )
        problems = audit.check_entry(entry, max_batches=10)
        self.assertEqual(len(problems), 1)
        self.assertIn("external DIRENTS", problems[0])


class CollectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ob = self._tmp.name
        os.makedirs(os.path.join(self.ob, "external"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel, content):
        with open(os.path.join(self.ob, rel), "w", encoding="utf-8") as f:
            f.write(content)

    def test_markers_and_hidden_lockfile(self):
        self._write(
            "external/@zephyr++ext+zc_x.marker",
            "deadbeef\nFILE:@@zephyr+//.git DIR\nFILE:@@//app/prj.conf 01\n",
        )
        self._write("external/@other+.marker", "deadbeef\nFILE:@@//x 01\n")
        self._write(
            "MODULE.bazel.lock",
            json.dumps(
                {
                    "moduleExtensions": {
                        "@@zephyr+//bazel:setup.bzl%zephyr_setup": {
                            "general": {
                                "recordedInputs": [
                                    "FILE:@@//d DIR",
                                    "DIRENTS:@@//d 00",
                                ]
                            }
                        },
                        "@@other+//:ext.bzl%ext": {"general": {"recordedInputs": []}},
                    }
                }
            ),
        )
        entries = audit.collect_entries(self.ob, [], ["zephyr"])
        self.assertEqual(len(entries), 2)
        marker, ext = entries
        self.assertEqual(marker.name, "@zephyr++ext+zc_x")
        self.assertEqual(len(marker.inputs), 2)
        self.assertEqual(audit.check_entry(marker, 10), [])
        self.assertIn("zephyr_setup", ext.name)
        self.assertEqual(len(audit.check_entry(ext, 10)), 1)

    def test_legacy_lockfile_format(self):
        lockfile = os.path.join(self.ob, "workspace.lock")
        with open(lockfile, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "moduleExtensions": {
                        "@@zephyr+//bazel:setup.bzl%zephyr_setup": {
                            "general": {
                                "recordedFileInputs": {"@@//a": "01"},
                                "recordedDirentsInputs": {"@@//d": "02"},
                                "envVariables": {"X": "y"},
                            }
                        }
                    }
                },
                f,
            )
        entries = audit.collect_entries(self.ob, [lockfile], [])
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].ordered)
        self.assertEqual(len(entries[0].inputs), 3)
        # Order is unknown in this format, so DIRENTS guards are not checked.
        self.assertEqual(audit.check_entry(entries[0], 10), [])

    def test_main_exit_status(self):
        self._write("external/@zephyr+.marker", "deadbeef\nDIRTREE:@@//t 00\n")
        self.assertEqual(audit.main([self.ob]), 1)
        self._write("external/@zephyr+.marker", "deadbeef\nFILE:@@//t 00\n")
        self.assertEqual(audit.main([self.ob]), 0)


if __name__ == "__main__":
    unittest.main()
