# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
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
        self.assertIn(sys.executable, args)
        self.assertIn(os.path.join(zephyr_base, "scripts", "dts", "gen_driver_kconfig_dts.py"), args)
        self.assertIn("--kconfig-out", args)
        self.assertIn(output_file, args)

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


if __name__ == '__main__':
    unittest.main()
