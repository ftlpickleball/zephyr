# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import unittest

import parse_board_metadata


class TestParseBoardMetadata(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_discover_revisions_from_yaml_format1(self):
        board_dir = os.path.join(self.tmp_dir.name, "board1")
        os.makedirs(board_dir)
        yaml_content = """
board:
  name: test_board
  revision:
    format: major.minor.patch
    revisions:
      - name: 1.0.0
        description: Initial release
      - name: 2.0.0
"""
        with open(os.path.join(board_dir, "board.yml"), "w", encoding="utf-8") as f:
            f.write(yaml_content)

        revs = parse_board_metadata.discover_revisions_for_board(board_dir)
        self.assertEqual(revs, ["1.0.0", "2.0.0"])

    def test_discover_revisions_from_revisions_folder(self):
        board_dir = os.path.join(self.tmp_dir.name, "board2")
        rev_dir = os.path.join(board_dir, "revisions")
        os.makedirs(rev_dir)
        with open(os.path.join(rev_dir, "1_0_0.conf"), "w") as f:
            f.write("")
        with open(os.path.join(rev_dir, "2_0_0_defconfig"), "w") as f:
            f.write("")

        revs = parse_board_metadata.discover_revisions_for_board(board_dir)
        self.assertEqual(sorted(revs), ["1_0_0", "2_0_0"])


if __name__ == "__main__":
    unittest.main()
