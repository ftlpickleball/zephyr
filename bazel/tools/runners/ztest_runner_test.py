# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for ztest_runner."""

import os
import sys
import unittest
from unittest import mock

import ztest_runner


class TestZTestRunner(unittest.TestCase):

    @mock.patch("ztest_runner.runfiles.Create")
    @mock.patch("ztest_runner.ztest_runner_core.run_ztest")
    @mock.patch("os.path.exists")
    def test_main_success(
        self, mock_exists, mock_run_ztest, mock_runfiles_create
    ):
        # Setup mocks
        mock_exists.return_value = True
        mock_run_ztest.return_value = 0

        mock_r = mock.MagicMock()
        mock_r.Rlocation.return_value = "/path/to/resolved/bin"
        mock_runfiles_create.return_value = mock_r

        # Execute with standard arguments
        test_args = [
            "ztest_runner.py",
            "--binary",
            "my_binary_rlocation",
            "--stop-at",
            "15",
            "--success-signature",
            "SIGNATURE",
        ]
        with mock.patch.object(sys, "argv", test_args):
            res = ztest_runner.main()

        self.assertEqual(res, 0)
        mock_r.Rlocation.assert_called_once_with("my_binary_rlocation")
        mock_run_ztest.assert_called_once_with(
            binary_path="/path/to/resolved/bin",
            runners_yaml_path=None,
            serial_port=None,
            baud_rate=115200,
            serial_number=None,
            stop_at=15,
            success_signature="SIGNATURE",
            xml_output_file=os.environ.get("XML_OUTPUT_FILE"),
        )

    @mock.patch("ztest_runner.runfiles.Create")
    @mock.patch("ztest_runner.ztest_runner_core.run_ztest")
    @mock.patch("os.path.exists")
    def test_main_quote_stripping(
        self, mock_exists, mock_run_ztest, mock_runfiles_create
    ):
        mock_exists.return_value = True
        mock_run_ztest.return_value = 0

        mock_r = mock.MagicMock()
        mock_r.Rlocation.return_value = "/path/to/resolved/bin"
        mock_runfiles_create.return_value = mock_r

        # Test double quotes stripping
        test_args = [
            "ztest_runner.py",
            "--binary",
            "bin",
            "--success-signature",
            '"DOUBLE QUOTED SIGNATURE"',
        ]
        with mock.patch.object(sys, "argv", test_args):
            ztest_runner.main()
        mock_run_ztest.assert_called_with(
            binary_path="/path/to/resolved/bin",
            runners_yaml_path=None,
            serial_port=None,
            baud_rate=115200,
            serial_number=None,
            stop_at=10,
            success_signature="DOUBLE QUOTED SIGNATURE",
            xml_output_file=os.environ.get("XML_OUTPUT_FILE"),
        )

        # Test single quotes stripping
        test_args = [
            "ztest_runner.py",
            "--binary",
            "bin",
            "--success-signature",
            "'SINGLE QUOTED SIGNATURE'",
        ]
        with mock.patch.object(sys, "argv", test_args):
            ztest_runner.main()
        mock_run_ztest.assert_called_with(
            binary_path="/path/to/resolved/bin",
            runners_yaml_path=None,
            serial_port=None,
            baud_rate=115200,
            serial_number=None,
            stop_at=10,
            success_signature="SINGLE QUOTED SIGNATURE",
            xml_output_file=os.environ.get("XML_OUTPUT_FILE"),
        )

    @mock.patch("ztest_runner.runfiles.Create")
    @mock.patch("ztest_runner.ztest_runner_core.run_ztest")
    @mock.patch("os.path.exists")
    def test_main_hw_arguments(
        self, mock_exists, mock_run_ztest, mock_runfiles_create
    ):
        mock_exists.return_value = True
        mock_run_ztest.return_value = 0

        mock_r = mock.MagicMock()
        mock_r.Rlocation.side_effect = lambda x: {
            "bin": "/path/to/resolved/bin",
            "runners.yaml": "/path/to/resolved/runners.yaml",
        }.get(x, x)
        mock_runfiles_create.return_value = mock_r

        test_args = [
            "ztest_runner.py",
            "--binary",
            "bin",
            "--runners-yaml",
            "runners.yaml",
            "--serial-port",
            "/dev/ttyACM0",
            "--baud-rate",
            "9600",
            "--serial-number",
            "123456",
        ]
        with mock.patch.object(sys, "argv", test_args):
            ztest_runner.main()

        mock_run_ztest.assert_called_once_with(
            binary_path="/path/to/resolved/bin",
            runners_yaml_path="/path/to/resolved/runners.yaml",
            serial_port="/dev/ttyACM0",
            baud_rate=9600,
            serial_number="123456",
            stop_at=10,
            success_signature="PROJECT EXECUTION SUCCESSFUL",
            xml_output_file=os.environ.get("XML_OUTPUT_FILE"),
        )

    @mock.patch("ztest_runner.runfiles.Create")
    def test_main_missing_runfiles(self, mock_runfiles_create):
        mock_runfiles_create.return_value = None

        test_args = ["ztest_runner.py", "--binary", "bin"]
        with mock.patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                ztest_runner.main()

        self.assertEqual(
            cm.exception.code, "Failed to initialize runfiles library."
        )

    @mock.patch("ztest_runner.runfiles.Create")
    @mock.patch("os.path.exists")
    def test_main_binary_not_found(self, mock_exists, mock_runfiles_create):
        mock_exists.return_value = False
        mock_r = mock.MagicMock()
        mock_r.Rlocation.return_value = "/nonexistent/bin"
        mock_runfiles_create.return_value = mock_r

        test_args = ["ztest_runner.py", "--binary", "bin"]
        with mock.patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                ztest_runner.main()

        self.assertEqual(
            cm.exception.code, "Failed to find binary runfiles target: bin"
        )


if __name__ == "__main__":
    unittest.main()
