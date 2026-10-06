# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
import argparse
import json
import os
import sys

import input_recorder

try:
    import yaml
except ImportError:
    yaml = None

# Allow importing from bazel/tools/kconfig
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kconfig"))
from discovery_utils import extract_board_revisions


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--boards-json",
        required=True,
        help="Path to input JSON mapping board directory paths to metadata",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to write output JSON mapping board directory paths to revision lists",
    )
    input_recorder.add_arguments(parser)
    return parser.parse_args(argv)


# TODO(tbk): Determine if this can be cleanly merged with discover_board_variants.
def discover_revisions_for_board(board_dir, deps):
    revisions = []

    # 1. Parse board.yml / board.yaml
    if yaml is not None:
        for yml_name in ["board.yml", "board.yaml"]:
            yml_path = os.path.join(board_dir, yml_name)
            # Read if present; if missing, creating it would change the
            # result. Candidates after the first existing one are unused.
            deps.add_file(yml_path)
            if os.path.exists(yml_path):
                try:
                    with open(yml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        board_obj = data.get("board", data)
                        rev_list = extract_board_revisions(data)
                        if not rev_list and isinstance(board_obj, dict):
                            rev_list = extract_board_revisions(board_obj)
                        for r in rev_list:
                            if r and r not in revisions:
                                revisions.append(r)
                except Exception as e:
                    sys.stderr.write(f"Warning: Failed to parse {yml_path}: {e}\n")
                break

    # 2. Check revisions/ directory
    rev_dir = os.path.join(board_dir, "revisions")
    if os.path.isdir(rev_dir):
        # Only the file names matter, not their content.
        deps.add_dir(rev_dir)
        try:
            for fname in os.listdir(rev_dir):
                for suffix in ["_defconfig", ".conf", ".overlay"]:
                    if fname.endswith(suffix):
                        r_name = fname[:-len(suffix)]
                        if r_name and r_name not in revisions:
                            revisions.append(r_name)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to read {rev_dir}: {e}\n")
    else:
        # Creating revisions/ would add revisions.
        deps.add_file(rev_dir)

    return revisions


def main(argv=None):
    args = parse_args(argv)

    with open(args.boards_json, "r", encoding="utf-8") as f:
        boards_map = json.load(f)

    # The local module this script imports affects the output too.
    deps = input_recorder.InputRecorder(
        __file__, sys.modules[extract_board_revisions.__module__].__file__
    )

    result = {}
    for board_dir in boards_map.keys():
        result[board_dir] = discover_revisions_for_board(board_dir, deps)

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    deps.write(args.deps_out, args.dirs_out)


if __name__ == "__main__":
    main()
