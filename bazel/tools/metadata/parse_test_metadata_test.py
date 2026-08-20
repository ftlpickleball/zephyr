# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import os
import tempfile
import shutil
import sys

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
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

if __name__ == '__main__':
    unittest.main()
