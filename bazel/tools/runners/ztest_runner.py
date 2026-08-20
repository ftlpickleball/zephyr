# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Test runner wrapper to execute Zephyr ztests."""

import argparse
import os
import sys

from python.runfiles import runfiles
import ztest_runner_core


def main() -> int:
    """Main entry point for the ztest runner."""
    parser = argparse.ArgumentParser(description="Run Zephyr unit tests.")
    parser.add_argument(
        "--binary", required=True, help="Rlocation path to the binary to run."
    )
    parser.add_argument(
        "--stop-at", type=int, default=10, help="Timeout in seconds."
    )
    parser.add_argument(
        "--success-signature",
        default="PROJECT EXECUTION SUCCESSFUL",
        help="String to match in output for success.",
    )
    parser.add_argument(
        "--runners-yaml", help="Rlocation path to the runners.yaml file."
    )
    parser.add_argument(
        "--serial-port", help="Serial port to monitor (e.g. /dev/ttyACM0)."
    )
    parser.add_argument(
        "--baud-rate",
        type=int,
        default=115200,
        help="Baud rate for serial port.",
    )
    parser.add_argument(
        "--serial-number", help="Serial number of the board to flash/monitor."
    )

    args = parser.parse_args()

    # Resolve runfiles path
    r = runfiles.Create()
    if not r:
        sys.exit("Failed to initialize runfiles library.")

    binary_path = r.Rlocation(args.binary)
    if not binary_path or not os.path.exists(binary_path):
        sys.exit(f"Failed to find binary runfiles target: {args.binary}")

    success_signature = args.success_signature
    if success_signature.startswith('"') and success_signature.endswith('"'):
        success_signature = success_signature[1:-1]
    if success_signature.startswith("'") and success_signature.endswith("'"):
        success_signature = success_signature[1:-1]

    runners_yaml_path = None
    if args.runners_yaml:
        runners_yaml_path = r.Rlocation(args.runners_yaml)
        if not runners_yaml_path or not os.path.exists(runners_yaml_path):
            sys.exit(
                "Failed to find runners.yaml runfiles target:"
                f" {args.runners_yaml}"
            )

    return ztest_runner_core.run_ztest(
        binary_path=binary_path,
        runners_yaml_path=runners_yaml_path,
        serial_port=args.serial_port,
        baud_rate=args.baud_rate,
        serial_number=args.serial_number,
        stop_at=args.stop_at,
        success_signature=success_signature,
        xml_output_file=os.environ.get("XML_OUTPUT_FILE"),
    )


if __name__ == "__main__":
    sys.exit(main())
