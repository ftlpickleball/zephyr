# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Zephyr board transition and matching functions."""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//bazel:naming.bzl", "find_package_boards", "get_zc_repo_name", "matches_board_base", "parse_cand_board", "parse_label", "resolve_board_id")
load("//bazel/private:zephyr_transition.bzl", "zephyr_transition_impl")

def _parse_cand_board_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.equals(env, struct(full_id = "nrf52840dk", base = "nrf52840dk", rev = None), parse_cand_board("nrf52840dk"))
    asserts.equals(env, struct(full_id = "nrf52840dk@1.0.0", base = "nrf52840dk", rev = "1.0.0"), parse_cand_board("nrf52840dk@1.0.0"))
    return unittest.end(env)

def _parse_label_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        struct(canonical_repo = "@@", apparent_repo = "", package = "boards/nordic/nrf52840dk", name = "nrf52840"),
        parse_label("//boards/nordic/nrf52840dk:nrf52840"),
    )
    asserts.equals(
        env,
        struct(canonical_repo = "@@+module+ext_repo", apparent_repo = "ext_repo", package = "boards/custom", name = "custom"),
        parse_label("@@+module+ext_repo//boards/custom"),
    )
    return unittest.end(env)

def _find_package_boards_test_impl(ctx):
    env = unittest.begin(ctx)
    pkg_map = {
        "boards/nordic": ["parent_board"],
        "boards/nordic/nrf5340dk": ["nrf5340dk/nrf5340/cpuapp", "nrf5340dk/nrf5340/cpunet"],
        "@other_repo//boards/nordic/nrf5340dk": ["other_board"],
    }
    asserts.equals(
        env,
        ("boards/nordic/nrf5340dk", ["nrf5340dk/nrf5340/cpuapp", "nrf5340dk/nrf5340/cpunet"]),
        find_package_boards("//boards/nordic/nrf5340dk:nrf5340_cpuapp", pkg_map),
    )
    asserts.equals(
        env,
        ("@other_repo//boards/nordic/nrf5340dk", ["other_board"]),
        find_package_boards("@@+module+other_repo//boards/nordic/nrf5340dk:other_board", pkg_map),
    )
    return unittest.end(env)

def _resolve_board_id_test_impl(ctx):
    env = unittest.begin(ctx)
    mock_pkg_boards = ["nrf52840dk/nrf52840", "nrf52840dk/nrf52840@1.0.0", "same70q21b"]
    mock_pkg_map = {"boards/nordic/nrf52840dk": mock_pkg_boards}

    # Exact revision match
    struct_label_rev = struct(name = "nrf52840dk@1.0.0")
    asserts.equals(
        env,
        "nrf52840dk/nrf52840@1.0.0",
        resolve_board_id(struct_label_rev, "boards/nordic/nrf52840dk", mock_pkg_boards, mock_pkg_map),
    )

    # Base board match
    struct_label_base = struct(name = "same70q21b")
    asserts.equals(
        env,
        "same70q21b",
        resolve_board_id(struct_label_base, "boards/nordic/nrf52840dk", mock_pkg_boards, mock_pkg_map),
    )

    # Default shortcut with revisions present
    mock_single_with_rev = ["my_board", "my_board@1.0.0"]
    mock_single_map = {"boards/my_board": mock_single_with_rev}
    struct_label_default = struct(name = "default")
    asserts.equals(
        env,
        "my_board",
        resolve_board_id(struct_label_default, "boards/my_board", mock_single_with_rev, mock_single_map),
    )

    # Single-board fallback with revisions present
    mock_soc_with_rev = ["my_board/my_soc", "my_board/my_soc@1.0.0"]
    mock_soc_map = {"boards/my_board": mock_soc_with_rev}
    struct_label_soc = struct(name = "my_soc")
    asserts.equals(
        env,
        "my_board/my_soc",
        resolve_board_id(struct_label_soc, "boards/my_board", mock_soc_with_rev, mock_soc_map),
    )

    return unittest.end(env)

