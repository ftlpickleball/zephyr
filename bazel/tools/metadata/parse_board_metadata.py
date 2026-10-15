# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
import argparse
import ast
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


def _is_toolchain_flag(flag):
    return flag.lstrip("-").endswith(
        ("//toolchain:zephyr_toolchain_variant", "//toolchain:compiler")
    )


def _extract_toolchain_from_flags(node):
    for subnode in ast.walk(node):
        if isinstance(subnode, ast.Dict):
            for k, v in zip(subnode.keys, subnode.values):
                if (
                    isinstance(k, ast.Constant)
                    and isinstance(k.value, str)
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                    and _is_toolchain_flag(k.value)
                ):
                    return v.value
        elif isinstance(subnode, (ast.List, ast.Tuple)):
            for elt in subnode.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    flag, sep, val = elt.value.partition("=")
                    if sep and _is_toolchain_flag(flag):
                        return val
    return None


def discover_toolchains_for_board(board_dir, bdata, deps):
    build_file = None
    for fname in ["BUILD.bazel", "BUILD"]:
        candidate = os.path.join(board_dir, fname)
        deps.add_file(candidate)
        if os.path.isfile(candidate):
            build_file = candidate
            break
    if not build_file:
        return {}

    try:
        with open(build_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=build_file)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse {build_file}: {e}\n")
        return {}

    target_toolchains = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "platform"
        ):
            kw = {
                k.arg: k.value
                for k in node.keywords
                if k.arg in ("name", "flags")
            }
            name_node = kw.get("name")
            flags_node = kw.get("flags")
            if (
                isinstance(name_node, ast.Constant)
                and isinstance(name_node.value, str)
                and flags_node is not None
            ):
                toolchain = _extract_toolchain_from_flags(flags_node)
                if toolchain:
                    target_toolchains[name_node.value] = toolchain

    if not target_toolchains:
        return {}

    board_toolchains = {}
    for entry in bdata.get("boards", [bdata]):
        board_name = entry.get("name", "")
        if not board_name:
            continue
        for q in entry.get("qualifiers", []):
            target = q.replace("/", "_")
            toolchain = (
                target_toolchains.get(target)
                or target_toolchains.get(f"{board_name}_{target}")
                or target_toolchains.get(board_name)
            )
            if toolchain:
                board_toolchains[f"{board_name}/{q}"] = toolchain
        if board_name in target_toolchains:
            board_toolchains[board_name] = target_toolchains[board_name]
    return board_toolchains


def main(argv=None):
    args = parse_args(argv)

    with open(args.boards_json, "r", encoding="utf-8") as f:
        boards_map = json.load(f)

    # The local module this script imports affects the output too.
    deps = input_recorder.InputRecorder(
        __file__, sys.modules[extract_board_revisions.__module__].__file__
    )

    revisions_result = {}
    board_toolchains = {}

    for board_dir, bdata in boards_map.items():
        revisions_result[board_dir] = discover_revisions_for_board(
            board_dir, deps
        )
        board_toolchains.update(
            discover_toolchains_for_board(board_dir, bdata, deps)
        )

    output = {
        "board_revisions": revisions_result,
        "board_toolchains": board_toolchains,
    }

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    deps.write(args.deps_out, args.dirs_out)


if __name__ == "__main__":
    main()
