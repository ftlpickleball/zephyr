# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import argparse
import importlib.util
import os
import pickle
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import input_recorder


class TestInputRecorder(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.realpath(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _touch(self, *parts):
        path = os.path.join(self.test_dir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).touch()
        return path

    def _chdir(self, path):
        cwd = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, cwd)

    def parse(self, argv):
        parser = argparse.ArgumentParser()
        input_recorder.add_arguments(parser)
        return parser.parse_args(argv)

    def test_add_arguments_defaults(self):
        args = self.parse([])
        self.assertIsNone(args.deps_out)
        self.assertIsNone(args.dirs_out)

    def test_init_with_sources_records_sources_and_self(self):
        recorder = input_recorder.InputRecorder("a.py", "b.py")
        self.assertEqual(
            recorder.files,
            {
                os.path.realpath("a.py"),
                os.path.realpath("b.py"),
                os.path.realpath(input_recorder.__file__),
            },
        )
        self.assertEqual(recorder.dirs, set())

    def test_init_without_sources_is_empty(self):
        recorder = input_recorder.InputRecorder()
        self.assertEqual(recorder.files, set())
        self.assertEqual(recorder.dirs, set())

    def test_write(self):
        d = self.test_dir
        os.makedirs(os.path.join(d, "real"))
        os.symlink(os.path.join(d, "real"), os.path.join(d, "link"))
        recorder = input_recorder.InputRecorder()
        recorder.add_file(os.path.join(d, "real", "b"))
        recorder.add_file(os.path.join(d, "link", "b"))
        recorder.add_file(os.path.join(d, "link", "a"))
        recorder.add_dir(os.path.join(d, "link"))
        deps_out = os.path.join(d, "deps.txt")
        dirs_out = os.path.join(d, "dirs.txt")

        recorder.write(deps_out, dirs_out)

        real = os.path.realpath(os.path.join(d, "real"))
        with open(deps_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "%s/a\n%s/b\n" % (real, real))
        with open(dirs_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), real + "\n")

    def test_write_only_requested(self):
        recorder = input_recorder.InputRecorder()
        recorder.add_dir(self.test_dir)
        deps_out = os.path.join(self.test_dir, "deps.txt")

        recorder.write(deps_out=deps_out)

        with open(deps_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "")
        self.assertEqual(os.listdir(self.test_dir), ["deps.txt"])

    def test_write_deps_out_with_exclude_dirs(self):
        scratch_dir = os.path.join(self.test_dir, "scratch")
        keep_file = self._touch("src", "keep.txt")
        drop_file = self._touch("scratch", "drop.txt")
        deps_out = os.path.join(self.test_dir, "deps.txt")

        recorder = input_recorder.InputRecorder()
        recorder.add(keep_file, drop_file)
        recorder.write(deps_out=deps_out, exclude_dirs=[scratch_dir])

        with open(deps_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), keep_file + "\n")

    def test_write_to_output_dir(self):
        out_dir = os.path.join(self.test_dir, "out")
        scratch_dir = os.path.join(self.test_dir, "scratch")
        os.makedirs(out_dir)
        existing = self._touch("src", "b.txt")
        os.symlink("src", os.path.join(self.test_dir, "src_link"))
        self._chdir(self.test_dir)

        recorder = input_recorder.InputRecorder()
        recorder.add(
            os.path.join(self.test_dir, "src_link", "b.txt"),  # Recorded by realpath.
            existing,  # Duplicate.
            os.path.join(self.test_dir, "src", "missing.txt"),  # Probed, missing.
            "a.txt",  # Relative to the current directory.
            os.path.join(self.test_dir, "out_sibling.txt"),  # Not in out/.
            os.path.join(out_dir, "generated.txt"),  # Output dir: dropped.
            os.path.join(scratch_dir, "tmp.txt"),  # Excluded dir: dropped.
            os.path.join(self.test_dir, "new\nline"),  # Unrepresentable: dropped.
            "",  # Ignored.
        )
        recorder.add_dir(
            os.path.join(self.test_dir, "src_link"),
            os.path.join(self.test_dir, "src"),
            out_dir,
        )
        recorder.write(output_dir=out_dir, exclude_dirs=[scratch_dir])

        expected_files = sorted([
            existing,
            os.path.join(self.test_dir, "src", "missing.txt"),
            os.path.join(self.test_dir, "a.txt"),
            os.path.join(self.test_dir, "out_sibling.txt"),
        ])
        with open(os.path.join(out_dir, input_recorder.DEPS_FILE), encoding="utf-8") as f:
            self.assertEqual(f.read(), "".join(p + "\n" for p in expected_files))
        with open(os.path.join(out_dir, input_recorder.DEP_DIRS_FILE), encoding="utf-8") as f:
            self.assertEqual(f.read(), os.path.join(self.test_dir, "src") + "\n")

    def test_write_empty_output_dir(self):
        input_recorder.InputRecorder().write(output_dir=self.test_dir)
        for name in (input_recorder.DEPS_FILE, input_recorder.DEP_DIRS_FILE):
            with open(os.path.join(self.test_dir, name), encoding="utf-8") as f:
                self.assertEqual(f.read(), "")

    def test_write_rejects_both_output_dir_and_deps_out(self):
        recorder = input_recorder.InputRecorder()
        with self.assertRaises(ValueError):
            recorder.write(deps_out="deps.txt", output_dir=self.test_dir)

    def test_snapshot_round_trip(self):
        worker = input_recorder.InputRecorder()
        worker.add(os.path.join(self.test_dir, "a"))
        worker.add_dir(self.test_dir)
        snapshot = pickle.loads(pickle.dumps(worker.snapshot()))

        recorder = input_recorder.InputRecorder()
        recorder.add(os.path.join(self.test_dir, "b"))
        recorder.update(snapshot)
        self.assertEqual(
            recorder.files,
            {os.path.join(self.test_dir, "a"), os.path.join(self.test_dir, "b")},
        )
        self.assertEqual(recorder.dirs, {self.test_dir})

    def test_add_kconfig_sources(self):
        kconfig_list = os.path.join(self.test_dir, "kconfig_list.txt")
        file1 = self._touch("a", "Kconfig")
        file2 = self._touch("b", "Kconfig")
        Path(kconfig_list).write_text(f"{file1}\n{file2}\n")

        recorder = input_recorder.InputRecorder()
        recorder.add_kconfig_sources(kconfig_list)
        self.assertEqual(recorder.files, {file1, file2})

    def test_add_tree(self):
        bindings = os.path.join(self.test_dir, "bindings")
        x = self._touch("bindings", "x.yaml")
        y = self._touch("bindings", "vendor", "y.yml")
        self._touch("bindings", "vendor", "README.txt")

        recorder = input_recorder.InputRecorder()
        with patch("input_recorder.os.walk", wraps=os.walk) as walk:
            recorder.add_tree(bindings, (".yaml", ".yml"))
            recorder.add_tree(bindings + os.sep, (".yaml", ".yml"))
        # Each tree is walked once per recorder.
        self.assertEqual(walk.call_count, 1)
        self.assertEqual(recorder.files, {x, y})
        self.assertEqual(recorder.dirs, {bindings, os.path.join(bindings, "vendor")})

    def test_add_python_modules(self):
        module_path = self._touch("pkg", "tracked_module.py")
        spec = importlib.util.spec_from_file_location(
            "_input_recorder_test_tracked_module", module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)

        recorder = input_recorder.InputRecorder()
        recorder.add_python_modules(os.path.join(self.test_dir, "pkg"), None)
        self.assertEqual(recorder.files, {module_path})

        # A module file symlinked into a root counts, recorded by realpath.
        os.makedirs(os.path.join(self.test_dir, "runfiles"))
        os.symlink(module_path, os.path.join(self.test_dir, "runfiles", "linked_module.py"))
        module.__file__ = os.path.join(self.test_dir, "runfiles", "linked_module.py")
        recorder = input_recorder.InputRecorder()
        recorder.add_python_modules(os.path.join(self.test_dir, "runfiles"))
        self.assertEqual(recorder.files, {module_path})

    def test_realpath_matches_os_path_realpath(self):
        d = self.test_dir
        os.makedirs(os.path.join(d, "real", "sub"))
        open(os.path.join(d, "real", "file"), "w").close()
        os.symlink(os.path.join(d, "real"), os.path.join(d, "link"))
        os.symlink("link", os.path.join(d, "chain"))
        os.symlink(os.path.join("real", "sub"), os.path.join(d, "rel_link"))
        os.symlink("..", os.path.join(d, "real", "sub", "up"))
        os.symlink("missing", os.path.join(d, "dangling"))
        os.symlink("loop2", os.path.join(d, "loop1"))
        os.symlink("loop1", os.path.join(d, "loop2"))
        recorder = input_recorder.InputRecorder()
        paths = [os.path.join(d, rel) for rel in [
            "link/sub/x.yml", "chain/sub/up/file", "rel_link/missing/deeper",
            "dangling/zephyr/module.yml", "real/file/zephyr/module.yml",
            "link/../real/sub", "link/./sub/", "loop1/x", "",
        ]] + ["/", ".", "relative/path"]
        for path in paths + paths:  # twice: memoized results must agree too
            self.assertEqual(recorder.realpath(path), os.path.realpath(path), path)


if __name__ == "__main__":
    unittest.main()
