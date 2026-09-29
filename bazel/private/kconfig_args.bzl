# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Helper functions for setting up args to zephyr kconfig parsing."""

load("//bazel/private:deps.bzl", "label_path")

def resolve_module_roots(tracker, modules):
    """Resolves the absolute paths of the module roots.

    Same semantics as `resolve_module_roots()` in naming.bzl, but resolves each repository once
    through the tracker instead of watching every module label.

    Args:
        tracker: The dict returned by deps.bzl's new_tracker().
        modules: A list of {"original": <canonical label>, "relpath": <path>} dicts, in the order of
            the discovery state (auto-linked modules first, then config-only ones).

    Returns:
        A list of unique path strings.
    """
    resolved_modules = []
    for m_info in modules:
        m_label_str = m_info.get("original")
        if not m_label_str:
            continue
        m_path = label_path(tracker, m_label_str)
        if m_path.basename == "module.yml" and m_path.dirname.basename == "zephyr":
            mod_root = m_path.dirname.dirname
        else:
            mod_root = m_path.dirname

        relpath = m_info.get("relpath")
        if relpath:
            mod_root = mod_root.get_child(relpath)

        path_str = str(mod_root)
        if path_str not in resolved_modules:
            resolved_modules.append(path_str)
    return resolved_modules

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
