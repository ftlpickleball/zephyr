# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
from typing import NamedTuple


class ParsedBoardId(NamedTuple):
    board_name: str
    board_qualifiers: str
    board_revision: str


def parse_board_id(board_id: str) -> ParsedBoardId:
    """Splits a board_id string into ParsedBoardId(board_name, board_qualifiers, board_revision)."""
    # Isolate revision and its potential qualifiers from the board_name
    board_name, _, rev_and_qual = board_id.partition("@")
    board_revision, _, rev_qualifiers = rev_and_qual.partition("/")

    # Isolate qualifiers attached directly to board_name
    board_name, slash, name_qualifiers = board_name.partition("/")

    # Qualifiers from board_name overwrite qualifiers found in revision block
    board_qualifiers = name_qualifiers if slash else rev_qualifiers

    return ParsedBoardId(board_name, board_qualifiers, board_revision)


def get_app_board_override_candidates(
    board_name: str,
    board_qualifiers: str,
    board_revision: str,
    ext: str,
    sep: str = ".",
) -> list[str]:
    """Returns application boards/ override candidate filenames in precedence order.

    Order: base -> qualified -> revision -> qualified revision.
    """
    safe_q = board_qualifiers.lstrip("/").replace("/", "_")
    safe_rev = (board_revision or "").replace(".", "_")

    # Establish base prefixes (unqualified vs qualified)
    bases = [board_name]
    if safe_q:
        parts = board_qualifiers.lstrip("/").split("/")
        for i in range(len(parts)):
            q_sub = "_".join(parts[:i + 1])
            bases.append(f"{board_name}_{q_sub}")

    candidates = [f"{b}{sep}{ext}" for b in bases]

    # Extend the list, applying the Cartesian product of all suffixes to all the bases
    if safe_rev:
        suffixes = [f"_{safe_rev}"]
        if board_revision != safe_rev:
            suffixes.append(f"@{board_revision}")

        candidates.extend(f"{b}{s}{sep}{ext}" for b in bases for s in suffixes)

    return candidates


def get_board_revision_defconfigs(board_dir, board_name, board_qualifiers, board_revision):
    """Returns existing revision defconfig/conf paths in board_dir."""
    if not (board_dir and board_revision):
        return []

    board_qualifiers = board_qualifiers.lstrip("/")
    safe_q = board_qualifiers.replace("/", "_") if board_qualifiers else ""
    safe_rev = board_revision.replace(".", "_") if board_revision else ""

    raw_candidates = [
        os.path.join(board_dir, "revisions", f"{safe_rev}_defconfig"),
        os.path.join(board_dir, "revisions", f"{board_revision}_defconfig"),
        os.path.join(board_dir, f"{board_name}_{safe_rev}_defconfig"),
        os.path.join(board_dir, "revisions", f"{safe_rev}.conf"),
        os.path.join(board_dir, "revisions", f"{board_revision}.conf"),
    ]
    if safe_q:
        raw_candidates.append(os.path.join(board_dir, f"{board_name}_{safe_q}_{safe_rev}_defconfig"))

    conf_files = []
    for cand in raw_candidates:
        if os.path.exists(cand) and cand not in conf_files:
            conf_files.append(cand)
    return conf_files


def get_board_revision_overlays(board_dir, board_name, board_qualifiers, board_revision):
    """Returns existing revision overlay paths in board_dir."""
    if not (board_dir and board_revision):
        return []

    board_qualifiers = board_qualifiers.lstrip("/")
    safe_q = board_qualifiers.replace("/", "_") if board_qualifiers else ""
    safe_rev = board_revision.replace(".", "_") if board_revision else ""

    raw_candidates = [
        os.path.join(board_dir, "revisions", f"{safe_rev}.overlay"),
        os.path.join(board_dir, "revisions", f"{board_revision}.overlay"),
        os.path.join(board_dir, f"{board_name}_{safe_rev}.overlay"),
    ]
    if safe_q:
        raw_candidates.append(os.path.join(board_dir, f"{board_name}_{safe_q}_{safe_rev}.overlay"))

    overlays = []
    for cand in raw_candidates:
        if os.path.exists(cand) and cand not in overlays:
            overlays.append(cand)
    return overlays


def check_filesystem_overrides(app_path, board_id):
    """Checks if application's boards/ directory has config or overlay overrides for board."""
    boards_dir = os.path.join(app_path, "boards")
    if not os.path.isdir(boards_dir):
        return False

    board_name, board_qualifiers, board_revision = parse_board_id(board_id)

    candidates = get_app_board_override_candidates(
        board_name, board_qualifiers, board_revision, "conf"
    ) + get_app_board_override_candidates(
        board_name, board_qualifiers, board_revision, "overlay"
    )

    for c in candidates:
        if os.path.exists(os.path.join(boards_dir, c)):
            return True
    return False


def extract_board_revisions(board_dict: dict) -> list[str]:
    """Extracts a list of revision raw names from board dictionary in board.yml.

    Supports three Zephyr HWM v2 schema formats in priority order:
      1. revision (dict) -> revisions (list)
      2. revision (list)
      3. revisions (list)
    """
    rev_sec = board_dict.get("revision")
    revs = []
    if isinstance(rev_sec, dict):
        revs = rev_sec.get("revisions", [])
    elif isinstance(rev_sec, list):
        revs = rev_sec
    elif isinstance(board_dict.get("revisions"), list):
        revs = board_dict.get("revisions")

    result = []
    if isinstance(revs, list):
        for rev in revs:
            rn_raw = rev.get("name") if isinstance(rev, dict) else str(rev)
            if rn_raw:
                result.append(rn_raw)
    return result


    return False
