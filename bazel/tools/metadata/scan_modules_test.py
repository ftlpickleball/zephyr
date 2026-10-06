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
import input_recorder
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


class TestScanModulesDeps(unittest.TestCase):
    """Tests for --deps-out / --dirs-out."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.out_dir = tempfile.mkdtemp()
        self.script = os.path.realpath(scan_modules.__file__)

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.out_dir)

    def real(self, *parts):
        return os.path.realpath(os.path.join(self.test_dir, *parts))

    def write(self, rel_path, content=""):
        path = os.path.join(self.test_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def run_scan(self, modules_dirs, deps_flags=True):
        """Returns (stdout, deps lines or None, dirs lines or None)."""
        from unittest.mock import patch
        import io

        deps_out = os.path.join(self.out_dir, "deps.txt")
        dirs_out = os.path.join(self.out_dir, "dirs.txt")
        argv = ["--modules-dirs-json", json.dumps(modules_dirs)]
        if deps_flags:
            argv += ["--deps-out", deps_out, "--dirs-out", dirs_out]
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            scan_modules.main(argv)

        def read_lines(path):
            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if content:
                self.assertTrue(content.endswith("\n"))
            lines = content.splitlines()
            self.assertEqual(lines, sorted(set(lines)))
            for line in lines:
                self.assertTrue(os.path.isabs(line), line)
            return lines

        return fake_out.getvalue(), read_lines(deps_out), read_lines(dirs_out)

    def test_deps_root_module(self):
        self.write("mod/zephyr/module.yml", "name: my_mod\n")
        self.write("mod/BUILD.bazel", 'zephyr_module(name = "my_mod")\n')
        mod = os.path.join(self.test_dir, "mod")

        out, deps, dirs = self.run_scan(
            {"@mod//": {"root": mod, "package_dir": mod}}
        )

        self.assertTrue(json.loads(out)[0]["has_zephyr_module_target_in_build"])
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.real("mod", "zephyr", "module.yml"),
                self.real("mod", "BUILD.bazel"),
            ]),
        )
        # A module root is not scanned for sub-modules.
        self.assertEqual(dirs, [])

    def test_deps_container(self):
        self.write("modules/mod1/zephyr/module.yml")  # no BUILD.bazel
        self.write("modules/mod2/zephyr/module.yml", "name: mod2\n")
        self.write("modules/mod2/BUILD.bazel", 'zephyr_module(name = "mod2")\n')
        os.makedirs(os.path.join(self.test_dir, "modules", "not_a_module"))
        os.makedirs(os.path.join(self.test_dir, "modules", ".hidden", "zephyr"))
        self.write("modules/README.md")
        os.symlink(
            "missing_target",
            os.path.join(self.test_dir, "modules", "dangling_link"),
        )
        container = os.path.join(self.test_dir, "modules")

        out, deps, dirs = self.run_scan(
            {"//modules": {"root": container, "package_dir": container}}
        )

        self.assertEqual(
            [m["name"] for m in json.loads(out)], ["mod1", "mod2"]
        )
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                # The container itself is not a module.
                self.real("modules", "zephyr", "module.yml"),
                self.real("modules", "mod1", "zephyr", "module.yml"),
                # Missing candidate: creating it would autolink mod1.
                self.real("modules", "mod1", "BUILD.bazel"),
                self.real("modules", "mod2", "zephyr", "module.yml"),
                self.real("modules", "mod2", "BUILD.bazel"),
                # Missing candidates: creating them would add modules.
                self.real("modules", "not_a_module", "zephyr", "module.yml"),
                self.real("modules", "missing_target", "zephyr", "module.yml"),
            ]),
        )
        self.assertEqual(dirs, [self.real("modules")])

    def test_deps_missing_root(self):
        missing = os.path.join(self.test_dir, "missing")

        out, deps, dirs = self.run_scan(
            {"@missing//": {"root": missing, "package_dir": missing}}
        )

        self.assertEqual(json.loads(out), [])
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.real("missing"),
            ]),
        )
        self.assertEqual(dirs, [])

    def test_deps_realpath_sorted_unique(self):
        self.write("real/b_mod/zephyr/module.yml")
        self.write("real/a_mod/zephyr/module.yml")
        real = os.path.join(self.test_dir, "real")
        link = os.path.join(self.test_dir, "link")
        os.symlink(real, link)

        _, deps, dirs = self.run_scan({
            "//link": {"root": link, "package_dir": link},
            "//real": {"root": real, "package_dir": real},
        })

        # Both labels resolve to the same files: listed once, by realpath.
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.real("real", "zephyr", "module.yml"),
                self.real("real", "a_mod", "zephyr", "module.yml"),
                self.real("real", "a_mod", "BUILD.bazel"),
                self.real("real", "b_mod", "zephyr", "module.yml"),
                self.real("real", "b_mod", "BUILD.bazel"),
            ]),
        )
        self.assertEqual(dirs, [self.real("real")])

    def test_output_unchanged_by_deps_flags(self):
        self.write("modules/mod1/zephyr/module.yml", "name: mod-1\n")
        self.write("modules/mod1/BUILD.bazel", 'zephyr_module(name = "mod_1")\n')
        self.write("root_mod/zephyr/module.yml")
        container = os.path.join(self.test_dir, "modules")
        root_mod = os.path.join(self.test_dir, "root_mod")
        modules_dirs = {
            "//modules": {"root": container, "package_dir": container},
            "@root_mod//": {"root": root_mod, "package_dir": root_mod},
        }

        out_without, deps, dirs = self.run_scan(modules_dirs, deps_flags=False)
        self.assertIsNone(deps)
        self.assertIsNone(dirs)
        out_with, deps, dirs = self.run_scan(modules_dirs)
        self.assertEqual(out_with, out_without)
        self.assertTrue(deps)
        self.assertTrue(dirs)

    def test_deps_out_only(self):
        from unittest.mock import patch
        import io

        deps_out = os.path.join(self.out_dir, "deps.txt")
        missing = os.path.join(self.test_dir, "missing")
        argv = [
            "--modules-dirs-json",
            json.dumps({"@m//": {"root": missing, "package_dir": missing}}),
            "--deps-out",
            deps_out,
        ]
        with patch("sys.stdout", new=io.StringIO()):
            scan_modules.main(argv)

        with open(deps_out, encoding="utf-8") as f:
            self.assertIn(self.real("missing") + "\n", f.read())
        self.assertEqual(os.listdir(self.out_dir), ["deps.txt"])


if __name__ == "__main__":
    unittest.main()
