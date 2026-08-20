# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Public API for Zephyr Sysbuild in Bazel."""

load("@zephyr_index//:index.bzl", "SYSBUILD_METADATA")
load("//bazel/private:transition_rule.bzl", "transitioned_dep")

def zephyr_sysbuild(name, main, **kwargs):
    """Defines a multi-image Sysbuild target.

    Args:
        name: Target name.
        main: Label of the main Zephyr application.
        **kwargs: Additional arguments passed to the underlying rule.
    """

    # Normalize main label to match index keys
    norm_main = str(main).split(":")[0]
    if "//" in norm_main:
        norm_main = norm_main.split("//")[-1]
    norm_main = norm_main.strip("/").lstrip(":")

    metadata = SYSBUILD_METADATA.get(norm_main, {"helpers": {}, "board_helpers": {}})

    global_helpers = metadata.get("helpers", {})
    board_helpers = metadata.get("board_helpers", {})

    # Instantiate targets for all possible helpers
    all_helpers_targets = {}

    # Helper for global helpers
    for helper_name, helper_config in global_helpers.items():
        helper_target = helper_config.get("target")
        if not helper_target:
            continue

        platform = helper_config.get("platform")
        if platform:
            t_name = "%s_helper_%s" % (name, helper_name)
            transitioned_dep(
                name = t_name,
                dep = helper_target,
                platform = platform,
            )
            all_helpers_targets[helper_name] = ":" + t_name
        else:
            all_helpers_targets[helper_name] = helper_target

    # Helper for board-specific helpers
    for board_id, helpers in board_helpers.items():
        for helper_name, helper_config in helpers.items():
            helper_target = helper_config.get("target")
            if not helper_target:
                continue

            # When platform is not specified, it is None so the helper domain
            # inherits the platform attribute from the parent domain.
            platform = helper_config.get("platform")
            t_name = "%s_helper_%s_%s" % (name, helper_name, sanitize_board_id(board_id))
            transitioned_dep(
                name = t_name,
                dep = helper_target,
                platform = platform,
            )
            all_helpers_targets["%s:%s" % (board_id, helper_name)] = ":" + t_name

    # Build select() dictionary
    select_dict = {}

    # Global helpers are always included
    base_helpers = []
    for helper_name in global_helpers.keys():
        target = all_helpers_targets.get(helper_name)
        if target:
            base_helpers.append(target)

    select_dict["//conditions:default"] = base_helpers

    # Add board-specific helpers
    for board_id, helpers in board_helpers.items():
        board_condition = "@zephyr_kconfig//:CONFIG_BOARD_%s=true" % board_id.upper()

        current_board_helpers = list(base_helpers)
        for helper_name in helpers.keys():
            target = all_helpers_targets.get("%s:%s" % (board_id, helper_name))
            if target:
                current_board_helpers.append(target)

        select_dict[board_condition] = current_board_helpers

    # Instantiate the underlying rule
    _zephyr_sysbuild_rule(
        name = name,
        main = main,
        helpers = select(select_dict),
        **kwargs
    )

def sanitize_board_id(board_id):
    return board_id.replace("/", "_").replace("-", "_").replace(".", "_")

def _zephyr_sysbuild_rule_impl(ctx):
    all_files = []
    all_files.extend(ctx.attr.main[DefaultInfo].files.to_list())
    for helper in ctx.attr.helpers:
        all_files.extend(helper[DefaultInfo].files.to_list())

    return [DefaultInfo(files = depset(all_files))]

_zephyr_sysbuild_rule = rule(
    implementation = _zephyr_sysbuild_rule_impl,
    attrs = {
        "main": attr.label(mandatory = True),
        "helpers": attr.label_list(),
    },
)
