# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import glob
import importlib.util
import os
import tempfile
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import kconfig_utils

class TestKconfigUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sanitize_name_for_target(self):
        self.assertEqual(kconfig_utils.sanitize_name_for_target("ABC-DEF.GHI"), "ABC_DEF_GHI")
        self.assertEqual(kconfig_utils.sanitize_name_for_target("abc(def)ghi"), "abc_def_ghi")
        self.assertEqual(kconfig_utils.sanitize_name_for_target("abc$def"), "abc_def")
        self.assertEqual(kconfig_utils.sanitize_name_for_target("abc\"def'ghi"), "abcdefghi")

    def test_generate_aggregation_file(self):
        output_file = os.path.join(self.test_dir, "Kconfig.agg")
        dirs = [os.path.join(self.test_dir, "dir1"), os.path.join(self.test_dir, "dir2")]
        os.makedirs(dirs[0])
        os.makedirs(dirs[1])

        # Create candidate files
        with open(os.path.join(dirs[0], "Kconfig.agg"), 'w') as f:
            f.write("# dir1")
        with open(os.path.join(dirs[1], "Kconfig.agg"), 'w') as f:
            f.write("# dir2")

        kconfig_utils.generate_aggregation_file(output_file, dirs, "test comment")

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('# Load test comment descriptions.', content)
            self.assertIn('osource "', content)
            self.assertIn('dir1/Kconfig.agg"', content)
            self.assertIn('dir2/Kconfig.agg"', content)

    def test_generate_aggregation_file_wildcard(self):
        output_file = os.path.join(self.test_dir, "Kconfig.agg")
        dirs = [os.path.join(self.test_dir, "dir1")]
        os.makedirs(dirs[0])
        # Create a dummy file that matches the wildcard
        Path(os.path.join(dirs[0], "Kconfig.agg.dummy")).touch()

        kconfig_utils.generate_aggregation_file(output_file, dirs, "test comment", include_wildcard=True)

        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('osource "', content)
            self.assertIn('dir1/Kconfig.agg.dummy"', content)

    def test_generate_aggregation_file_wildcard_exclusion(self):
        output_file = os.path.join(self.test_dir, "Kconfig")
        dirs = [os.path.join(self.test_dir, "dir1")]
        os.makedirs(dirs[0])

        # Create base file
        Path(os.path.join(dirs[0], "Kconfig")).touch()
        # Create files that should be included by wildcard
        Path(os.path.join(dirs[0], "Kconfig.other")).touch()
        # Create files that should be EXCLUDED
        Path(os.path.join(dirs[0], "Kconfig.defconfig")).touch()
        Path(os.path.join(dirs[0], "Kconfig.sysbuild")).touch()
        Path(os.path.join(dirs[0], "Kconfig.shield")).touch()

        kconfig_utils.generate_aggregation_file(output_file, dirs, "test comment", include_wildcard=True)

        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('dir1/Kconfig.other', content)
            self.assertNotIn('dir1/Kconfig.defconfig', content)
            self.assertNotIn('dir1/Kconfig.sysbuild', content)
            self.assertNotIn('dir1/Kconfig.shield', content)

    def test_generate_kconfig_modules(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        os.makedirs(os.path.join(zephyr_base, "modules", "module1", "zephyr"))
        os.makedirs(os.path.join(zephyr_base, "modules", "module2"))

        with open(os.path.join(zephyr_base, "modules", "module1", "zephyr", "Kconfig"), 'w') as f:
            f.write("module1 kconfig")
        with open(os.path.join(zephyr_base, "modules", "module2", "Kconfig"), 'w') as f:
            f.write("module2 kconfig")

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, [], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('module1/zephyr/Kconfig', content)
            self.assertIn('module2/Kconfig', content)

    def test_generate_kconfig_modules_with_extra_modules(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        os.makedirs(os.path.join(zephyr_base, "modules"), exist_ok=True)

        extra_dir1 = os.path.join(self.test_dir, "extra1")
        os.makedirs(extra_dir1)
        with open(os.path.join(extra_dir1, "Kconfig"), 'w') as f:
            f.write("extra1 kconfig")

        extra_dir2 = os.path.join(self.test_dir, "extra2")
        os.makedirs(os.path.join(extra_dir2, "zephyr"))
        with open(os.path.join(extra_dir2, "zephyr", "Kconfig"), 'w') as f:
            f.write("extra2 kconfig")

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, [extra_dir1, extra_dir2], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('extra1/Kconfig', content)
            self.assertIn('extra2/zephyr/Kconfig', content)

    def test_generate_kconfig_modules_with_bzlmod_name(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        os.makedirs(os.path.join(zephyr_base, "modules"), exist_ok=True)

        # Bzlmod canonical name format for injected repos
        extra_dir = os.path.join(self.test_dir, "+_repo_rules+hal_nordic")
        os.makedirs(extra_dir)
        with open(os.path.join(extra_dir, "Kconfig"), 'w') as f:
            f.write("hal_nordic kconfig")

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, [extra_dir], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('+_repo_rules+hal_nordic/Kconfig', content)
            # Verify config name is parsed correctly: '+_repo_rules+hal_nordic' -> 'HAL_NORDIC'
            self.assertIn('config ZEPHYR_HAL_NORDIC_MODULE', content)

    def test_generate_kconfig_modules_precedence(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        os.makedirs(os.path.join(zephyr_base, "modules"), exist_ok=True)

        module_dir = os.path.join(self.test_dir, "module_prec")
        os.makedirs(os.path.join(module_dir, "zephyr"))

        with open(os.path.join(module_dir, "Kconfig"), 'w') as f:
            f.write("Kconfig")
        with open(os.path.join(module_dir, "zephyr", "Kconfig"), 'w') as f:
            f.write("zephyr/Kconfig")

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, [module_dir], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn('module_prec/zephyr/Kconfig', content)
            self.assertNotIn('module_prec/Kconfig', content)

    def test_generate_kconfig_modules_empty_or_missing(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, ["/nonexistent/path"], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertEqual(content, "")

    def test_generate_kconfig_modules_dir_exists_no_kconfig(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        os.makedirs(os.path.join(zephyr_base, "modules"), exist_ok=True)

        # Create an existing directory but with NO Kconfig file
        extra_dir = os.path.join(self.test_dir, "existing_no_kconfig")
        os.makedirs(extra_dir)

        output_file = os.path.join(self.test_dir, "Kconfig.modules")

        kconfig_utils.generate_kconfig_modules(zephyr_base, [extra_dir], output_file)

        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r') as f:
            content = f.read()
            # Should NOT contain osource for this dir
            self.assertNotIn('existing_no_kconfig/Kconfig', content)
            self.assertNotIn('existing_no_kconfig/zephyr/Kconfig', content)
            # SHOULD contain the config block
            self.assertIn('config ZEPHYR_EXISTING_NO_KCONFIG_MODULE', content)
            self.assertIn('bool', content)
            self.assertIn('default y', content)

    @patch('subprocess.run')
    def test_generate_kconfig_dts(self, mock_run):
        """"Verifies that generate_kconfig_dts calls Zephyr's script with correct arguments."""
        zephyr_base = "/path/to/zephyr"
        output_file = "/path/to/output"
        dts_roots = ["/path/to/root1"]

        with patch('kconfig_utils.Path.exists') as mock_exists:
            mock_exists.return_value = True
            # Also need to mock resolve() if we want to avoid real path resolution issues
            with patch('kconfig_utils.Path.resolve') as mock_resolve:
                mock_resolve.return_value = Path("/path/to/root1/zephyr/dts/bindings")
                kconfig_utils.generate_kconfig_dts(zephyr_base, output_file, dts_roots)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        env = mock_run.call_args[1]["env"]
        self.assertEqual(args[:3], [sys.executable, "-B", "-s"])
        self.assertIn(os.path.join(zephyr_base, "scripts", "dts", "gen_driver_kconfig_dts.py"), args)
        self.assertIn("--kconfig-out", args)
        self.assertIn(output_file, args)
        self.assertFalse(env["PYTHONPATH"].endswith(":"))

    def test_sanitize_host_env(self):
        env = {
            "PATH": "/usr/bin",
            "KCONFIG_WARN_UNDEF": "y",
            "ZEPHYR_FOO_MODULE_DIR": "/stale/foo",
            "CONFIG_BAR": "y",
            "PYTHONSTARTUP": "/home/user/.pystartup",
            "PYTHONUSERBASE": "/home/user/.local",
        }
        kconfig_utils.sanitize_host_env(env)
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("KCONFIG_WARN_UNDEF", env)
        self.assertNotIn("ZEPHYR_FOO_MODULE_DIR", env)
        self.assertNotIn("CONFIG_BAR", env)
        self.assertNotIn("PYTHONSTARTUP", env)
        self.assertNotIn("PYTHONUSERBASE", env)
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["PYTHONHASHSEED"], "0")
        self.assertEqual(env["PYTHONUTF8"], "1")

    def test_filtered_walk(self):
        sub1 = os.path.join(self.test_dir, "sub1")
        bazel_out = os.path.join(self.test_dir, "bazel-out")
        git_dir = os.path.join(self.test_dir, ".git")

        os.makedirs(sub1)
        os.makedirs(bazel_out)
        os.makedirs(git_dir)

        Path(os.path.join(sub1, "file1.txt")).touch()
        Path(os.path.join(bazel_out, "file2.txt")).touch()
        Path(os.path.join(git_dir, "file3.txt")).touch()

        visited_roots = []
        for root, dirs, files in kconfig_utils.filtered_walk(self.test_dir):
            visited_roots.append(os.path.relpath(root, self.test_dir))

        self.assertIn(".", visited_roots)
        self.assertIn("sub1", visited_roots)
        self.assertIn("bazel-out", visited_roots)
        self.assertNotIn(".git", visited_roots)


def _load_kconfiglib():
    """Loads Zephyr's scripts/kconfig/kconfiglib.py without registering it in
    sys.modules (other tests mock 'kconfiglib'), or returns None if it is not
    available, e.g. outside of a Zephyr source tree."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts", "kconfig", "kconfiglib.py"
    )
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("_kconfiglib_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestInputTracking(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.test_dir)

    def _touch(self, *parts):
        path = os.path.join(self.test_dir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).touch()
        return path

    def _chdir(self, path):
        cwd = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, cwd)

    def test_glob_dependencies(self):
        base = os.path.join(self.test_dir, "base")
        self._touch("base", "a", "Kconfig")
        self._touch("base", "a", "Kconfig.x")
        self._touch("base", "a", "Kconfig.y")
        os.makedirs(os.path.join(base, "b"))
        self._touch("base", "c")  # A file, so no c/Kconfig candidate.
        self._touch("base", ".hidden", "Kconfig")  # Skipped, like glob does.

        # The listed dirs, and every path whose creation or removal changes the result.
        pattern = os.path.join(base, "*", "Kconfig")
        dirs, paths = kconfig_utils.glob_dependencies(pattern)
        self.assertEqual(dirs, {base})
        self.assertEqual(paths, {os.path.join(base, "a", "Kconfig"), os.path.join(base, "b", "Kconfig")})
        self.assertLessEqual(set(glob.glob(pattern)), paths)

        self.assertEqual(
            kconfig_utils.glob_dependencies(os.path.join(base, "a", "Kconfig.*")),
            ({os.path.join(base, "a")}, {os.path.join(base, "a", "Kconfig.x"), os.path.join(base, "a", "Kconfig.y")}),
        )

        # An 'osource' of a single file depends on that path only.
        literal = os.path.join(base, "missing", "Kconfig")
        self.assertEqual(kconfig_utils.glob_dependencies(literal), (set(), {literal}))

        # Creating a missing directory could add matches.
        missing = os.path.join(self.test_dir, "missing")
        self.assertEqual(kconfig_utils.glob_dependencies(os.path.join(missing, "*", "Kconfig")), (set(), {missing}))

        # Relative patterns are relative to the current directory, like glob's.
        self._chdir(self.test_dir)
        self.assertEqual(
            kconfig_utils.glob_dependencies(os.path.join("base", "*", "Kconfig")),
            ({base}, {os.path.join(base, "a", "Kconfig"), os.path.join(base, "b", "Kconfig")}),
        )

    def test_record_kconfig_sources(self):
        kconfiglib = _load_kconfiglib()
        if kconfiglib is None:
            self.skipTest("scripts/kconfig/kconfiglib.py is not available")
        root = os.path.join(self.test_dir, "root")
        os.makedirs(os.path.join(root, "opt", "x"))
        os.makedirs(os.path.join(root, "opt", "empty"))
        self._touch("root", "sub", "Kconfig")
        Path(root, "opt", "x", "Kconfig").write_text('config X\n\tbool "X"\n')
        Path(root, "Kconfig").write_text(
            'mainmenu "Test"\n'
            'rsource "sub/Kconfig"\n'
            'orsource "opt/*/Kconfig"\n'
            'orsource "missing/Kconfig"\n'
            'osource "$(UNSET_VAR)/Kconfig.unset"\n'
            'osource "$(UNSET_VAR)/zephyr/Kconfig"\n'
            f'osource "{self.test_dir}/elsewhere/Kconfig"\n'
        )

        tracker = kconfig_utils.InputRecorder()
        original_iglob = kconfiglib.iglob
        with patch.dict(os.environ):
            os.environ.pop("srctree", None)
            os.environ.pop("UNSET_VAR", None)
            with kconfig_utils.record_kconfig_sources(kconfiglib, tracker):
                kconf = kconfiglib.Kconfig(os.path.join(root, "Kconfig"), warn_to_stderr=False)

        self.assertIs(kconfiglib.iglob, original_iglob)
        self.assertIn("X", kconf.syms)
        self.assertEqual(tracker.files, {
            os.path.join(root, "sub", "Kconfig"),
            os.path.join(root, "opt", "x", "Kconfig"),
            os.path.join(root, "opt", "empty", "Kconfig"),
            os.path.join(root, "missing", "Kconfig"),
            os.path.join(self.test_dir, "elsewhere", "Kconfig"),
        })
        self.assertEqual(tracker.dirs, {os.path.join(root, "opt")})

    def test_dts_python_sources(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        package = ("zephyr", "scripts", "dts", "python-devicetree", "src", "devicetree")
        edtlib = self._touch(*package, "edtlib.py")
        dtlib = self._touch(*package, "dtlib.py")
        self._touch(*package, "grammar.lark")
        self.assertEqual(
            kconfig_utils.dts_python_sources(zephyr_base),
            [os.path.join(zephyr_base, "scripts", "dts", "edtlib_logger.py"), dtlib, edtlib],
        )

    def test_generate_aggregation_file_records_inputs(self):
        dir1 = os.path.join(self.test_dir, "dir1")
        dir2 = os.path.join(self.test_dir, "dir2")
        missing_dir = os.path.join(self.test_dir, "missing")
        self._touch("dir1", "Kconfig")
        self._touch("dir1", "Kconfig.extra")
        os.makedirs(dir2)
        dirs = [dir1, dir2, missing_dir]

        untracked = os.path.join(self.test_dir, "out1", "Kconfig")
        tracked = os.path.join(self.test_dir, "out2", "Kconfig")
        kconfig_utils.generate_aggregation_file(untracked, dirs, "Test", include_wildcard=True)
        tracker = kconfig_utils.InputRecorder()
        kconfig_utils.generate_aggregation_file(tracked, dirs, "Test", include_wildcard=True, tracker=tracker)

        self.assertEqual(Path(tracked).read_text(), Path(untracked).read_text())
        self.assertEqual(tracker.files, {os.path.join(d, "Kconfig") for d in dirs})
        # Their listings decide which Kconfig.* files are sourced.
        self.assertEqual(tracker.dirs, {dir1, dir2})

    def test_generate_kconfig_modules_records_inputs(self):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        modules_dir = os.path.join(zephyr_base, "modules")
        self._touch("zephyr", "modules", "m1", "zephyr", "Kconfig")
        self._touch("zephyr", "modules", "m2", "Kconfig")
        extra = os.path.dirname(self._touch("extra", "Kconfig.zephyr"))
        missing = os.path.join(self.test_dir, "missing_module")

        untracked = os.path.join(self.test_dir, "Kconfig.modules.untracked")
        tracked = os.path.join(self.test_dir, "Kconfig.modules")
        kconfig_utils.generate_kconfig_modules(zephyr_base, [extra, missing], untracked)
        tracker = kconfig_utils.InputRecorder()
        kconfig_utils.generate_kconfig_modules(zephyr_base, [extra, missing], tracked, tracker=tracker)

        self.assertEqual(Path(tracked).read_text(), Path(untracked).read_text())
        # Candidates are recorded up to the first existing one.
        self.assertEqual(tracker.files, {
            os.path.join(modules_dir, "m1", "zephyr", "Kconfig"),
            os.path.join(modules_dir, "m2", "zephyr", "Kconfig"),
            os.path.join(modules_dir, "m2", "Kconfig"),
            os.path.join(extra, "zephyr", "module.yml"),
            os.path.join(extra, "zephyr", "Kconfig"),
            os.path.join(extra, "Kconfig"),
            os.path.join(extra, "Kconfig.zephyr"),
            missing,
        })
        self.assertEqual(tracker.dirs, {modules_dir})

        # Without zephyr/modules/, creating it would add modules.
        tracker = kconfig_utils.InputRecorder()
        no_modules = os.path.join(self.test_dir, "no_modules")
        kconfig_utils.generate_kconfig_modules(no_modules, [], tracked, tracker=tracker)
        self.assertEqual(tracker.files, {os.path.join(no_modules, "modules")})

    @patch("subprocess.run")
    def test_generate_kconfig_dts_records_inputs(self, mock_run):
        zephyr_base = os.path.join(self.test_dir, "zephyr")
        root1 = os.path.join(self.test_dir, "root1")
        root2 = os.path.join(self.test_dir, "root2")
        bindings = os.path.join(root1, "dts", "bindings")
        x = self._touch("root1", "dts", "bindings", "x.yaml")
        y = self._touch("root1", "dts", "bindings", "vendor", "y.yml")
        self._touch("root1", "dts", "bindings", "vendor", "README.txt")
        os.makedirs(root2)

        tracker = kconfig_utils.InputRecorder()
        kconfig_utils.generate_kconfig_dts(
            zephyr_base, os.path.join(self.test_dir, "Kconfig.dts"), [root1, root2], tracker=tracker
        )

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--bindings-dirs") + 1:], [bindings])
        self.assertEqual(tracker.files, {
            os.path.join(zephyr_base, "scripts", "dts", "gen_driver_kconfig_dts.py"),
            x,
            y,
            # Creating these would add or switch a bindings dir.
            os.path.join(root1, "zephyr", "dts", "bindings"),
            os.path.join(root2, "zephyr", "dts", "bindings"),
            os.path.join(root2, "dts", "bindings"),
        })
        self.assertEqual(tracker.dirs, {bindings, os.path.join(bindings, "vendor")})

    def test_filtered_walk_records_visited_dirs(self):
        os.makedirs(os.path.join(self.test_dir, "sub_b"))
        os.makedirs(os.path.join(self.test_dir, "sub", "deeper"))
        os.makedirs(os.path.join(self.test_dir, ".git", "objects"))
        self._touch("sub", "z.txt")
        self._touch("sub", "a.txt")

        tracker = kconfig_utils.InputRecorder()
        walked = list(kconfig_utils.filtered_walk(self.test_dir, tracker=tracker))
        self.assertEqual(walked[0][1], ["sub", "sub_b"])
        self.assertEqual(walked[1][2], ["a.txt", "z.txt"])
        self.assertEqual(tracker.dirs, {
            self.test_dir,
            os.path.join(self.test_dir, "sub"),
            os.path.join(self.test_dir, "sub", "deeper"),
            os.path.join(self.test_dir, "sub_b"),
        })
        self.assertEqual(tracker.files, set())


if __name__ == '__main__':
    unittest.main()
