# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Utilities for flashing Zephyr devices using West runners."""

import argparse
import logging
import os
from pathlib import Path
import sys
import yaml
import serial
import serial.tools.list_ports
from python.runfiles import runfiles

sys.dont_write_bytecode = True

try:
    import pylink
except ImportError:
    pylink = None

_LOG = logging.getLogger(__name__)


def setup_tool_paths(r):
    """Locate J-Link and OpenOCD and add them to PATH if found."""
    extra_paths = []

    # 1. J-Link
    jlink_path = os.environ.get("ZEPHYR_JLINK_PATH")
    if jlink_path:
        if os.path.isdir(jlink_path):
            extra_paths.append(jlink_path)
        elif os.path.isfile(jlink_path):
            extra_paths.append(os.path.dirname(jlink_path))
    else:
        # Search standard locations
        standard_jlink_dirs = [
            Path("/opt/SEGGER/JLink"),
            Path("/usr/bin"),
            Path("/usr/local/bin"),
        ]
        # Also check for versioned dirs in /opt/SEGGER
        if os.path.exists("/opt/SEGGER"):
            opt_segger = Path("/opt/SEGGER")
            for entry in opt_segger.iterdir():
                if os.path.isdir(entry) and entry.name.startswith("JLink"):
                    standard_jlink_dirs.append(entry)

        for d in standard_jlink_dirs:
            if os.path.exists(d / "JLinkExe") or os.path.exists(d / "JLink.exe"):
                extra_paths.append(str(d))
                break

    # 2. OpenOCD
    openocd_path = os.environ.get("ZEPHYR_OPENOCD_PATH")
    if openocd_path:
        if os.path.isdir(openocd_path):
            extra_paths.append(openocd_path)
        elif os.path.isfile(openocd_path):
            extra_paths.append(os.path.dirname(openocd_path))
    else:
        # We can also check if we packaged it, but for now fallback to PATH
        pass

    if extra_paths:
        path_env = os.environ.get("PATH", "")
        # Prepend to PATH so they take precedence
        os.environ["PATH"] = os.pathsep.join(
            extra_paths + [path_env] if path_env else extra_paths
        )


def auto_detect_device(serial_port=None, serial_number=None):
    """Auto-detects missing serial port or serial number.

    If both are provided, returns them as is. If one is missing, attempts to
    resolve the other. If both are missing, attempts to pair a single connected
    J-Link probe with a single CDC serial port.

    Args:
        serial_port: Provided serial port, or None.
        serial_number: Provided serial number, or None.

    Returns:
        A tuple of (serial_port, serial_number), or (None, None) if
        auto-detection fails.
    """
    if serial_port and serial_number:
        return serial_port, serial_number

    probes = []
    if pylink is not None:
        try:
            jlink = pylink.JLink()
            emulators = jlink.connected_emulators()
            probes = [str(info.SerialNumber) for info in emulators]
        except Exception as e:
            print(f"Warning: Failed to query J-Link probes: {e}", file=sys.stderr)
    else:
        print(
            "Warning: Failed to query J-Link probes: pylink module not available",
            file=sys.stderr,
        )

    ports = serial.tools.list_ports.comports()

    _LOG.info("Detected serial ports:")
    for p in ports:
        _LOG.info(
            f"  {p.device}: serial_number={p.serial_number}, hwid={p.hwid}, desc={p.description}"
        )
    _LOG.info("Detected J-Link probes: %s", probes)

    if serial_number and not serial_port:
        for p in ports:
            if p.serial_number and (
                p.serial_number == serial_number
                or serial_number.endswith(p.serial_number)
                or p.serial_number.endswith(serial_number)
            ):
                return p.device, serial_number
        raise RuntimeError(f"Could not find serial port for device {serial_number}")

    if serial_port and not serial_number:
        for p in ports:
            if p.device == serial_port:
                if p.serial_number:
                    return serial_port, p.serial_number
                sanitized_port = serial_port.replace("/", "_")
                return serial_port, sanitized_port
        raise RuntimeError(f"Serial port {serial_port} not found on host")

    if len(probes) == 1:
        sn = probes[0]
        for p in ports:
            if p.serial_number and (
                p.serial_number == sn
                or sn.endswith(p.serial_number)
                or p.serial_number.endswith(sn)
            ):
                return p.device, sn
        cdc_ports = [p for p in ports if "ACM" in p.device or "USB" in p.device]
        if len(cdc_ports) == 1:
            return cdc_ports[0].device, sn

    if len(probes) > 1:
        raise RuntimeError(
            f"Multiple J-Link probes detected ({probes}). Please specify --serial-number explicitly."
        )
    if len(ports) > 0:
        cdc_ports = [p for p in ports if "ACM" in p.device or "USB" in p.device]
        if len(cdc_ports) == 1:
            p = cdc_ports[0]
            sn = p.serial_number or p.device.replace("/", "_")
            return p.device, sn

    return None, None


