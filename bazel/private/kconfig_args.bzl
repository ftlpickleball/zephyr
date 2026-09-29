# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Helper functions for setting up args to zephyr kconfig parsing."""

def get_kconfig_args(
        script,
        zephyr_root,
        modules = [],
        output = None,
        output_dir = None,
        app_dir = None,
        board = None,
        board_dir = None,
        parent_platform = None,
        app_name = None,
        board_dirs = [],
        oot_dts_roots = [],
        conf_fragments = [],
        dtc_overlays = []):
    args = [
        str(script),
        "--zephyr-base",
        zephyr_root,
    ]
    if output:
        args.extend(["--output", output])
    if output_dir:
        args.extend(["--output-dir", output_dir])
    if app_dir:
        args.extend(["--app-dir", app_dir])
    if board:
        args.extend(["--board", board])
    if board_dir:
        args.extend(["--board-dir", board_dir])
    if parent_platform:
        args.extend(["--parent-platform", str(parent_platform)])
    if app_name:
        args.extend(["--app-name", app_name])

    if board_dirs:
        args.append("--board-dirs")
        args.extend(board_dirs)

    if modules:
        args.append("--modules")
        args.extend(modules)

    if oot_dts_roots:
        args.append("--oot-dts-roots")
        args.extend(oot_dts_roots)

    if conf_fragments:
        args.append("--conf-fragments")
        args.extend(conf_fragments)

    if dtc_overlays:
        args.append("--dtc-overlays")
        args.extend(dtc_overlays)

    return args
