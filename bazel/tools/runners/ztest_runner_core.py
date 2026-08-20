# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Core logic for running Zephyr ztests in Bazel."""

import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import serial
import serial.tools.list_ports
import yaml
import zephyr_flash_utils

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import pylink
except ImportError:
    pylink = None

def run_ztest(binary_path, runners_yaml_path=None, serial_port=None, baud_rate=115200, serial_number=None, stop_at=10, success_signature="PROJECT EXECUTION SUCCESSFUL", xml_output_file=None):
    """Runs a Zephyr binary and checks for success.

    Args:
        binary_path: Path to the simulator binary.
        runners_yaml_path: Path to the runners.yaml file.
        serial_port: Serial port to monitor.
        baud_rate: Baud rate for serial port.
        serial_number: Serial number of the board.
        stop_at: Timeout in seconds.
        success_signature: String to look for in output to determine success.
        xml_output_file: Path to write JUnit XML results.

    Returns:
        0 on success, non-zero on failure.
    """
    if runners_yaml_path:
        with open(runners_yaml_path, 'r') as f:
            runners_config = yaml.safe_load(f)

        flash_runner = runners_config.get('flash-runner')
        if flash_runner:
            return _run_ztest_hw(
                binary_path=binary_path,
                runners_yaml_path=runners_yaml_path,
                runners_config=runners_config,
                serial_port=serial_port,
                baud_rate=baud_rate,
                serial_number=serial_number,
                stop_at=stop_at,
                success_signature=success_signature,
                xml_output_file=xml_output_file
            )

    print(f"Running ztest binary: {binary_path}")
    print(f"Timeout: {stop_at}s")
    print(f"Success signature: '{success_signature}'")

    start_time = time.time()

    # We use native_sim arguments if applicable, but since we might run other host binaries,
    # we just run the binary directly. native_sim supports standard stdinout.
    # We pass -uart_stdinout to native_sim to ensure it uses stdout.
    cmd = [binary_path]


    try:
        # Run the subprocess, capturing stdout and merging stderr.
        # We use a timeout to prevent hangs.
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=stop_at
        )
    except subprocess.TimeoutExpired as e:
        duration = time.time() - start_time
        error_msg = f"\nTest timed out after {stop_at} seconds.\n"
        if e.output:
             error_msg += f"Captured output before timeout:\n{e.output}\n"
        sys.stderr.write(error_msg)
        if xml_output_file:
             _write_junit_xml(xml_output_file, "ztest", "timeout", duration, error_msg, e.output or "")
        return 1

    duration = time.time() - start_time
    output = result.stdout

    # Print the output so it appears in Bazel's test.log
    print("--- Simulator Output ---")
    print(output)
    print("------------------------")

    if result.returncode != 0:
        error_msg = f"Simulator exited with non-zero code: {result.returncode}\n"
        sys.stderr.write(error_msg)
        if xml_output_file:
             _write_junit_xml(xml_output_file, "ztest", "crash", duration, error_msg, output)
        return result.returncode

    if success_signature not in output:
        error_msg = f"Success signature '{success_signature}' not found in output.\n"
        sys.stderr.write(error_msg)
        if xml_output_file:
             _write_junit_xml(xml_output_file, "ztest", "failure", duration, error_msg, output)
        return 1

    print("Test passed successfully.")
    if xml_output_file:
         _write_junit_xml(xml_output_file, "ztest", "pass", duration, "", output)
    return 0

