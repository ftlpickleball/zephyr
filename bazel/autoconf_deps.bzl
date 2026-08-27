# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//bazel:cc.bzl", "zephyr_cc_library")

def autoconf_deps(board, configs_repo, **kwargs):
    """
    A macro that declares common autoconf-derived components a build needs.

    Args:
        board: The name of the board, e.g. "robokit1" or "nrf52833dk/nrf52833".
        configs_repo: The name of the repository containing generated autoconf.
        **kwargs: Other args.

    Returns:
        A dictionary of zephyr-bazel flags to be used in platform definition.
    """
    board_name = board.replace("/", "_")
    native.filegroup(
        name = board_name + "_autoconf_file",
        srcs = [configs_repo + "//:generated/zephyr/autoconf.h"],
    )
    cc_library(
        name = board_name + "_autoconf",
        defines = [
            # Extra CONFIGs that we should clean up some day.
            "CONFIG_PIGWEED_SYS_IO_INIT_PRIORITY=1",
            "CONFIG_PIGWEED_THREAD_DEFAULT_PRIORITY=0",
            "CONFIG_PIGWEED_THREAD_NUM_COOP_PRIORITIES=16",
            "CONFIG_PIGWEED_THREAD_NUM_PREEMPT_PRIORITIES=15",
            "CONFIG_PIGWEED_THREAD_MAX_THREAD_NAME_LEN=32",
            "CONFIG_PIGWEED_THREAD_MINIMUM_STACK_SIZE=128",
            "CONFIG_PIGWEED_THREAD_DEFAULT_STACK_SIZE=1024",
        ],
        deps = [configs_repo + "//:autoconf"],
    )

    zephyr_cc_library(
        name = board_name + "_autoconf_symbols_to_link",
        srcs = [configs_repo + "//:configs_file"],
    )

    native.alias(
        name = board_name + "_autoconf_dir",
        actual = configs_repo + Label("//:autoconf_dir"),
    )

    flags = {
        Label("//:autoconf_file"): ":" + board_name + "_autoconf_file",
        Label("//:autoconf_dir"): ":" + board_name + "_autoconf_dir",
        Label("//:autoconf_library"): ":" + board_name + "_autoconf",
        Label("//:autoconf_symbols_to_link"): ":" + board_name + "_autoconf_symbols_to_link",
    }

    overlay_file = "boards/" + board_name + ".overlay"
    if native.glob([overlay_file], allow_empty = True):
        native.filegroup(
            name = board_name + "_extra_dts_overlays",
            srcs = [overlay_file],
        )
        flags[Label("//:extra_dts_overlays")] = ":" + board_name + "_extra_dts_overlays"

    return flags
