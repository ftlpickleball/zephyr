# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for find_pin_files.py."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import find_pin_files


class ModuleNameTest(unittest.TestCase):
    def test_keyword_name_single_and_multiline(self):
        self.assertEqual(
            find_pin_files.module_name('module(name = "zephyr", version = "3.5.99")\n'),
            "zephyr",
        )
        self.assertEqual(
            find_pin_files.module_name(
                'module(\n    version = "1.0.0",\n    name = "my_module",\n)\n'
            ),
            "my_module",
        )

    def test_positional_name(self):
        self.assertEqual(
            find_pin_files.module_name('module("positional_mod")\n'),
            "positional_mod",
        )

    def test_ignores_comments_and_docstrings(self):
        content = '''"""
module(name = "docstring_mod")
"""
# module(name = "comment_mod")
module(
    name = "real_mod",
)
'''
        self.assertEqual(find_pin_files.module_name(content), "real_mod")

    def test_missing_or_invalid_returns_none(self):
        self.assertIsNone(find_pin_files.module_name('bazel_dep(name = "foo")\n'))
        self.assertIsNone(find_pin_files.module_name("module(name = DYNAMIC_VAR)\n"))
        self.assertIsNone(find_pin_files.module_name("def broken(:\n"))


class StringLiteralsTest(unittest.TestCase):
    def test_extracts_literals_and_ignores_comments_and_docstrings(self):
        content = '''"""Module docstring with "//patches/openair:0001-fix.patch"."""

load("//bazel:helpers.bzl", "some_symbol", aliased = "other_symbol")

# Comment with "//patches:comment.patch"
def my_func(ctx):
    """Function docstring with "//patches:func_doc.patch"."""
    if not ctx:
        fail("Failed on //patches:fail_msg.patch")
    print("Debug //patches:print_msg.patch")
    return [
        "//patches:real.patch",
        "@zephyr//modules/acpica:external.BUILD",
    ]
'''
        self.assertEqual(
            find_pin_files.string_literals(content),
            [
                "//bazel:helpers.bzl",
                "//patches:real.patch",
                "@zephyr//modules/acpica:external.BUILD",
            ],
        )

    def test_ignores_fstrings_and_handles_syntax_errors(self):
        self.assertEqual(
            find_pin_files.string_literals('x = f"//patches:{name}.patch"\ny = "//a:b.txt"\n'),
            ["//a:b.txt"],
        )
        self.assertEqual(find_pin_files.string_literals("def invalid(:\n"), [])


class LabelLiteralToRelpathTest(unittest.TestCase):
    def test_main_and_override_relative_labels(self):
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "//patches/openair:0001-fix.patch", ""
            ),
            find_pin_files.PinLabel(
                relpath="patches/openair/0001-fix.patch",
                explicit_name=True,
                repo_relpath="",
            ),
        )
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "//patches:sub.patch", "repository_overrides/sub"
            ),
            find_pin_files.PinLabel(
                relpath="repository_overrides/sub/patches/sub.patch",
                explicit_name=True,
                repo_relpath="repository_overrides/sub",
            ),
        )
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "@//patches:root.patch", "repository_overrides/sub"
            ),
            find_pin_files.PinLabel(
                relpath="patches/root.patch",
                explicit_name=True,
                repo_relpath="",
            ),
        )
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "@@//:lock.json", "repository_overrides/sub"
            ),
            find_pin_files.PinLabel(
                relpath="lock.json",
                explicit_name=True,
                repo_relpath="",
            ),
        )

    def test_named_repo_labels(self):
        by_name = {
            "zephyr": "",
            "submod": "repository_overrides/submod",
        }
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "@zephyr//modules/acpica:external.BUILD", "", by_name
            ),
            find_pin_files.PinLabel(
                relpath="modules/acpica/external.BUILD",
                explicit_name=True,
                repo_relpath="",
            ),
        )
        self.assertEqual(
            find_pin_files.label_literal_to_relpath(
                "@submod//bazel:pins.bzl", "", by_name
            ),
            find_pin_files.PinLabel(
                relpath="repository_overrides/submod/bazel/pins.bzl",
                explicit_name=True,
                repo_relpath="repository_overrides/submod",
            ),
        )
        self.assertIsNone(
            find_pin_files.label_literal_to_relpath(
                "@unknown_repo//bazel:pins.bzl", "", by_name
            )
        )

    def test_implicit_target_and_invalid_labels(self):
        self.assertEqual(
            find_pin_files.label_literal_to_relpath("//apps/blinky", ""),
            find_pin_files.PinLabel(
                relpath="apps/blinky/blinky",
                explicit_name=False,
                repo_relpath="",
            ),
        )
        for invalid in (
            "not_a_label.txt",
            "@@external//pkg:file.txt",
            "//pkg:with space.txt",
            "//pkg:with\nnewline.txt",
            "//pkg:fmt%s.txt",
            "//pkg:{var}.txt",
            "//pkg:$var.txt",
            "//pkg:*.txt",
            "//pkg:../escape.txt",
            "//pkg//double:slash.txt",
            "//pkg:",
            "//pkg:/leading.txt",
            "//pkg:trailing/",
        ):
            self.assertIsNone(
                find_pin_files.label_literal_to_relpath(invalid, ""),
                msg=f"Expected None for {invalid!r}",
            )


class FindPinFilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, relpath: str, content: str) -> str:
        full_path = os.path.join(self.ws, relpath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        Path(full_path).write_text(content, encoding="utf-8")
        return full_path

    def test_discovers_transitive_pins_and_skips_docstrings_and_dirs(self):
        self._write(
            "MODULE.bazel",
            '''module(name = "zephyr", version = "3.5.99")

include("//bazel:extra.MODULE.bazel")

new_git_repository(
    name = "acpica",
    build_file = "@zephyr//modules/acpica:external.BUILD",
    patches = ["//patches:missing_future.patch"],
)

ext = use_extension("//bazel:setup.bzl", "ext")
ext.env(
    apps_dirs = ["//samples"],
    non_file_target = ["//tools:my_binary"],
)
''',
        )
        self._write(
            "bazel/extra.MODULE.bazel",
            '''pip = use_extension("@rules_python//python/extensions:pip.bzl", "pip")
pip.parse(requirements_lock = "//bazel/pip:requirements-lock.txt")
''',
        )
        self._write("bazel/pip/requirements-lock.txt", "pyyaml==6.0\n")
        self._write("modules/acpica/external.BUILD", "# overlay\n")
        os.makedirs(os.path.join(self.ws, "samples"), exist_ok=True)

        # Create a cycle between setup.bzl and deps.bzl and include a docstring
        # with a fake label in deps.bzl.
        self._write(
            "bazel/setup.bzl",
            '''load("//bazel/private:deps.bzl", "helper")

def impl(ctx):
    return ctx.path(Label("//:VERSION"))
''',
        )
        self._write(
            "bazel/private/deps.bzl",
            '''"""Docstring with fake label "//patches/openair:0001-fix.patch"."""

load("//bazel:setup.bzl", "impl")

def helper():
    fail("Error referencing //patches:fail_only.patch")
''',
        )
        self._write("VERSION", "3.5.99\n")

        # Set up an in-workspace override repository.
        self._write(
            "repository_overrides/submod/MODULE.bazel",
            '''module(
    name = "submod",
    version = "0.1.0",
)
include("//bazel:sub.MODULE.bazel")
''',
        )
        self._write(
            "repository_overrides/submod/bazel/sub.MODULE.bazel",
            '''archive_override(
    module_name = "dep",
    patches = [
        "//patches:sub_local.patch",
        "@submod//patches:sub_named.patch",
        "@//patches:root_from_sub.patch",
    ],
)
sub_ext = use_extension("//bazel:sub_ext.bzl", "sub_ext")
''',
        )
        self._write("repository_overrides/submod/patches/sub_local.patch", "")
        self._write("repository_overrides/submod/patches/sub_named.patch", "")
        self._write(
            "repository_overrides/submod/bazel/sub_ext.bzl",
            'load("//bazel:unfollowed_in_override.bzl", "x")\n',
        )
        self._write(
            "repository_overrides/submod/bazel/unfollowed_in_override.bzl",
            "# Should not be crawled because sub_ext.bzl is not in main repo.\n",
        )
        self._write("patches/root_from_sub.patch", "")

        pins = find_pin_files.find_pin_files(
            workspace_root=self.ws,
            repo_relpaths=[
                "",
                "repository_overrides/submod",
                "repository_overrides/missing_mod",
            ],
            extra_relpaths=["custom/extra.pin"],
        )

        self.assertEqual(
            pins,
            [
                "MODULE.bazel",
                "VERSION",
                "bazel/extra.MODULE.bazel",
                "bazel/pip/requirements-lock.txt",
                "bazel/private/deps.bzl",
                "bazel/setup.bzl",
                "custom/extra.pin",
                "modules/acpica/external.BUILD",
                "patches/missing_future.patch",
                "patches/root_from_sub.patch",
                "repository_overrides/missing_mod/MODULE.bazel",
                "repository_overrides/submod/MODULE.bazel",
                "repository_overrides/submod/bazel/sub.MODULE.bazel",
                "repository_overrides/submod/bazel/sub_ext.bzl",
                "repository_overrides/submod/patches/sub_local.patch",
                "repository_overrides/submod/patches/sub_named.patch",
            ],
        )

    def test_parses_each_module_bazel_once(self):
        self._write(
            "MODULE.bazel",
            'module(name = "zephyr")\ninclude("//bazel:extra.MODULE.bazel")\n',
        )
        self._write("bazel/extra.MODULE.bazel", "# empty\n")

        with patch(
            "find_pin_files.ast.parse", wraps=find_pin_files.ast.parse
        ) as mock_parse:
            pins = find_pin_files.find_pin_files(
                workspace_root=self.ws,
                repo_relpaths=[""],
            )

        self.assertEqual(pins, ["MODULE.bazel", "bazel/extra.MODULE.bazel"])
        # 1 parse for MODULE.bazel + 1 parse for bazel/extra.MODULE.bazel = 2
        self.assertEqual(mock_parse.call_count, 2)

    def test_main_outputs_json(self):
        self._write("MODULE.bazel", 'module(name = "test_ws")\n')
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            rc = find_pin_files.main(
                [
                    "--workspace-root",
                    self.ws,
                    "--repo-relpaths-json",
                    json.dumps([""]),
                    "--extra-relpaths-json",
                    json.dumps(["extra.lock"]),
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stdout.getvalue()), ["MODULE.bazel", "extra.lock"])


if __name__ == "__main__":
    unittest.main()
