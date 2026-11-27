# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for zephyr_flash_utils."""

import tempfile
import unittest
from pathlib import Path
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

class TestRunnerBuildDir(unittest.TestCase):
    """zephyr_app ships zephyr/<app>.config; runners read <build_dir>/zephyr/.config."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "bin" / "puck"
        (self.out / "zephyr").mkdir(parents=True)
        self.yaml = self.out / "puck_runners_yaml.yaml"
        self.yaml.write_text("config: {}\n")
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_app_config_exposed_as_dot_config(self):
        (self.out / "zephyr" / "puck.config").write_text("CONFIG_BIG_ENDIAN=n\n")
        build_dir = Path(zephyr_flash_utils.runner_build_dir(self.yaml, self.scratch))
        self.assertEqual((build_dir / "zephyr" / ".config").read_text(), "CONFIG_BIG_ENDIAN=n\n")
        self.assertFalse((self.out / "zephyr" / ".config").exists())

    def test_picks_this_apps_config_among_several(self):
        (self.out / "zephyr" / "puck.config").write_text("puck\n")
        (self.out / "zephyr" / "other.config").write_text("other\n")
        build_dir = Path(zephyr_flash_utils.runner_build_dir(self.yaml, self.scratch))
        self.assertEqual((build_dir / "zephyr" / ".config").read_text(), "puck\n")

    def test_existing_dot_config_keeps_yaml_dir(self):
        (self.out / "zephyr" / ".config").write_text("x\n")
        self.assertEqual(zephyr_flash_utils.runner_build_dir(self.yaml, self.scratch), str(self.out))

    def test_no_config_keeps_yaml_dir(self):
        self.assertEqual(zephyr_flash_utils.runner_build_dir(self.yaml, self.scratch), str(self.out))


if __name__ == '__main__':
    unittest.main()