def _matches_board_base_test_impl(ctx):
    env = unittest.begin(ctx)

    # Exact match
    asserts.true(env, matches_board_base("same70q21b", "same70q21b"))
    asserts.false(env, matches_board_base("same70q21b", "other_board"))

    # Underscore-sanitized match
    asserts.true(env, matches_board_base("nrf52840dk_nrf52840", "nrf52840dk/nrf52840"))

    # Board family prefix match
    asserts.true(env, matches_board_base("nrf52840dk", "nrf52840dk/nrf52840"))

    # SoC / sub-variant suffix match
    asserts.true(env, matches_board_base("nrf52840", "nrf52840dk/nrf52840"))

    # Multi-level variant matching
    asserts.true(env, matches_board_base("cpuapp", "nrf5340dk/nrf5340/cpuapp"))
    asserts.true(env, matches_board_base("nrf5340_cpuapp", "nrf5340dk/nrf5340/cpuapp"))

    # Negative cases
    asserts.false(env, matches_board_base("nrf52833", "nrf52840dk/nrf52840"))
    asserts.false(env, matches_board_base("dk", "nrf52840dk/nrf52840"))

    return unittest.end(env)

def _zephyr_transition_board_toolchains_test_impl(ctx):
    env = unittest.begin(ctx)
    board_toolchains = {
        "esp32s3_devkitc_esp32s3_procpu": "xt-clang",
    }
    repo_name = get_zc_repo_name("//samples/hello_world:hello_world", "esp32s3_devkitc/esp32s3/procpu")
    canonical_repo = "@@+zephyr_setup_apps+" + repo_name
    top_level_settings = {
        "//command_line_option:platforms": [Label("//boards/espressif/esp32s3_devkitc:esp32s3_procpu")],
        "//command_line_option:compilation_mode": "fastbuild",
        "//toolchain:zephyr_toolchain_variant": "gcc",
        "//bazel:sysbuild_context": "",
    }
    res_top = zephyr_transition_impl(
        top_level_settings,
        struct(app_label = "//samples/hello_world:hello_world"),
        package_to_boards = {"boards/espressif/esp32s3_devkitc": ["esp32s3_devkitc/esp32s3/procpu"]},
        repo_name_to_canonical = {repo_name: canonical_repo},
        sysbuild_custom_repos = {},
        board_toolchains = board_toolchains,
    )
    asserts.equals(
        env,
        ["%s//:%s_platform_xt-clang" % (canonical_repo, canonical_repo.lstrip("@"))],
        res_top["//command_line_option:platforms"],
    )

    parent_repo_name = get_zc_repo_name("//samples/sysbuild/main_app:main_app", "esp32s3_devkitc/esp32s3/procpu")
    zc_settings = {
        "//command_line_option:platforms": [
            "@@+zephyr_setup_apps+%s//:zc_target_platform_xt-clang" % parent_repo_name,
        ],
        "//command_line_option:compilation_mode": "fastbuild",
        "//toolchain:zephyr_toolchain_variant": "gcc",
        "//bazel:sysbuild_context": "samples/sysbuild/main_app:helper_app",
    }
    res_zc = zephyr_transition_impl(
        zc_settings,
        struct(app_label = "//samples/hello_world:hello_world"),
        package_to_boards = {},
        repo_name_to_canonical = {repo_name: canonical_repo},
        sysbuild_custom_repos = {},
        board_toolchains = board_toolchains,
    )
    asserts.equals(
        env,
        ["%s//:%s_platform_xt-clang" % (canonical_repo, canonical_repo.lstrip("@"))],
        res_zc["//command_line_option:platforms"],
    )
    return unittest.end(env)

parse_cand_board_test = unittest.make(_parse_cand_board_test_impl)
parse_label_test = unittest.make(_parse_label_test_impl)
find_package_boards_test = unittest.make(_find_package_boards_test_impl)
resolve_board_id_test = unittest.make(_resolve_board_id_test_impl)
matches_board_base_test = unittest.make(_matches_board_base_test_impl)
zephyr_transition_board_toolchains_test = unittest.make(_zephyr_transition_board_toolchains_test_impl)

def zephyr_transition_test_suite(name = "zephyr_transition_test_suite"):
    unittest.suite(
        name,
        parse_cand_board_test,
        parse_label_test,
        find_package_boards_test,
        resolve_board_id_test,
        matches_board_base_test,
        zephyr_transition_board_toolchains_test,
    )
