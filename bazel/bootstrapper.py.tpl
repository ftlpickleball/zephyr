#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys

def main():
    exec_dir = os.path.dirname(sys.argv[0])
    runfiles_dir = os.path.join(exec_dir, "{app_name}.runfiles")
    if "RUNFILES_DIR" in os.environ:
        runfiles_dir = os.environ["RUNFILES_DIR"]

    yaml_path = "{runners_yaml}"
    binary_path = "{binary}"
    flash_bin_path = "{flash_bin}"

    abs_yaml = os.path.join(runfiles_dir, yaml_path)
    abs_binary = os.path.join(runfiles_dir, binary_path)
    abs_flash_bin = os.path.join(runfiles_dir, flash_bin_path)

    if abs_flash_bin and os.path.exists(abs_flash_bin):
        os.execv(abs_flash_bin, [abs_flash_bin, "--yaml", abs_yaml, "--binary", abs_binary] + sys.argv[1:])
    else:
        print(f"Failed to locate flashing tool in runfiles: {abs_flash_bin}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
