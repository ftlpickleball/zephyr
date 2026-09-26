# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Public API for Zephyr Sysbuild in Bazel."""

load("@zephyr_index//:index.bzl", "SYSBUILD_METADATA")
load("//bazel:naming.bzl", "sanitize_board_id")
load("//bazel/private:transition_rule.bzl", "transitioned_dep")
load("//bazel/private:zephyr_transition.bzl", "zephyr_transition")

def _normalize_condition(cond):
    if not cond:
        return None
    if not cond.startswith("@") and not cond.startswith("//"):
        if not cond.startswith("CONFIG_"):
            cond = "CONFIG_" + cond
        if "=" not in cond:
            cond = cond + "=true"
        cond = "@zephyr_kconfig//:" + cond
    return cond

def zephyr_sysbuild(name, main, **kwargs):
    """Defines a multi-image Sysbuild target.

    Args:
        name: Target name.
        main: Label of the main Zephyr application.
        **kwargs: Additional arguments passed to the underlying rule.
    """
    testonly = kwargs.get("testonly", False)

    # Normalize main label to match index keys
    norm_main = str(main).split(":")[0]
    if "//" in norm_main:
        norm_main = norm_main.split("//")[-1]
    norm_main = norm_main.strip("/").lstrip(":")
    if not norm_main:
        norm_main = native.package_name()

    raw_meta = SYSBUILD_METADATA.get("raw_metadata", SYSBUILD_METADATA)
    metadata = raw_meta.get(norm_main, {"helpers": {}, "board_helpers": {}})

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
                testonly = testonly,
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
                testonly = testonly,
            )
            all_helpers_targets["%s:%s" % (board_id, helper_name)] = ":" + t_name

    # Build select() dictionary
    select_dict = {}

    # Global helpers
    base_helpers_map = {}
    conditional_global_helpers = {}
    for helper_name, helper_config in global_helpers.items():
        target = all_helpers_targets.get(helper_name)
        if not target:
            continue
        cond = helper_config.get("condition")
        if cond:
            normalized_cond = _normalize_condition(cond)
            if normalized_cond not in conditional_global_helpers:
                conditional_global_helpers[normalized_cond] = []
            conditional_global_helpers[normalized_cond].append(target)
        else:
            base_helpers_map[helper_name] = target

    select_dict["//conditions:default"] = list(base_helpers_map.values())

    for cond, targets in conditional_global_helpers.items():
        if cond in select_dict:
            for t in targets:
                if t not in select_dict[cond]:
                    select_dict[cond].append(t)
        else:
            select_dict[cond] = list(base_helpers_map.values()) + targets

    # Add board-specific helpers
    for board_id, helpers in board_helpers.items():
        custom_condition = None
        for helper_name, helper_config in helpers.items():
            if helper_config.get("condition"):
                custom_condition = _normalize_condition(helper_config["condition"])
                break

        if custom_condition:
            board_condition = custom_condition
        else:
            board_condition = "@zephyr_kconfig//:CONFIG_BOARD_%s=true" % sanitize_board_id(board_id).upper()

        current_board_helpers_map = dict(base_helpers_map)
        for helper_name in helpers.keys():
            target = all_helpers_targets.get("%s:%s" % (board_id, helper_name))
            if target:
                current_board_helpers_map[helper_name] = target

        if board_condition in select_dict:
            for t in current_board_helpers_map.values():
                if t not in select_dict[board_condition]:
                    select_dict[board_condition].append(t)
        else:
            select_dict[board_condition] = list(current_board_helpers_map.values())

    app_label = kwargs.pop("app_label", None)
    if not app_label:
        app_label = "//" + norm_main
    else:
        app_label = str(app_label)

    # Instantiate the underlying rule
    _zephyr_sysbuild_rule(
        name = name,
        app_label = app_label,
        main = main,
        helpers = select(select_dict),
        **kwargs
    )

def _zephyr_sysbuild_rule_impl(ctx):
    all_files = []
    all_files.extend(ctx.attr.main[DefaultInfo].files.to_list())
    for helper in ctx.attr.helpers:
        all_files.extend(helper[DefaultInfo].files.to_list())

    runfiles = ctx.runfiles()
    if ctx.attr.main[DefaultInfo].default_runfiles:
        runfiles = runfiles.merge(ctx.attr.main[DefaultInfo].default_runfiles)
    for helper in ctx.attr.helpers:
        if helper[DefaultInfo].default_runfiles:
            runfiles = runfiles.merge(helper[DefaultInfo].default_runfiles)

    output_groups = {}
    targets_with_og = []
    if OutputGroupInfo in ctx.attr.main:
        targets_with_og.append(ctx.attr.main)
    for helper in ctx.attr.helpers:
        if OutputGroupInfo in helper:
            targets_with_og.append(helper)

    for target in targets_with_og:
        og = target[OutputGroupInfo]
        for field in dir(og):
            if field.startswith("_"):
                continue
            val = getattr(og, field)
            if type(val) != "depset":
                continue
            if field not in output_groups:
                output_groups[field] = []
            output_groups[field].append(val)

    providers = [DefaultInfo(
        files = depset(all_files),
        runfiles = runfiles,
    )]
    if output_groups:
        merged_groups = {k: depset(transitive = v) for k, v in output_groups.items()}
        providers.append(OutputGroupInfo(**merged_groups))
    return providers

_zephyr_sysbuild_rule = rule(
    implementation = _zephyr_sysbuild_rule_impl,
    attrs = {
        "app_label": attr.string(mandatory = True),
        "main": attr.label(mandatory = True),
        "helpers": attr.label_list(),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    cfg = zephyr_transition,
)
