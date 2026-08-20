# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for scan_modules.py."""

import json
import os
import shutil
import sys
import tempfile
import unittest

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import scan_modules


class TestScanModules(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_module(self, path, name=None):
        os.makedirs(os.path.join(path, "zephyr"), exist_ok=True)
        module_yml = os.path.join(path, "zephyr", "module.yml")
        content = {}
        if name:
            content["name"] = name
        with open(module_yml, "w", encoding="utf-8") as f:
            import yaml
            yaml.dump(content, f)

    def test_scan_root_module(self):
        mod_path = os.path.join(self.test_dir, "my-module")
        os.makedirs(mod_path)
        self.create_module(mod_path, "my-module-custom")

        modules_dirs_json = json.dumps({
            "@my_module//": {
                "root": mod_path,
                "package_dir": mod_path,
            }
        })

        # Mock sys.argv
        sys.argv = ["scan_modules.py", "--modules-dirs-json", modules_dirs_json]

        # We need to capture stdout
        from unittest.mock import patch
        import io
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            scan_modules.main()
            result = json.loads(fake_out.getvalue())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["modules_dir_label"], "@my_module//")
        self.assertEqual(result[0]["relpath"], "")
        self.assertEqual(result[0]["name"], "my_module_custom")
        self.assertEqual(result[0]["abs_path"], mod_path)

    def test_scan_depth_1_modules(self):
        container_path = os.path.join(self.test_dir, "modules")
        os.makedirs(container_path)

        mod1_path = os.path.join(container_path, "mod1")
        os.makedirs(mod1_path)
        self.create_module(mod1_path) # no custom name, defaults to dir name

        mod2_path = os.path.join(container_path, "mod2-dir")
        os.makedirs(mod2_path)
        self.create_module(mod2_path, "mod2-custom")

        # Non-module dir
        os.makedirs(os.path.join(container_path, "not-a-module"))

        modules_dirs_json = json.dumps({
            "//modules": {
                "root": container_path,
                "package_dir": container_path,
            }
        })

        sys.argv = ["scan_modules.py", "--modules-dirs-json", modules_dirs_json]

        from unittest.mock import patch
        import io
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            scan_modules.main()
            result = json.loads(fake_out.getvalue())

        # Sort results by name to ensure deterministic assert
        result.sort(key=lambda x: x["name"])

        self.assertEqual(len(result), 2)

        self.assertEqual(result[0]["modules_dir_label"], "//modules")
        self.assertEqual(result[0]["relpath"], "mod1")
        self.assertEqual(result[0]["name"], "mod1")
        self.assertEqual(result[0]["abs_path"], mod1_path)

        self.assertEqual(result[1]["modules_dir_label"], "//modules")
        self.assertEqual(result[1]["relpath"], "mod2-dir")
        self.assertEqual(result[1]["name"], "mod2_custom") # sanitized
        self.assertEqual(result[1]["abs_path"], mod2_path)

    def test_extract_apparent_name(self):
        # Existing tests
        self.assertEqual(
            scan_modules.extract_apparent_name("rules_python~1.8.3"),
            "rules_python",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name(
                "zephyr-bazel++zephyr_setup+zephyr_kconfig"
            ),
            "zephyr_kconfig",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("+_repo_rules+hal_atmel"),
            "hal_atmel",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("local_mod"), "local_mod"
        )

        # Robustness tests
        self.assertEqual(
            scan_modules.extract_apparent_name("rules_python~1.8.3~pip"),
            "rules_python",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("rules_python+1.8.3"),
            "rules_python",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("pigweed+"),
            "pigweed",
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("+foo+bar"), "bar"
        )
        self.assertEqual(
            scan_modules.extract_apparent_name("local+mod+with+plus"),
            "local+mod+with+plus",
        )

        # Exception tests
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("~invalid")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("zephyr-bazel++zephyr_setup")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("zephyr-bazel++zephyr_setup+")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("+_repo_rules")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("+_repo_rules+")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("+foo")
        with self.assertRaises(ValueError):
            scan_modules.extract_apparent_name("+foo+")

    def test_scan_canonical_name_dir(self):
        mod_path = os.path.join(self.test_dir, "+_repo_rules+hal-atmel")
        os.makedirs(mod_path)
        self.create_module(mod_path)

        modules_dirs_json = json.dumps({
            "@hal_atmel//": {
                "root": mod_path,
                "package_dir": mod_path,
            }
        })

        sys.argv = ["scan_modules.py", "--modules-dirs-json", modules_dirs_json]

        from unittest.mock import patch
        import io
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            scan_modules.main()
            result = json.loads(fake_out.getvalue())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "hal_atmel")


    def test_malformed_yaml(self):
        mod_path = os.path.join(self.test_dir, "bad-yaml-mod")
        os.makedirs(os.path.join(mod_path, "zephyr"))

        # Write invalid YAML (e.g., with a tab character)
        module_yml = os.path.join(mod_path, "zephyr", "module.yml")
        with open(module_yml, "w", encoding="utf-8") as f:
            f.write("\tname: bad-yaml\n")

        modules_dirs_json = json.dumps({
            "@bad_yaml_mod//": {
                "root": mod_path,
                "package_dir": mod_path,
            }
        })

        sys.argv = ["scan_modules.py", "--modules-dirs-json", modules_dirs_json]

        from unittest.mock import patch
        import io
        with patch("sys.stdout", new=io.StringIO()) as fake_out, \
             patch("sys.stderr", new=io.StringIO()) as fake_err:
            scan_modules.main()
            result = json.loads(fake_out.getvalue())
            stderr_output = fake_err.getvalue()

        # Should fall back to directory name (sanitized)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "bad_yaml_mod")
        self.assertIn("Warning: failed to parse", stderr_output)

    def test_malformed_json_input(self):
        sys.argv = ["scan_modules.py", "--modules-dirs-json", "{invalid json"]

        from unittest.mock import patch
        import io
        with patch("sys.stderr", new=io.StringIO()) as fake_err:
            with self.assertRaises(SystemExit) as cm:
                scan_modules.main()

            self.assertEqual(cm.exception.code, 1)
            stderr_output = fake_err.getvalue()
            self.assertIn("Error parsing modules-dirs-json", stderr_output)


if __name__ == "__main__":
    unittest.main()
