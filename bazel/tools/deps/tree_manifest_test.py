# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for tree_manifest.py."""

import json
import os
import tempfile
import unittest

import tree_manifest


def _touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        for rel in (
            "drivers/foo/Kconfig",
            "drivers/foo/foo.c",
            "drivers/foo/BUILD.bazel",
            "dts/bindings/vnd/vnd,foo.yaml",
            "boards/vnd/b1/board.yml",
            "boards/vnd/b1/b1.dts",
            "tests/t1/testcase.yaml",
            "tests/t1/prj.conf",
        ):
            _touch(os.path.join(self.root, rel))
        self.subdirs = ["boards", "drivers", "dts", "tests"]

    def tearDown(self):
        self._tmp.cleanup()

    def _manifests(self):
        return tree_manifest.manifests(self.root, self.subdirs)

    def test_editing_files_keeps_digests(self):
        m0 = self._manifests()
        _touch(os.path.join(self.root, "drivers/foo/foo.c"), "int x;\n")
        _touch(os.path.join(self.root, "drivers/foo/Kconfig"), "config FOO\n\tbool\n")
        self.assertEqual(self._manifests(), m0)

    def test_adding_source_file_keeps_digests(self):
        m0 = self._manifests()
        _touch(os.path.join(self.root, "drivers/foo/bar.c"))
        _touch(os.path.join(self.root, "drivers/foo/__pycache__/Kconfig"))
        _touch(os.path.join(self.root, "drivers/foo/.hidden/Kconfig"))
        _touch(os.path.join(self.root, "tests/t1/out/zephyr/.config.conf"))
        self.assertEqual(self._manifests(), m0)

    def test_adding_kconfig_changes_both(self):
        m0 = self._manifests()
        _touch(os.path.join(self.root, "drivers/foo/new/Kconfig"))
        m1 = self._manifests()
        self.assertNotEqual(m1["done"], m0["done"])
        self.assertNotEqual(m1["kconfig_done"], m0["kconfig_done"])
        os.remove(os.path.join(self.root, "drivers/foo/new/Kconfig"))
        self.assertEqual(self._manifests(), m0)

    def test_adding_binding_and_build_file_changes_kconfig_done(self):
        for rel in ("dts/bindings/vnd/vnd,bar.yaml", "drivers/bar/BUILD.bazel"):
            m0 = self._manifests()
            _touch(os.path.join(self.root, rel))
            self.assertNotEqual(self._manifests()["kconfig_done"], m0["kconfig_done"], rel)

    def test_adding_board_root_zephyr_dts_binding_changes_both(self):
        # Board roots may keep bindings in zephyr/dts/bindings instead of dts/bindings.
        self.subdirs.append("zephyr/dts")
        m0 = self._manifests()
        _touch(os.path.join(self.root, "zephyr/dts/bindings/vnd/vnd,baz.yaml"))
        m1 = self._manifests()
        self.assertNotEqual(m1["done"], m0["done"])
        self.assertNotEqual(m1["kconfig_done"], m0["kconfig_done"])

    def test_adding_app_changes_only_done(self):
        m0 = self._manifests()
        _touch(os.path.join(self.root, "tests/t2/testcase.yaml"))
        _touch(os.path.join(self.root, "tests/t2/prj.conf"))
        _touch(os.path.join(self.root, "boards/vnd/b1/b1_v2.overlay"))
        m1 = self._manifests()
        self.assertNotEqual(m1["done"], m0["done"])
        self.assertEqual(m1["kconfig_done"], m0["kconfig_done"])

    def test_missing_subdir_is_ignored(self):
        self.assertEqual(
            tree_manifest.manifests(self.root, self.subdirs + ["missing"]),
            self._manifests(),
        )

    def test_main_writes_outputs(self):
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        args = ["hash", "--root", self.root, "--out-dir", out]
        for sub in self.subdirs:
            args += ["--subdir", sub]
        self.assertEqual(tree_manifest.main(args), 0)
        m = self._manifests()
        for name in ("done", "kconfig_done"):
            with open(os.path.join(out, name), encoding="utf-8") as f:
                self.assertEqual(f.read(), m[name] + "\n")

    def test_unreadable_directory_fails(self):
        if os.geteuid() == 0:
            self.skipTest("root can list any directory")
        locked = os.path.join(self.root, "drivers", "locked")
        os.makedirs(locked)
        os.chmod(locked, 0)
        try:
            with self.assertRaises(OSError):
                self._manifests()
        finally:
            os.chmod(locked, 0o755)


class SetupDirsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = self._tmp.name
        for d in ("apps/a1", "boards/vnd/b1", "modules/m1/zephyr", "bazel-out/x"):
            os.makedirs(os.path.join(self.ws, d))
        _touch(os.path.join(self.ws, "BUILD.bazel"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_module(self, content, rel="MODULE.bazel"):
        _touch(os.path.join(self.ws, rel), content)

    def test_finds_env_dirs(self):
        self._write_module(
            """
module(name = "downstream")
bazel_dep(name = "zephyr")
zephyr_setup = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zephyr_setup.env(
    apps_dirs = ["//apps", "@zephyr//samples"],
    boards_dirs = ["//:BUILD.bazel"],
    modules = ["@downstream//modules/m1"],
)
"""
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["module_files"], ["MODULE.bazel"])
        self.assertEqual(info["warnings"], [])
        self.assertEqual(
            info["dirs"],
            [
                "apps",
                "boards",
                "dts",
                "modules/m1",
                "snippets",
                "soc",
                # Probed before dts/ for bindings and DTS includes.
                "zephyr/dts",
            ],
        )

    def test_follows_includes_variables_and_aliases(self):
        self._write_module(
            """
module(name = "downstream")
include("//:zephyr.MODULE.bazel")
"""
        )
        self._write_module(
            """
APPS = ["//apps/a1"]
zs = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zs.env(apps_dirs = APPS + ["//apps/missing"])
other = use_extension("@foo//:ext.bzl", "zephyr_setup")
other.env(apps_dirs = ["//boards"])
""",
            rel="zephyr.MODULE.bazel",
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["module_files"], ["MODULE.bazel", "zephyr.MODULE.bazel"])
        # Missing directories are reported too, so that creating them is noticed.
        self.assertEqual(info["dirs"], ["apps/a1", "apps/missing"])

    def test_root_apps_dir_lists_children_without_bazel_symlinks(self):
        self._write_module(
            """
zephyr_setup = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zephyr_setup.env(apps_dirs = ["//:BUILD.bazel"])
"""
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["dirs"], ["apps", "boards", "modules"])

    def test_module_yml_names_its_parent_directory(self):
        _touch(os.path.join(self.ws, "zephyr", "module.yml"))
        _touch(os.path.join(self.ws, "modules", "m1", "zephyr", "module.yml"))
        self._write_module(
            """
zephyr_setup = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zephyr_setup.env(modules = ["//modules/m1/zephyr:module.yml"])
"""
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["dirs"], ["modules/m1"])

    def test_root_module_yml_lists_workspace_children(self):
        # As in setup.bzl, `//zephyr:module.yml` names the workspace root as
        # the module, not just its zephyr/ directory.
        _touch(os.path.join(self.ws, "zephyr", "module.yml"))
        self._write_module(
            """
zephyr_setup = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zephyr_setup.env(modules = ["//zephyr:module.yml"])
"""
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["dirs"], ["apps", "boards", "modules", "zephyr"])

    def test_non_literal_labels_warn(self):
        self._write_module(
            """
zephyr_setup = use_extension("@zephyr//bazel:setup.bzl", "zephyr_setup")
zephyr_setup.env(apps_dirs = UNKNOWN)
"""
        )
        info = tree_manifest.zephyr_setup_dirs(self.ws)
        self.assertEqual(info["dirs"], [])
        self.assertEqual(len(info["warnings"]), 1)
        self.assertIn("apps_dirs", info["warnings"][0])

    def test_main_prints_json(self):
        self._write_module("")
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(
                tree_manifest.main(["setup-dirs", "--workspace-root", self.ws]), 0
            )
        self.assertEqual(
            json.loads(buf.getvalue()),
            {"dirs": [], "module_files": ["MODULE.bazel"], "warnings": []},
        )


if __name__ == "__main__":
    unittest.main()
