# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Lists the inputs of scripts/list_boards.py for the given hardware roots.

list_boards.py (via list_hardware.py) discovers boards by globbing `<board-root>/boards/**/board.yml`,
SoCs by globbing `<soc-root>/soc/**/soc.yml`, and architectures from `<arch-root>/arch/archs.yml`,
and validates them against the schemas next to the scripts. This script reports those inputs so that
the module extension running list_boards.py can watch them:

*   --deps-out: every file list_boards.py reads, plus the missing `boards`/`soc` directories and
    `archs.yml` files whose creation would change its output. One realpath per line, sorted.
*   --dirs-out: every directory the globs list. Same format.
"""

import argparse
import os
import sys

import input_recorder


BOARD_YML = "board.yml"
SOC_YML = "soc.yml"
ARCHS_YML = os.path.join("arch", "archs.yml")
SCRIPT_INPUTS = [
    "list_boards.py",
    "list_hardware.py",
    os.path.join("schemas", "board-schema.yaml"),
    os.path.join("schemas", "soc-schema.yaml"),
    os.path.join("schemas", "arch-schema.yaml"),
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scripts-dir",
        required=True,
        help="Directory containing list_boards.py (zephyr's scripts/)",
    )
    parser.add_argument("--board-root", action="append", default=[])
    parser.add_argument("--soc-root", action="append", default=[])
    parser.add_argument("--arch-root", action="append", default=[])
    input_recorder.add_arguments(parser)
    return parser.parse_args(argv)


def _walk(top, name, recorder):
    """Records what `Path(top).rglob(name)` depends on.

    Like pathlib's recursive glob (before Python 3.13), symlinked directories are not followed.
    """
    if not os.path.isdir(top):
        recorder.add_file(top)
        return
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        recorder.add_dir(dirpath)
        if name in filenames:
            recorder.add_file(os.path.join(dirpath, name))
        # os.walk() lists symlinks to directories in dirnames without descending into them.
        dirnames.sort()


def collect(scripts_dir, board_roots, soc_roots, arch_roots, recorder=None):
    """Records inputs into `recorder` and returns `(deps, dirs)` sets of realpaths."""
    if recorder is None:
        recorder = input_recorder.InputRecorder()
    for rel in SCRIPT_INPUTS:
        recorder.add_file(os.path.join(scripts_dir, rel))
    for root in board_roots:
        _walk(os.path.join(root, "boards"), BOARD_YML, recorder)
    for root in soc_roots:
        _walk(os.path.join(root, "soc"), SOC_YML, recorder)
    for root in arch_roots:
        recorder.add_file(os.path.join(root, ARCHS_YML))
    return recorder.files, recorder.dirs


def main(argv=None):
    args = parse_args(argv)
    recorder = input_recorder.InputRecorder(__file__)
    collect(
        args.scripts_dir,
        args.board_root,
        args.soc_root,
        args.arch_root,
        recorder=recorder,
    )
    recorder.write(args.deps_out, args.dirs_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
