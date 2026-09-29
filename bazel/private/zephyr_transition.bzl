# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Incoming transition for Zephyr applications."""

load("//bazel:naming.bzl", "get_zc_repo_name", "normalize_app_label", "parse_label")
load("@zephyr_index//:index.bzl", "PACKAGE_TO_BOARDS", "REPO_NAME_TO_CANONICAL", "SYSBUILD_CUSTOM_REPOS")

def _matches_board_base(target_name, b_base):
    """Checks if a user platform target name matches a candidate Zephyr board ID.

    Note: A target matching a board ID base is a necessary but insufficient
    condition for full resolution, as generic names (e.g. SoC 'nrf52840')
    can match multiple board IDs sharing that SoC.

    Supports:
      - Exact match (e.g. 'same70q21b' == 'same70q21b')
      - Underscore-sanitized match (e.g. 'nrf52840dk_nrf52840' == 'nrf52840dk/nrf52840')
      - Board family prefix match (e.g. 'nrf52840dk' matching 'nrf52840dk/nrf52840')
      - SoC / sub-variant suffix match (e.g. 'nrf52840' matching 'nrf52840dk/nrf52840')
    """
    if target_name == b_base:
        return True
    if b_base.replace("/", "_") == target_name:
        return True
    if b_base.endswith("/" + target_name):
        return True

    board_family, slash, variant = b_base.partition("/")
    if not slash:
        return False

    if target_name == board_family or target_name == variant:
        return True
    if variant.replace("/", "_") == target_name:
        return True
    return False

matches_board_base = _matches_board_base

def _parse_cand_board(b):
    """Parses a candidate board name into a struct(full_id, base, rev)."""
    base, sep, rev = b.partition("@")
    return struct(
        full_id = b,
        base = base,
        rev = rev if sep else None,
    )

parse_cand_board = _parse_cand_board

def _resolve_exact_revision(parsed_boards, target_name, label_rev):
    for p in parsed_boards:
        if p.rev == label_rev and _matches_board_base(target_name, p.base):
            return p.full_id
    return None

def _resolve_base_board(parsed_boards, target_name):
    unique_bases = []
    for p in parsed_boards:
        if p.base not in unique_bases:
            unique_bases.append(p.base)

    # 1. Default Shortcut
    if target_name == "default" and len(unique_bases) == 1:
        return unique_bases[0]

    # Pre-compute variant map
    variants_by_prefix = {}
    for p in parsed_boards:
        board_family, sep, _ = p.base.partition("/")
        if sep:
            variants_by_prefix.setdefault(board_family, []).append(p.base)

    # 2. Explicit Match (with default SoC resolution for HWM v2)
    for p in parsed_boards:
        if target_name == p.base:
            qualified_variants = variants_by_prefix.get(target_name, [])
            if qualified_variants:
                matching_main = [v for v in qualified_variants if v.split("/", 1)[1] == target_name]
                valid_variant_names = [v.split("/", 1)[1] for v in qualified_variants]
                if len(matching_main) == 0:
                    if len(qualified_variants) == 1:
                        return qualified_variants[0]
                    fail("Board family '%s' requires specifying an SoC variant. Valid variants: %s" %
                         (target_name, valid_variant_names))
                if len(matching_main) > 1:
                    fail("Board '%s' has multiple matching SoC variants: %s. Valid variants: %s" %
                         (target_name, matching_main, valid_variant_names))
                return matching_main[0]
            return p.base

    # 3. SoC/Variant Match (e.g. :nrf52833 for board nrf52833dk)
    for p in parsed_boards:
        if _matches_board_base(target_name, p.base):
            return p.base

    # 4. Fallback: if exactly one BASE board exists, assume it's board/soc
    base_boards = []
    for p in parsed_boards:
        if "/" not in p.base and p.base not in base_boards:
            base_boards.append(p.base)
    if len(base_boards) == 1:
        return base_boards[0] + "/" + target_name

    return None