def _write_junit_xml(filepath, test_name, status, duration, error_msg, stdout):
    """Writes a simple JUnit XML file."""
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(testsuites, "testsuite", name="ztest", tests="1", failures="1" if status != "pass" else "0", time=str(duration))
    testcase = ET.SubElement(testsuite, "testcase", name=test_name, classname="ztest", time=str(duration))

    # Add stdout to system-out
    system_out = ET.SubElement(testcase, "system-out")
    system_out.text = stdout

    if status == "timeout":
        ET.SubElement(testcase, "error", message="Timeout", type="Timeout").text = error_msg
    elif status == "crash":
        ET.SubElement(testcase, "error", message="Crash", type="Crash").text = error_msg
    elif status == "failure":
        ET.SubElement(testcase, "failure", message="Failure", type="Failure").text = error_msg

    tree = ET.ElementTree(testsuites)
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    tree.write(filepath, encoding="UTF-8", xml_declaration=True)


def _run_ztest_hw(binary_path, runners_yaml_path, runners_config, serial_port, baud_rate, serial_number, stop_at, success_signature, xml_output_file):
    """Flashes and runs a ztest on a physical hardware device.

    Flashes the device using zephyr_flash_utils, then monitors the serial port
    for the success signature.

    Args:
        binary_path: Path to the binary to flash.
        runners_yaml_path: Path to the runners.yaml file.
        runners_config: Parsed runners.yaml configuration.
        serial_port: Serial port to monitor (auto-detected if None).
        baud_rate: Baud rate for the serial port.
        serial_number: Serial number of the device (auto-detected if None).
        stop_at: Timeout in seconds.
        success_signature: Signature to look for in output.
        xml_output_file: Path to write JUnit XML results.

    Returns:
        0 on success, non-zero on failure.
    """
    if not serial_port or not serial_number:
        serial_port, serial_number = zephyr_flash_utils.auto_detect_device(serial_port, serial_number)

    if not serial_port:
        raise RuntimeError("Serial port not specified and auto-detection failed.")
    if not serial_number:
        raise RuntimeError("Serial number not specified and auto-detection failed.")

    print(f"Using device: Serial={serial_number}, Port={serial_port}")

    lock_file_path = f"{tempfile.gettempdir()}/zephyr_lock_{serial_number}.lock"
    try:
        fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o666)
            os.write(fd, f"{os.getpid()}\n".encode())
        finally:
            os.close(fd)
    except FileExistsError:
        pass

    lock_file = open(lock_file_path, 'r')
    has_lock = False
    if fcntl:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            has_lock = True
        except OSError as e:
            lock_file.close()
            raise RuntimeError(f"Device {serial_number} is busy (lock acquired by another process).") from e
    else:
        print("Warning: Concurrency protection (file locking) is not supported on this platform. Proceeding without lock.", file=sys.stderr)

    try:
        try:
            ser = serial.Serial(serial_port, baud_rate, timeout=1)
        except serial.SerialException as e:
            raise RuntimeError(f"Failed to open serial port {serial_port}: {e}") from e

        try:
            ser.reset_input_buffer()

            print(f"Flashing device {serial_number} with {binary_path}...")
            extra_flash_args = ["--dev-id", serial_number]

            ret = zephyr_flash_utils.flash_main(runners_yaml_path, binary_path, extra_flash_args)
            if ret != 0:
                raise RuntimeError(f"Flashing failed with exit code: {ret}")

            print("Monitoring serial port for success signature...")
            start_time = time.time()
            output_lines = []
            success = False

            while time.time() - start_time < stop_at:
                line = ser.readline().decode('utf-8', errors='replace')
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    output_lines.append(line)
                    if success_signature in line:
                        success = True
                        break

            duration = time.time() - start_time
            full_output = "".join(output_lines)

            if not success:
                error_msg = f"Timed out after {stop_at} seconds waiting for success signature.\n"
                sys.stderr.write(error_msg)
                if xml_output_file:
                     _write_junit_xml(xml_output_file, "ztest", "timeout", duration, error_msg, full_output)
                return 1

            print("Test passed successfully.")
            if xml_output_file:
                 _write_junit_xml(xml_output_file, "ztest", "pass", duration, "", full_output)
            return 0

        finally:
            ser.close()
    finally:
        if has_lock and fcntl:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_file.close()



