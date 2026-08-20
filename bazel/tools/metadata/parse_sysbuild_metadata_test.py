# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import os
import tempfile
import shutil
import sys
import json

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import parse_sysbuild_metadata

class TestParseSysbuildMetadata(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_parser(self, apps_dict):
        apps_json_path = os.path.join(self.test_dir, "apps.json")
        output_json_path = os.path.join(self.test_dir, "output.json")

        with open(apps_json_path, "w", encoding="utf-8") as f:
             json.dump(apps_dict, f)

        parse_sysbuild_metadata.main([
            "--apps-json", apps_json_path,
            "--output-json", output_json_path
        ])

        with open(output_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_parse_empty_app(self):
        apps = {"//apps/empty": self.test_dir}
        output = self.run_parser(apps)
        self.assertEqual(output["custom_repos"], [])

    def test_parse_global_helpers(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        with open(os.path.join(app_path, "sysbuild.yml"), 'w', encoding="utf-8") as f:
            f.write("""
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("//apps/my_app", output["raw_metadata"])
        self.assertIn("mcuboot", output["raw_metadata"]["//apps/my_app"]["helpers"])

    def test_parse_custom_repo_detection_from_conf(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        with open(os.path.join(app_path, "sysbuild.yml"), 'w', encoding="utf-8") as f:
            f.write("""
helpers:
  helper_app:
    target: "//hello_bazel"
""")

        # Create sysbuild.conf with helper setting to trigger custom repo
        with open(os.path.join(app_path, "sysbuild.conf"), 'w', encoding="utf-8") as f:
            f.write("helper_app_CONFIG_LOG=y\n")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertEqual(len(output["custom_repos"]), 1)
        self.assertEqual(output["custom_repos"][0]["helper_name"], "helper_app")
        self.assertIn("CONFIG_LOG=y", output["custom_repos"][0]["extra_kconfig"])

    def test_parse_namespaced_settings(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, 'w', encoding="utf-8") as f:
            f.write("""
mcuboot_CONFIG_BOOT_SIGNATURE_TYPE_RSA=y
net_app_CONFIG_SOME_OPTION=value
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("translated_confs", output)
        translated = output["translated_confs"]
        self.assertIn("//apps/my_app", translated)
        self.assertIn("mcuboot", translated["//apps/my_app"])
        self.assertIn("CONFIG_BOOT_SIGNATURE_TYPE_RSA=y", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("net_app", translated["//apps/my_app"])
        self.assertIn("CONFIG_SOME_OPTION=value", translated["//apps/my_app"]["net_app"])

    def test_translate_sb_config(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, 'w', encoding="utf-8") as f:
            f.write("""
SB_CONFIG_BOOTLOADER_MCUBOOT=y
SB_CONFIG_MCUBOOT_MODE_UPGRADE_ONLY=y
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("translated_confs", output)
        translated = output["translated_confs"]
        self.assertIn("//apps/my_app", translated)
        self.assertIn("mcuboot", translated["//apps/my_app"])
        self.assertIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_UPGRADE_ONLY=y", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("CONFIG_BOOTLOADER_MCUBOOT=y", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("main", translated["//apps/my_app"])
        self.assertIn("CONFIG_BOOTLOADER_MCUBOOT=y", translated["//apps/my_app"]["main"])

if __name__ == '__main__':
    unittest.main()
