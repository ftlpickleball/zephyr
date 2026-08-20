# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for zephyr_flash_utils."""

import unittest
from unittest import mock
import sys

# Mock rules_python runfiles before import
sys.modules['rules_python'] = mock.MagicMock()
sys.modules['rules_python.python'] = mock.MagicMock()
sys.modules['rules_python.python.runfiles'] = mock.MagicMock()

import zephyr_flash_utils

class TestZephyrFlashUtils(unittest.TestCase):

    def setUp(self):
        self._orig_sys_path = list(sys.path)
        # Prepare sys.modules mocks
        self.mock_runner_core = mock.MagicMock()
        self.mock_runners = mock.MagicMock()
        sys.modules['runners'] = self.mock_runners
        sys.modules['runners.core'] = self.mock_runner_core

    def tearDown(self):
        sys.path = list(self._orig_sys_path)
        # Clean up sys.modules
        sys.modules.pop('runners', None)
        sys.modules.pop('runners.core', None)
        sys.modules.pop('runners.mock_runner', None)

    @mock.patch('zephyr_flash_utils.runfiles.Create')
    @mock.patch('builtins.open')
    @mock.patch('zephyr_flash_utils.yaml.safe_load')
    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_flash_main_success(self, mock_exists, mock_which, mock_yaml_load, mock_file_open, mock_runfiles_create):
        # Setup mocks
        mock_runfiles = mock.MagicMock()
        mock_runfiles_create.return_value = mock_runfiles
        mock_runfiles.Rlocation.side_effect = lambda x: {
            "test_runners.yaml": "/resolved/test_runners.yaml",
            "zephyr/scripts/west_commands/runners/core.py": "/resolved/zephyr/scripts/west_commands/runners/core.py",
            "zephyr.elf": "/resolved/zephyr.elf",
            "boards/nordic/nrf52833dk": "/resolved/boards/nordic/nrf52833dk",
        }.get(x, x)

        mock_yaml_load.return_value = {
            "config": {
                "board_dir": "boards/nordic/nrf52833dk",
                "elf_file": "zephyr.elf",
            },
            "flash-runner": "mock_runner",
            "args": {
                "mock_runner": ["--some-arg"],
            }
        }
        # Avoid checking /opt/SEGGER listdir by returning False for it
        mock_exists.side_effect = lambda x: {
            "/opt/SEGGER": False,
            "/usr/bin/JLinkExe": True,
            "/resolved/test_runners.yaml": True,
            "/resolved/zephyr/scripts/west_commands/runners/core.py": True,
            "/resolved/zephyr.elf": True,
            "/resolved/boards/nordic/nrf52833dk": True,
        }.get(x, False)
        mock_which.return_value = "/usr/bin/mock_tool"

        # Mock Zephyr runner classes
        mock_runner_cls = mock.MagicMock()
        mock_runner_inst = mock.MagicMock()

        self.mock_runners.get_runner_cls.return_value = mock_runner_cls
        mock_runner_cls.create.return_value = mock_runner_inst

        # Inject mock module for the specific runner to avoid import error in flash_main
        sys.modules['runners.mock_runner'] = mock.MagicMock()

        # Run flash_main
        result = zephyr_flash_utils.flash_main("test_runners.yaml")

        self.assertEqual(result, 0)
        self.mock_runners.get_runner_cls.assert_called_once_with('mock_runner')
        mock_runner_cls.create.assert_called_once()
        mock_runner_inst.run.assert_called_once_with('flash')

    @mock.patch('zephyr_flash_utils.runfiles.Create')
    @mock.patch('builtins.open')
    @mock.patch('zephyr_flash_utils.yaml.safe_load')
    @mock.patch('os.execv')
    @mock.patch('os.path.exists')
    def test_flash_main_fallback_run(self, mock_exists, mock_execv, mock_yaml_load, mock_file_open, mock_runfiles_create):
        # Setup mocks
        mock_runfiles = mock.MagicMock()
        mock_runfiles_create.return_value = mock_runfiles
        mock_runfiles.Rlocation.side_effect = lambda x: {
            "test_runners.yaml": "/resolved/test_runners.yaml",
            "zephyr/scripts/west_commands/runners/core.py": "/resolved/zephyr/scripts/west_commands/runners/core.py",
            "zephyr.elf": "/resolved/zephyr.elf",
        }.get(x, x)

        mock_yaml_load.return_value = {
            "config": {
                "board_dir": "boards/native/native_sim",
                "elf_file": "zephyr.elf",
            },
            "flash-runner": "", # No runner
            "args": {}
        }
        mock_exists.side_effect = lambda x: {
            "/resolved/test_runners.yaml": True,
            "/resolved/zephyr.elf": True,
            "/resolved/zephyr/scripts/west_commands/runners/core.py": True,
        }.get(x, False)

        # Run flash_main with binary
        result = zephyr_flash_utils.flash_main("test_runners.yaml", binary_path="zephyr.elf", extra_args=["--foo"])

        self.assertEqual(result, 0)
        mock_execv.assert_called_once_with("/resolved/zephyr.elf", ["/resolved/zephyr.elf", "--foo"])

if __name__ == '__main__':
    unittest.main()
