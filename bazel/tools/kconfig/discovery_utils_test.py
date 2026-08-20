# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import os
import tempfile
import shutil
import sys

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import discovery_utils

class TestDiscoveryUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.app_path = os.path.join(self.test_dir, "app")
        os.makedirs(self.app_path)
        self.boards_dir = os.path.join(self.app_path, "boards")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_check_filesystem_overrides_no_boards_dir(self):
        self.assertFalse(discovery_utils.check_filesystem_overrides(self.app_path, "board1"))

    def test_check_filesystem_overrides_empty_boards_dir(self):
        os.makedirs(self.boards_dir)
        self.assertFalse(discovery_utils.check_filesystem_overrides(self.app_path, "board1"))

    def test_check_filesystem_overrides_match_conf(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "board1.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "board1"))

    def test_check_filesystem_overrides_match_overlay(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "board1.overlay"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "board1"))

    def test_check_filesystem_overrides_match_with_qualifier(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "board1_qual.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "board1/qual"))

    def test_check_filesystem_overrides_match_fallback(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "board1.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "board1/qual"))

    def test_check_filesystem_overrides_no_match_with_qualifier(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "board2.conf"), 'w') as f:
            f.write("")
        self.assertFalse(discovery_utils.check_filesystem_overrides(self.app_path, "board1/qual"))

    def test_check_filesystem_overrides_match_qemu_xtensa(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "qemu_xtensa_dc233c.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "qemu_xtensa/dc233c"))

    def test_check_filesystem_overrides_match_nested_qualifier(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "rpi_pico2_rp2350_m33.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "rpi_pico2/rp2350/m33"))

    def test_parse_board_id(self):
        self.assertEqual(discovery_utils.parse_board_id("nrf52833dk"), ("nrf52833dk", "", ""))
        self.assertEqual(discovery_utils.parse_board_id("nrf52833dk/nrf52833"), ("nrf52833dk", "nrf52833", ""))
        self.assertEqual(discovery_utils.parse_board_id("nrf52833dk@0.7.0"), ("nrf52833dk", "", "0.7.0"))
        self.assertEqual(discovery_utils.parse_board_id("nrf52833dk/nrf52833@0.7.0"), ("nrf52833dk", "nrf52833", "0.7.0"))
        self.assertEqual(discovery_utils.parse_board_id("nrf52833dk@0.7.0/nrf52833"), ("nrf52833dk", "nrf52833", "0.7.0"))

    def test_get_app_board_override_candidates(self):
        cands = discovery_utils.get_app_board_override_candidates("board1", "qual1", "1.0.0", "conf")
        self.assertEqual(
            cands,
            [
                "board1.conf",
                "board1_qual1.conf",
                "board1_1_0_0.conf",
                "board1@1.0.0.conf",
                "board1_qual1_1_0_0.conf",
                "board1_qual1@1.0.0.conf",
            ],
        )

    def test_get_app_board_override_candidates_multi_segment(self):
        cands = discovery_utils.get_app_board_override_candidates("nrf5340dk", "nrf5340/cpuapp", "", "defconfig")
        self.assertEqual(
            cands,
            [
                "nrf5340dk.defconfig",
                "nrf5340dk_nrf5340.defconfig",
                "nrf5340dk_nrf5340_cpuapp.defconfig",
            ],
        )

    def test_check_filesystem_overrides_match_revision(self):
        os.makedirs(self.boards_dir)
        with open(os.path.join(self.boards_dir, "nrf52833dk@0.7.0.conf"), 'w') as f:
            f.write("")
        self.assertTrue(discovery_utils.check_filesystem_overrides(self.app_path, "nrf52833dk/nrf52833@0.7.0"))

if __name__ == '__main__':
    unittest.main()