def resolve_board_id(platform_label, pkg, pkg_boards, package_to_boards):
    """Resolves the Zephyr board ID from the platform label and context discovery index.

    Args:
        platform_label: The user requested platform label.
        pkg: The resolved package path.
        pkg_boards: Boards mapped to that package.
        package_to_boards: The global boards configuration index dict.

    Returns:
        The resolved board_id or None.
    """
    cand_label = _parse_cand_board(platform_label.name)
    target_name = cand_label.base
    label_rev = cand_label.rev

    candidates = [(pkg, pkg_boards)]
    prefix = pkg + "/"
    for sub_pkg, sub_pkg_boards in package_to_boards.items():
        if sub_pkg.startswith(prefix):
            candidates.append((sub_pkg, sub_pkg_boards))

    for cand_pkg, cand_boards in candidates:
        parsed_boards = [_parse_cand_board(b) for b in cand_boards]

        base_board_id = _resolve_base_board(parsed_boards, target_name)
        if base_board_id:
            resolved_id = base_board_id + ("@" + label_rev if label_rev else "")
            if not label_rev or any([p.full_id == resolved_id for p in parsed_boards]):
                return resolved_id

        if label_rev:
            exact = _resolve_exact_revision(parsed_boards, target_name, label_rev)
            if exact:
                return exact

    return None

def _zephyr_transition_impl(settings, attr):
    platforms = settings["//command_line_option:platforms"]
    if not platforms:
        return {}

    platform_label = platforms[0]

    # If already transitioned, do nothing.
    # Check both the old zc_ pattern and the new canonical Bzlmod pattern.
    platform_str = str(platform_label)
    if "zc_" in platform_str or "+zephyr_setup" in platform_str:
        return {}

    # Resolve package path as used in PACKAGE_TO_BOARDS
    target_info = parse_label(platform_label)
    pkg = None
    pkg_boards = None

    direct_pkg = str(platform_label).split(":")[0]
    if direct_pkg.startswith("//"):
        direct_pkg = "@@" + direct_pkg
    direct_pkg = direct_pkg.rstrip("/")
    if direct_pkg in PACKAGE_TO_BOARDS:
        pkg = direct_pkg
        pkg_boards = PACKAGE_TO_BOARDS[direct_pkg]
    else:
        for k, v in PACKAGE_TO_BOARDS.items():
            k_info = parse_label(k)
            if target_info.package == k_info.package or target_info.package.startswith(k_info.package + "/"):
                pkg = k
                pkg_boards = v
                break

    if pkg_boards == None:
        # This platform is not in a package that contains Zephyr boards.
        # Bypass the transition and let Bazel handle it.
        return {}

    board_id = resolve_board_id(platform_label, pkg, pkg_boards, PACKAGE_TO_BOARDS)

    if not board_id:
        fail("Unknown Zephyr board: %s. Valid boards in %s: %s" % (platform_label, pkg, pkg_boards))

    app_board_key = "%s:%s" % (normalize_app_label(attr.app_label), board_id)
    repo_name = SYSBUILD_CUSTOM_REPOS.get(app_board_key) or get_zc_repo_name(attr.app_label, board_id)
    canonical_repo = REPO_NAME_TO_CANONICAL.get(repo_name)
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

    toolchain_variant = settings["//toolchain:zephyr_toolchain_variant"]
    repo_clean = canonical_repo.lstrip("@")
    return {
        "//command_line_option:platforms": ["%s//:%s_platform_%s" % (canonical_repo, repo_clean, toolchain_variant)],
        "//command_line_option:compilation_mode": target_mode,
    }

zephyr_transition = transition(
    implementation = _zephyr_transition_impl,
    inputs = [
        "//command_line_option:platforms",
        "//command_line_option:compilation_mode",
        "//toolchain:zephyr_toolchain_variant",
    ],
    outputs = [
        "//command_line_option:platforms",
        "//command_line_option:compilation_mode",
    ],
)
