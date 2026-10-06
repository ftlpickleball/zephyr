# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for hardware_deps.py."""

import os
import tempfile
import unittest

import hardware_deps


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x\n")


class HardwareDepsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def test_collect(self):
        _touch(self.p("zephyr", "scripts", "list_boards.py"))
        _touch(self.p("zephyr", "boards", "vnd", "b1", "board.yml"))
        _touch(self.p("zephyr", "boards", "vnd", "b1", "b1.dts"))
        os.makedirs(self.p("zephyr", "boards", "vnd", "empty"))
        _touch(self.p("zephyr", "soc", "fam", "soc.yml"))
        _touch(self.p("oot", "boards", "g", "b2", "board.yml"))
        # Symlinked directories are listed but not descended into, like Path.rglob().
        os.makedirs(self.p("elsewhere", "b3"))
        _touch(self.p("elsewhere", "b3", "board.yml"))
        os.symlink(self.p("elsewhere"), self.p("oot", "boards", "link"))

        deps, dirs = hardware_deps.collect(
            self.p("zephyr", "scripts"),
            board_roots=[self.p("zephyr"), self.p("oot")],
            soc_roots=[self.p("zephyr"), self.p("mod")],
            arch_roots=[self.p("zephyr")],
        )

        self.assertIn(self.p("zephyr", "scripts", "list_boards.py"), deps)
        self.assertIn(self.p("zephyr", "scripts", "schemas", "soc-schema.yaml"), deps)
        self.assertIn(self.p("zephyr", "boards", "vnd", "b1", "board.yml"), deps)
        self.assertIn(self.p("oot", "boards", "g", "b2", "board.yml"), deps)
        self.assertIn(self.p("zephyr", "soc", "fam", "soc.yml"), deps)
        self.assertIn(self.p("zephyr", "arch", "archs.yml"), deps)
        # A missing soc/ directory is a candidate: creating it changes the output.
        self.assertIn(self.p("mod", "soc"), deps)
        self.assertNotIn(self.p("zephyr", "boards", "vnd", "b1", "b1.dts"), deps)
        self.assertNotIn(self.p("elsewhere", "b3", "board.yml"), deps)

        self.assertIn(self.p("zephyr", "boards"), dirs)
        self.assertIn(self.p("zephyr", "boards", "vnd", "empty"), dirs)
        self.assertIn(self.p("oot", "boards", "g"), dirs)
        self.assertNotIn(self.p("elsewhere"), dirs)
        self.assertNotIn(self.p("oot", "boards", "link"), dirs)

    def test_main_writes_sorted_realpaths(self):
        _touch(self.p("real", "boards", "b", "board.yml"))
        os.symlink(self.p("real"), self.p("alias"))
        deps_out = self.p("deps.txt")
        dirs_out = self.p("dirs.txt")
        hardware_deps.main([
            "--scripts-dir", self.p("scripts"),
            "--board-root", self.p("alias"),
            "--deps-out", deps_out,
            "--dirs-out", dirs_out,
        ])
        with open(deps_out, encoding="utf-8") as f:
            deps = f.read()
        with open(dirs_out, encoding="utf-8") as f:
            dirs = f.read()
        self.assertTrue(deps.endswith("\n"))
        lines = deps.splitlines()
        self.assertEqual(lines, sorted(set(lines)))
        self.assertIn(self.p("real", "boards", "b", "board.yml"), lines)
        self.assertNotIn(self.p("alias", "boards", "b", "board.yml"), lines)
        self.assertIn(self.p("real", "boards", "b"), dirs.splitlines())


if __name__ == "__main__":
    unittest.main()