def monitor_serial(serial_port, baud_rate=115200):
    """Monitors a serial port until KeyboardInterrupt."""
    print(f"--- Monitoring serial port {serial_port} at {baud_rate} baud ---")
    print("Press Ctrl+C to stop.")
    try:
        ser = serial.Serial(serial_port, baud_rate, timeout=1.0)
        try:
            ser.dtr = True
            ser.rts = True
        except IOError:
            pass

        while True:
            try:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    sys.stdout.write(data.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
            except (serial.SerialException, OSError) as e:
                print(f"\nSerial read error: {e}. Stopping.", file=sys.stderr)
                break
    except serial.SerialException as e:
        print(f"Failed to open serial port {serial_port}: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")
    finally:
        if "ser" in locals() and ser.is_open:
            ser.close()
    return 0


def flash_main(
    yaml_path,
    binary_path=None,
    monitor=False,
    serial_port=None,
    baud_rate=115200,
    serial_number=None,
    extra_args=[],
):
    """Flashes a Zephyr binary using runners.yaml configuration.

    Args:
        yaml_path: Path to the runners.yaml file (rlocation or path).
        binary_path: Optional path to the binary to flash (overrides yaml).
        monitor: Whether to monitor the serial port after flashing.
        serial_port: Serial port to monitor.
        baud_rate: Baud rate for serial port.
        serial_number: Serial number of the board.
        extra_args: Extra arguments to pass to the flash runner.

    Returns:
        0 on success, non-zero on failure.
    """
    r = runfiles.Create()
    if not r:
        raise RuntimeError("Failed to initialize runfiles")

    def safe_resolve(p):
        if not p:
            return None
        if os.path.exists(p):
            return str(Path(p).resolve())
        try:
            resolved = r.Rlocation(p)
            if resolved and os.path.exists(resolved):
                return resolved
        except Exception:
            pass
        return str(Path(p).resolve())

    resolved_yaml_path = safe_resolve(yaml_path)
    if resolved_yaml_path and os.path.exists(resolved_yaml_path):
        yaml_file = Path(resolved_yaml_path)
    else:
        raise RuntimeError(f"Failed to locate runners.yaml: {yaml_path}")

    with open(yaml_file, "r") as f:
        config = yaml.safe_load(f)

    # Setup sys.path for Zephyr scripts
    runner_core_path = safe_resolve("zephyr/scripts/west_commands/runners/core.py")
    if not runner_core_path or not os.path.exists(runner_core_path):
        runner_core_path = safe_resolve("_main/scripts/west_commands/runners/core.py")
    if not runner_core_path or not os.path.exists(runner_core_path):
        raise RuntimeError(
            "Failed to locate Zephyr runner scripts in runfiles. "
            "Ensure @zephyr//scripts:west_runners_scripts is in data."
        )

    west_commands_dir = Path(runner_core_path).parent.parent
    if str(west_commands_dir) not in sys.path:
        sys.path.insert(0, str(west_commands_dir))

    import runners.core
    import runners

    cfg = config["config"]
    board_dir = cfg.get("board_dir")
    if board_dir:
        resolved_board_dir = safe_resolve(board_dir)
        if not resolved_board_dir or not os.path.exists(resolved_board_dir):
            resolved_board_dir = safe_resolve("zephyr/" + board_dir)
        if resolved_board_dir and os.path.exists(resolved_board_dir):
            cfg["board_dir"] = resolved_board_dir

    for key in ["elf_file", "hex_file", "bin_file"]:
        if key in cfg and cfg[key]:
            cfg[key] = safe_resolve(cfg[key])

    setup_tool_paths(r)

    flash_runner = config.get("flash-runner")
    if not flash_runner:
        if binary_path:
            abs_binary = safe_resolve(binary_path)
            if abs_binary and os.path.exists(abs_binary):
                try:
                    os.execv(abs_binary, [abs_binary] + extra_args)
                except OSError as e:
                    if e.errno == 8:
                        print(
                            f"Error: Binary {binary_path} is not host-executable. "
                            f"No flash runner is configured for this board.",
                            file=sys.stderr,
                        )
                    else:
                        print(f"Failed to execute binary: {e}", file=sys.stderr)
                    return 1
                return 0
            else:
                print(
                    f"No flash runner configured, and binary {binary_path} not found.",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                "No flash runner configured, and no binary path provided.",
                file=sys.stderr,
            )
            return 1

    args_dict = config.get("args") or {}
    runner_args = args_dict.get(flash_runner) or []
    runner_args = list(runner_args)
    runner_args.extend(extra_args)

    # Add runner library dependencies to sys.path if specified
    python_paths = cfg.get("python_paths") or []
    for p in python_paths:
        resolved_path = safe_resolve(p)
        if (
            resolved_path
            and os.path.exists(resolved_path)
            and resolved_path not in sys.path
        ):
            _LOG.info(f"Adding runner python path: {resolved_path}")
            sys.path.insert(0, resolved_path)

    # Load custom runner if specified
    custom_runner_path = cfg.get("runner_source")
    if custom_runner_path:
        resolved_custom_runner = r.Rlocation(custom_runner_path)
        if not resolved_custom_runner or not os.path.exists(resolved_custom_runner):
            raise RuntimeError(
                f"Failed to locate custom runner source in runfiles: {custom_runner_path} (resolved: {resolved_custom_runner})"
            )

        _LOG.info(f"Loading custom runner from {resolved_custom_runner}")
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"runners.{flash_runner}", resolved_custom_runner
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"runners.{flash_runner}"] = module
        spec.loader.exec_module(module)

    try:
        __import__("runners." + flash_runner)
    except ImportError:
        pass

    runner_cls = runners.get_runner_cls(flash_runner)

    build_dir = str(yaml_file.parent)
    runner_config = runners.core.RunnerConfig(
        build_dir=build_dir,
        board_dir=cfg.get("board_dir"),
        elf_file=cfg.get("elf_file"),
        exe_file=cfg.get("exe_file"),
        hex_file=cfg.get("hex_file"),
        bin_file=cfg.get("bin_file"),
        uf2_file=cfg.get("uf2_file"),
        mot_file=cfg.get("mot_file"),
        file=cfg.get("file"),
    )

    parser = argparse.ArgumentParser()
    runner_cls.add_parser(parser)
    parsed_args, unknown = parser.parse_known_args(runner_args)
    if unknown:
        print(f"Warning: unknown arguments for {flash_runner}: {unknown}")

    runner = runner_cls.create(runner_config, parsed_args)

    try:
        runner.run("flash")
    except Exception as e:
        print(f"Flashing failed: {e}")
        return 1

    if monitor:
        if not serial_port or not serial_number:
            try:
                serial_port, serial_number = auto_detect_device(
                    serial_port, serial_number
                )
            except RuntimeError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1

        if not serial_port:
            print(
                "Serial port not specified and auto-detection failed. Cannot monitor.",
                file=sys.stderr,
            )
            return 1

        print(f"Using device: Serial={serial_number}, Port={serial_port}")
        return monitor_serial(serial_port, baud_rate)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml", required=True)
    parser.add_argument("--binary", default=None)
    parser.add_argument(
        "--monitor", action="store_true", help="Monitor serial port after flashing."
    )
    parser.add_argument("--serial-port", default=None, help="Serial port to monitor.")
    parser.add_argument(
        "--baud-rate", type=int, default=115200, help="Baud rate for serial port."
    )
    parser.add_argument(
        "--serial-number", default=None, help="Serial number of the board."
    )
    args, unknown = parser.parse_known_args()
    sys.exit(
        flash_main(
            yaml_path=args.yaml,
            binary_path=args.binary,
            monitor=args.monitor,
            serial_port=args.serial_port,
            baud_rate=args.baud_rate,
            serial_number=args.serial_number,
            extra_args=unknown,
        )
    )
