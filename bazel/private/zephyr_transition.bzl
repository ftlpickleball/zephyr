# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Incoming transition for Zephyr applications."""

load("@zephyr_index//:index.bzl", "BOARD_TOOLCHAINS", "PACKAGE_TO_BOARDS", "REPO_NAME_TO_CANONICAL", "SYSBUILD_CUSTOM_REPOS")
load(
    "//bazel:naming.bzl",
    "find_package_boards",
    "get_zc_repo_name",
    "resolve_board_id",
    "sanitize_board_id",
)

def extract_safe_board_from_zc_platform(platform_str):
    """Extracts the sanitized board ID from a zc_<hash>_<safe_board> platform label string."""
    marker = "zc_"
    idx = platform_str.find(marker)
    if idx == -1:
        return None
    rest = platform_str[idx + len(marker):]
    if "//" in rest:
        rest = rest.split("//", 1)[0]
    if len(rest) > 9 and rest[8] == "_":
        return rest[9:]
    return None

def resolve_platform_board_id(platform_label):
    """Resolves the Zephyr board_id from a platform label using PACKAGE_TO_BOARDS."""
    pkg, pkg_boards = find_package_boards(platform_label, PACKAGE_TO_BOARDS)
    if pkg_boards == None:
        return None
    return resolve_board_id(platform_label, pkg, pkg_boards, PACKAGE_TO_BOARDS)

def zephyr_transition_impl(
        settings,
        attr,
        package_to_boards = PACKAGE_TO_BOARDS,
        repo_name_to_canonical = REPO_NAME_TO_CANONICAL,
        sysbuild_custom_repos = SYSBUILD_CUSTOM_REPOS,
        board_toolchains = BOARD_TOOLCHAINS):
    """Implementation of the incoming Zephyr configuration transition."""
    platforms = settings["//command_line_option:platforms"]
    if not platforms:
        return {}

    platform_label = platforms[0]
    platform_str = str(platform_label)
    sysbuild_ctx = settings["//bazel:sysbuild_context"]

    # If already transitioned, only re-transition when entering a sysbuild helper
    # domain that inherited the parent domain's platform.
    if "zc_" in platform_str or "+zephyr_setup" in platform_str:
        if not sysbuild_ctx:
            return {}
        board_id = extract_safe_board_from_zc_platform(platform_str)
        if not board_id:
            return {}
    else:
        pkg, pkg_boards = find_package_boards(platform_label, package_to_boards)
        if pkg_boards == None:
            # This platform is not in a package that contains Zephyr boards.
            # Bypass the transition and let Bazel handle it.
            return {}

        board_id = resolve_board_id(platform_label, pkg, pkg_boards, package_to_boards)

        if not board_id:
            fail("Unknown Zephyr board: %s. Valid boards in %s: %s" % (platform_label, pkg, pkg_boards))

    repo_name = None
    if sysbuild_ctx:
        custom_key = "%s:%s" % (sysbuild_ctx, sanitize_board_id(board_id))
        repo_name = sysbuild_custom_repos.get(custom_key)
    if not repo_name:
        repo_name = get_zc_repo_name(attr.app_label, board_id)
    canonical_repo = repo_name_to_canonical.get(repo_name)
    if not canonical_repo:
        fail("""
Board combination '%s' for app '%s' was filtered out by heuristics.
To fix this, you can either:
  1. Add a .conf or .overlay file for this board under the 'boards/' directory of the app.
  2. Add the board to the 'manual_boards' attribute of 'zephyr_setup.env' in MODULE.bazel
""" % (board_id, attr.app_label))

    # Allow the user to override compilation mode for hardware debugging.
    # If they explicitly passed '-c dbg', compile in debug mode. Otherwise,
    # default to 'opt' to enable function inlining and prevent stack overflows.
    incoming_mode = settings["//command_line_option:compilation_mode"]
    target_mode = "opt"
    if incoming_mode == "dbg":
        target_mode = "dbg"

    toolchain_variant = board_toolchains.get(
        sanitize_board_id(board_id),
        settings["//toolchain:zephyr_toolchain_variant"],
    )
    repo_clean = canonical_repo.lstrip("@")
    return {
        "//command_line_option:platforms": ["%s//:%s_platform_%s" % (canonical_repo, repo_clean, toolchain_variant)],
        "//command_line_option:compilation_mode": target_mode,
        "//bazel:sysbuild_context": "",
    }

zephyr_transition = transition(
    implementation = zephyr_transition_impl,
    inputs = [
        "//command_line_option:platforms",
        "//command_line_option:compilation_mode",
        "//toolchain:zephyr_toolchain_variant",
        "//bazel:sysbuild_context",
    ],
    outputs = [
        "//command_line_option:platforms",
        "//command_line_option:compilation_mode",
        "//bazel:sysbuild_context",
    ],
)
