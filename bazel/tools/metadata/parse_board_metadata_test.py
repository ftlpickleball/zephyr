# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import json
import os
import sys
import tempfile
import unittest

import input_recorder
import parse_board_metadata


class TestParseBoardMetadata(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_discover_revisions_from_yaml_format1(self):
        board_dir = os.path.join(self.tmp_dir.name, "board1")
        os.makedirs(board_dir)
        yaml_content = """
board:
  name: test_board
  revision:
    format: major.minor.patch
    revisions:
      - name: 1.0.0
        description: Initial release
      - name: 2.0.0
"""
        with open(os.path.join(board_dir, "board.yml"), "w", encoding="utf-8") as f:
            f.write(yaml_content)

        recorder = input_recorder.InputRecorder()
        revs = parse_board_metadata.discover_revisions_for_board(board_dir, recorder)
        self.assertEqual(revs, ["1.0.0", "2.0.0"])

    def test_discover_revisions_from_revisions_folder(self):
        board_dir = os.path.join(self.tmp_dir.name, "board2")
        rev_dir = os.path.join(board_dir, "revisions")
        os.makedirs(rev_dir)
        with open(os.path.join(rev_dir, "1_0_0.conf"), "w") as f:
            f.write("")
        with open(os.path.join(rev_dir, "2_0_0_defconfig"), "w") as f:
            f.write("")

        recorder = input_recorder.InputRecorder()
        revs = parse_board_metadata.discover_revisions_for_board(board_dir, recorder)
        self.assertEqual(sorted(revs), ["1_0_0", "2_0_0"])

    def test_discover_toolchains_from_build_bazel(self):
        board_dir = os.path.join(self.tmp_dir.name, "test_board")
        os.makedirs(board_dir)
        build_content = """
platform(
    name = "soc_a_cpu0",
    flags = flags_from_dict({
        "@zephyr//:soc": "@zephyr//soc/test",
    }) + [
        "--@zephyr//toolchain:zephyr_toolchain_variant=llvm",
    ],
)

platform(
    name = "soc_a_dsp",
    flags = flags_from_dict({
        "@zephyr//toolchain:compiler": "xt-clang",
    }),
)
"""
        with open(os.path.join(board_dir, "BUILD.bazel"), "w", encoding="utf-8") as f:
            f.write(build_content)

        recorder = input_recorder.InputRecorder()
        bdata = {"name": "test_board", "qualifiers": ["soc_a/cpu0", "soc_a/dsp"]}
        toolchains = parse_board_metadata.discover_toolchains_for_board(
            board_dir, bdata, recorder
        )
        self.assertEqual(
            toolchains,
            {
                "test_board/soc_a/cpu0": "llvm",
                "test_board/soc_a/dsp": "xt-clang",
            },
        )

    def test_discover_toolchains_multi_board_and_target_fallbacks(self):
        board_dir = os.path.join(self.tmp_dir.name, "multi_board")
        os.makedirs(board_dir)
        build_content = """
platform(
    name = "board_a_soc_a",
    flags = [
        "--@zephyr//toolchain:zephyr_toolchain_variant=llvm",
    ],
)

platform(
    name = "board_b",
    flags = [
        "--@zephyr//toolchain:zephyr_toolchain_variant=xt-clang",
    ],
)
"""
        with open(os.path.join(board_dir, "BUILD.bazel"), "w", encoding="utf-8") as f:
            f.write(build_content)

        recorder = input_recorder.InputRecorder()
        bdata = {
            "name": "board_a",
            "qualifiers": ["soc_a"],
            "boards": [
                {"name": "board_a", "qualifiers": ["soc_a"]},
                {"name": "board_b", "qualifiers": ["soc_b"]},
            ],
        }
        toolchains = parse_board_metadata.discover_toolchains_for_board(
            board_dir, bdata, recorder
        )
        self.assertEqual(
            toolchains,
            {
                "board_a/soc_a": "llvm",
                "board_b/soc_b": "xt-clang",
                "board_b": "xt-clang",
            },
        )


class TestParseBoardMetadataDeps(unittest.TestCase):
    """Tests for --deps-out / --dirs-out."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def write(self, rel_path, content=""):
        path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def discover(self, board):
        deps = input_recorder.InputRecorder()
        revs = parse_board_metadata.discover_revisions_for_board(
            os.path.join(self.root, board), deps
        )
        return revs, deps

    def test_board_yml_and_revisions_dir(self):
        self.write("b/board.yml", "board:\n  revision:\n    revisions:\n      - name: A\n")
        self.write("b/board.yaml", "board:\n  revisions: [Z]\n")  # shadowed
        self.write("b/revisions/B.conf")

        revs, deps = self.discover("b")

        self.assertEqual(revs, ["A", "B"])
        # board.yaml is never consulted once board.yml exists; the content of
        # revision files does not matter, only their names.
        self.assertEqual(deps.files, {os.path.join(self.root, "b", "board.yml")})
        self.assertEqual(deps.dirs, {os.path.join(self.root, "b", "revisions")})

    def test_board_yaml_fallback_and_missing_candidates(self):
        self.write("b/board.yaml", "board:\n  revisions: [Z]\n")

        revs, deps = self.discover("b")

        self.assertEqual(revs, ["Z"])
        self.assertEqual(
            deps.files,
            {
                # Missing: creating it would shadow board.yaml.
                os.path.join(self.root, "b", "board.yml"),
                os.path.join(self.root, "b", "board.yaml"),
                # Missing: creating it could add revisions.
                os.path.join(self.root, "b", "revisions"),
            },
        )
        self.assertEqual(deps.dirs, set())

    def test_main_deps_out(self):
        self.write("real/b1/board.yml", "board:\n  name: b1\n")
        os.makedirs(os.path.join(self.root, "real", "b2", "revisions"))
        os.symlink(
            os.path.join(self.root, "real"), os.path.join(self.root, "link")
        )
        boards_json = os.path.join(self.root, "boards.json")
        with open(boards_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    os.path.join(self.root, "link", "b2"): {},
                    os.path.join(self.root, "link", "b1"): {},
                    os.path.join(self.root, "real", "b1"): {},
                },
                f,
            )

        def run(*extra):
            output_json = os.path.join(self.root, "out.json")
            parse_board_metadata.main(
                ["--boards-json", boards_json, "--output-json", output_json]
                + list(extra)
            )
            with open(output_json, "rb") as f:
                return f.read()

        out_without = run()
        deps_out = os.path.join(self.root, "deps.txt")
        dirs_out = os.path.join(self.root, "dirs.txt")
        self.assertFalse(os.path.exists(deps_out))
        out_with = run("--deps-out", deps_out, "--dirs-out", dirs_out)
        self.assertEqual(out_with, out_without)

        real = os.path.join(self.root, "real")
        with open(deps_out, encoding="utf-8") as f:
            self.assertEqual(
                f.read(),
                "".join(
                    p + "\n"
                    for p in sorted([
                        os.path.realpath(parse_board_metadata.__file__),
                        os.path.realpath(input_recorder.__file__),
                        os.path.realpath(
                            sys.modules[
                                parse_board_metadata.extract_board_revisions.__module__
                            ].__file__
                        ),
                        os.path.join(real, "b1", "BUILD.bazel"),
                        os.path.join(real, "b1", "BUILD"),
                        os.path.join(real, "b1", "board.yml"),
                        os.path.join(real, "b1", "revisions"),
                        os.path.join(real, "b2", "BUILD.bazel"),
                        os.path.join(real, "b2", "BUILD"),
                        os.path.join(real, "b2", "board.yml"),
                        os.path.join(real, "b2", "board.yaml"),
                    ])
                ),
            )
        with open(dirs_out, encoding="utf-8") as f:
            self.assertEqual(f.read(), os.path.join(real, "b2", "revisions") + "\n")


if __name__ == "__main__":
    unittest.main()
