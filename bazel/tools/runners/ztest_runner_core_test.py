# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for ztest_runner_core."""

import os
import tempfile
import unittest
from unittest import mock
import subprocess
import fcntl
import xml.etree.ElementTree as ET

import ztest_runner_core

class TestZTestRunnerCore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.xml_file = os.path.join(self.temp_dir.name, "output.xml")

    def tearDown(self):
        self.temp_dir.cleanup()

    @mock.patch("subprocess.run")
    def test_success(self, mock_run):
        # Mock successful execution
        mock_run.return_value = mock.MagicMock(
            returncode=0,
            stdout="Booting Zephyr...\nRunning tests...\nPROJECT EXECUTION SUCCESSFUL\n"
        )

        res = ztest_runner_core.run_ztest("fake_bin", xml_output_file=self.xml_file)
        self.assertEqual(res, 0)

        # Verify XML
        self.assertTrue(os.path.exists(self.xml_file))
        tree = ET.parse(self.xml_file)
        root = tree.getroot()
        self.assertEqual(root.tag, "testsuites")
        testcase = root.find("testsuite/testcase")
        self.assertIsNotNone(testcase)
        self.assertIsNone(testcase.find("failure"))
        self.assertIsNone(testcase.find("error"))

    @mock.patch("subprocess.run")
    def test_failure_exit_code(self, mock_run):
        # Mock crash (non-zero exit code)
        mock_run.return_value = mock.MagicMock(
            returncode=1,
            stdout="Booting Zephyr...\nAssert failed!\n"
        )

        res = ztest_runner_core.run_ztest("fake_bin", xml_output_file=self.xml_file)
        self.assertEqual(res, 1)

        # Verify XML
        self.assertTrue(os.path.exists(self.xml_file))
        tree = ET.parse(self.xml_file)
        root = tree.getroot()
        testcase = root.find("testsuite/testcase")
        self.assertIsNotNone(testcase.find("error"))
        self.assertEqual(testcase.find("error").get("type"), "Crash")

    @mock.patch("subprocess.run")
    def test_failure_missing_signature(self, mock_run):
        # Mock execution that exits 0 but doesn't print success signature
        mock_run.return_value = mock.MagicMock(
            returncode=0,
            stdout="Booting Zephyr...\nHung or exited early without message...\n"
        )

        res = ztest_runner_core.run_ztest("fake_bin", xml_output_file=self.xml_file)
        self.assertEqual(res, 1)

        # Verify XML
        self.assertTrue(os.path.exists(self.xml_file))
        tree = ET.parse(self.xml_file)
        root = tree.getroot()
        testcase = root.find("testsuite/testcase")
        self.assertIsNotNone(testcase.find("failure"))
        self.assertEqual(testcase.find("failure").get("type"), "Failure")

    @mock.patch("subprocess.run")
    def test_timeout(self, mock_run):
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="fake_bin", timeout=10, output="Booting...")

        res = ztest_runner_core.run_ztest("fake_bin", stop_at=10, xml_output_file=self.xml_file)
        self.assertEqual(res, 1)

        # Verify XML
        self.assertTrue(os.path.exists(self.xml_file))
        tree = ET.parse(self.xml_file)
        root = tree.getroot()
        testcase = root.find("testsuite/testcase")
        self.assertIsNotNone(testcase.find("error"))
        self.assertEqual(testcase.find("error").get("type"), "Timeout")

    @mock.patch("ztest_runner_core.yaml.safe_load")
    @mock.patch("ztest_runner_core.serial.Serial")
    @mock.patch("ztest_runner_core.fcntl.flock")
    @mock.patch("ztest_runner_core.zephyr_flash_utils.flash_main")
    @mock.patch("ztest_runner_core.open", create=True)
    @mock.patch("ztest_runner_core.os.open")
    @mock.patch("ztest_runner_core.os.write")
    @mock.patch("ztest_runner_core.os.close")
    @mock.patch("ztest_runner_core.os.fchmod", create=True)
    def test_hw_success(self, mock_os_fchmod, mock_os_close, mock_os_write, mock_os_open, mock_open, mock_flash_main, mock_flock, mock_serial_cls, mock_yaml_load):
        mock_yaml_load.return_value = {"flash-runner": "jlink"}
        
        mock_serial = mock.MagicMock()
        mock_serial.readline.side_effect = [
            b"Booting...\n",
            b"PROJECT EXECUTION SUCCESSFUL\n"
        ]
        mock_serial_cls.return_value = mock_serial
        mock_flash_main.return_value = 0
        
        # Mock lock file descriptor
        mock_os_open.return_value = 99
        mock_file = mock.MagicMock()
        mock_file.fileno.return_value = 100
        mock_open.return_value = mock_file
        
        res = ztest_runner_core.run_ztest(
            binary_path="fake_bin",
            runners_yaml_path="fake_runners.yaml",
            serial_port="/dev/ttyFake",
            serial_number="12345",
            xml_output_file=self.xml_file
        )
        
        self.assertEqual(res, 0)
        mock_flash_main.assert_called_once_with("fake_runners.yaml", "fake_bin", ["--dev-id", "12345"])
        mock_serial_cls.assert_called_once_with("/dev/ttyFake", 115200, timeout=1)
        mock_flock.assert_has_calls([
            mock.call(100, fcntl.LOCK_EX | fcntl.LOCK_NB),
            mock.call(100, fcntl.LOCK_UN)
        ])

    @mock.patch("ztest_runner_core.yaml.safe_load")
    @mock.patch("ztest_runner_core.serial.Serial")
    @mock.patch("ztest_runner_core.fcntl.flock")
    @mock.patch("ztest_runner_core.zephyr_flash_utils.flash_main")
    @mock.patch("ztest_runner_core.open", create=True)
    @mock.patch("ztest_runner_core.os.open")
    @mock.patch("ztest_runner_core.os.write")
    @mock.patch("ztest_runner_core.os.close")
    @mock.patch("ztest_runner_core.os.fchmod", create=True)
    def test_hw_flash_failure(self, mock_os_fchmod, mock_os_close, mock_os_write, mock_os_open, mock_open, mock_flash_main, mock_flock, mock_serial_cls, mock_yaml_load):
        mock_yaml_load.return_value = {"flash-runner": "jlink"}
        
        mock_serial = mock.MagicMock()
        mock_serial_cls.return_value = mock_serial
        # flash_main returns non-zero for failure
        mock_flash_main.return_value = 1
        
        mock_os_open.return_value = 99
        mock_file = mock.MagicMock()
        mock_file.fileno.return_value = 100
        mock_open.return_value = mock_file
        
        with self.assertRaises(RuntimeError) as context:
            ztest_runner_core.run_ztest(
                binary_path="fake_bin",
                runners_yaml_path="fake_runners.yaml",
                serial_port="/dev/ttyFake",
                serial_number="12345",
                xml_output_file=self.xml_file
            )
        self.assertIn("Flashing failed with exit code: 1", str(context.exception))

    @mock.patch("ztest_runner_core.yaml.safe_load")
    @mock.patch("ztest_runner_core.serial.Serial")
    @mock.patch("ztest_runner_core.fcntl.flock")
    @mock.patch("ztest_runner_core.open", create=True)
    @mock.patch("ztest_runner_core.os.open")
    @mock.patch("ztest_runner_core.os.write")
    @mock.patch("ztest_runner_core.os.close")
    @mock.patch("ztest_runner_core.os.fchmod", create=True)
    def test_hw_lock_busy(self, mock_os_fchmod, mock_os_close, mock_os_write, mock_os_open, mock_open, mock_flock, mock_serial_cls, mock_yaml_load):
        mock_yaml_load.return_value = {"flash-runner": "jlink"}
        
        # Mock flock to raise OSError (device busy)
        mock_flock.side_effect = OSError("Resource temporarily unavailable")
        
        mock_os_open.return_value = 99
        mock_file = mock.MagicMock()
        mock_file.fileno.return_value = 100
        mock_open.return_value = mock_file
        
        with self.assertRaises(RuntimeError) as context:
            ztest_runner_core.run_ztest(
                binary_path="fake_bin",
                runners_yaml_path="fake_runners.yaml",
                serial_port="/dev/ttyFake",
                serial_number="12345",
                xml_output_file=self.xml_file
            )
        self.assertIn("is busy (lock acquired by another process)", str(context.exception))

    @mock.patch("ztest_runner_core.yaml.safe_load")
    @mock.patch("ztest_runner_core.serial.Serial")
    @mock.patch("ztest_runner_core.fcntl.flock")
    @mock.patch("ztest_runner_core.zephyr_flash_utils.flash_main")
    @mock.patch("ztest_runner_core.open", create=True)
    @mock.patch("ztest_runner_core.os.open")
    @mock.patch("ztest_runner_core.os.write")
    @mock.patch("ztest_runner_core.os.close")
    @mock.patch("ztest_runner_core.os.fchmod", create=True)
    @mock.patch("pylink.JLink")
    @mock.patch("serial.tools.list_ports.comports")
    def test_hw_auto_detect(self, mock_comports, mock_jlink_cls, mock_os_fchmod, mock_os_close, mock_os_write, mock_os_open, mock_open, mock_flash_main, mock_flock, mock_serial_cls, mock_yaml_load):
        mock_yaml_load.return_value = {"flash-runner": "jlink"}
        
        # Mock J-Link connected emulators
        mock_jlink = mock.MagicMock()
        mock_emulator_info = mock.MagicMock()
        mock_emulator_info.SerialNumber = 54321
        mock_jlink.connected_emulators.return_value = [mock_emulator_info]
        mock_jlink_cls.return_value = mock_jlink
        
        # Mock serial ports
        mock_port = mock.MagicMock()
        mock_port.device = "/dev/ttyACM0"
        mock_port.serial_number = "54321"
        mock_comports.return_value = [mock_port]
        
        mock_serial = mock.MagicMock()
        mock_serial.readline.side_effect = [
            b"PROJECT EXECUTION SUCCESSFUL\n"
        ]
        mock_serial_cls.return_value = mock_serial
        mock_flash_main.return_value = 0
        
        mock_os_open.return_value = 99
        mock_file = mock.MagicMock()
        mock_file.fileno.return_value = 100
        mock_open.return_value = mock_file
        
        res = ztest_runner_core.run_ztest(
            binary_path="fake_bin",
            runners_yaml_path="fake_runners.yaml",
            xml_output_file=self.xml_file
        )
        
        self.assertEqual(res, 0)
        mock_flash_main.assert_called_once_with("fake_runners.yaml", "fake_bin", ["--dev-id", "54321"])
        mock_serial_cls.assert_called_once_with("/dev/ttyACM0", 115200, timeout=1)
        mock_flock.assert_has_calls([
            mock.call(100, fcntl.LOCK_EX | fcntl.LOCK_NB),
            mock.call(100, fcntl.LOCK_UN)
        ])

if __name__ == "__main__":
    unittest.main()
