# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import json
import os
import tempfile
import shutil
import sys

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import input_recorder
import parse_test_metadata

class TestParseTestMetadata(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_lightweight_yaml_parse_platform_allow(self):
        file_path = os.path.join(self.test_dir, "testcase.yaml")

        # Test simple list
        with open(file_path, 'w') as f:
            f.write("""
platform_allow:
  - board1
  - board2
""")
        platforms = parse_test_metadata.lightweight_yaml_parse_platform_allow(file_path)
        self.assertEqual(platforms, ["board1", "board2"])

    def test_lightweight_yaml_parse_platform_allow_empty(self):
        file_path = os.path.join(self.test_dir, "testcase.yaml")

        # Test no platform_allow
        with open(file_path, 'w') as f:
            f.write("""
other_field: value
""")
        platforms = parse_test_metadata.lightweight_yaml_parse_platform_allow(file_path)
        self.assertEqual(platforms, None)

    def test_lightweight_yaml_parse_platform_allow_complex(self):
        file_path = os.path.join(self.test_dir, "testcase.yaml")

        # Test complex YAML structure similar to with_mcumgr
        with open(file_path, 'w') as f:
            f.write("""
common:
  sysbuild: true
  platform_allow:
    - board1
    - board2
tests:
  test1:
    platform_allow:
      - board3
""")
        platforms = parse_test_metadata.lightweight_yaml_parse_platform_allow(file_path)
        # It should pick the first platform_allow (in common)
        self.assertEqual(platforms, ["board1", "board2", "board3"])


class TestParseTestMetadataDeps(unittest.TestCase):
    """Tests for --deps-out / --dirs-out."""

    def setUp(self):
        self.test_dir = os.path.realpath(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def write(self, rel_path, content=""):
        path = os.path.join(self.test_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def run_main(self, apps, *extra):
        apps_json = os.path.join(self.test_dir, "apps.json")
        output_json = os.path.join(self.test_dir, "out.json")
        with open(apps_json, "w", encoding="utf-8") as f:
            json.dump(apps, f)
        parse_test_metadata.main([
            "--apps-json", apps_json,
            "--zephyr-root", self.test_dir,
            "--output-json", output_json,
        ] + list(extra))
        with open(output_json, "rb") as f:
            return f.read()

    def test_deps_out(self):
        self.write("both/testcase.yaml", "platform_allow:\n  - b1\n")
        self.write("both/sample.yaml", "platform_allow:\n  - b2\n")
        self.write("real_sample/sample.yaml", "platform_allow:\n  - b3\n")
        os.makedirs(os.path.join(self.test_dir, "none"))
        os.symlink(
            os.path.join(self.test_dir, "real_sample"),
            os.path.join(self.test_dir, "sample"),
        )
        apps = {
            "//none": os.path.join(self.test_dir, "none"),
            "//sample": os.path.join(self.test_dir, "sample"),
            "//both": os.path.join(self.test_dir, "both"),
        }
        deps_out = os.path.join(self.test_dir, "deps.txt")
        dirs_out = os.path.join(self.test_dir, "dirs.txt")

        out_without = self.run_main(apps)
        self.assertFalse(os.path.exists(deps_out))
        out_with = self.run_main(
            apps, "--deps-out", deps_out, "--dirs-out", dirs_out
        )

        self.assertEqual(out_with, out_without)
        self.assertEqual(
            json.loads(out_with),
            {"//none": None, "//sample": ["b3"], "//both": ["b1"]},
        )
        expected = sorted([
            os.path.realpath(parse_test_metadata.__file__),
            os.path.realpath(input_recorder.__file__),
            # testcase.yaml wins, so sample.yaml is never consulted.
            os.path.join(self.test_dir, "both", "testcase.yaml"),
            # Missing: creating it would shadow sample.yaml.
            os.path.join(self.test_dir, "real_sample", "testcase.yaml"),
            os.path.join(self.test_dir, "real_sample", "sample.yaml"),
            # Missing: creating either would add metadata.
            os.path.join(self.test_dir, "none", "testcase.yaml"),
            os.path.join(self.test_dir, "none", "sample.yaml"),
        ])
        with open(deps_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "".join(p + "\n" for p in expected))
        with open(dirs_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "")


if __name__ == '__main__':
    unittest.main()
