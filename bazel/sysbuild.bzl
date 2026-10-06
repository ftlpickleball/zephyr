# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Public API for Zephyr Sysbuild in Bazel."""

load("@zephyr_index//:index.bzl", "SYSBUILD_METADATA")
load("//bazel:naming.bzl", "sanitize_board_id")
load("//bazel:runfiles.bzl", "resolve_runfiles_path")
load("//bazel/private:transition_rule.bzl", "SysbuildHelperInfo", "transitioned_dep")
load(
    "//bazel/private:zephyr_transition.bzl",
    "extract_safe_board_from_zc_platform",
    "resolve_platform_board_id",
)

# NOTE: _zephyr_sysbuild_transition intentionally only sets //bazel:sysbuild_board
# and does NOT transition //command_line_option:platforms to the main app's @zc_
# platform. In Bazel, platform flags (--@zephyr_kconfig//:CONFIG_*=true) are
# additive across transitions; transitioning the parent sysbuild target to the
# main app's @zc_ platform would leak the main domain's Kconfig flags into all
# child helper domains.
def _zephyr_sysbuild_transition_impl(settings, attr):
    platforms = settings["//command_line_option:platforms"]
    if not platforms:
        return {}
    board_id = resolve_platform_board_id(platforms[0])
    if board_id:
        safe_board = sanitize_board_id(board_id)
        if safe_board not in attr.board_helper_keys and "@" in board_id:
            base_safe = sanitize_board_id(board_id.split("@")[0])
            if base_safe in attr.board_helper_keys:
                safe_board = base_safe
    else:
        safe_board = extract_safe_board_from_zc_platform(str(platforms[0]))
    if not safe_board:
        return {}
    return {
        "//bazel:sysbuild_board": safe_board,
    }

_zephyr_sysbuild_transition = transition(
    implementation = _zephyr_sysbuild_transition_impl,
    inputs = ["//command_line_option:platforms"],
    outputs = ["//bazel:sysbuild_board"],
)

def zephyr_sysbuild(name, main, **kwargs):
    """Defines a multi-image Sysbuild target.

    Args:
        name: Target name.
        main: Label of the main Zephyr application.
        **kwargs: Additional arguments passed to the underlying rule.
    """
    testonly = kwargs.get("testonly", False)
    kwargs.pop("app_label", None)

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

        t_name = "%s_helper_%s" % (name, helper_name)
        transitioned_dep(
            name = t_name,
            dep = helper_target,
            platform = helper_config.get("platform"),
            sysbuild_context = "%s:%s" % (norm_main, helper_name),
            testonly = testonly,
        )
        all_helpers_targets[helper_name] = ":" + t_name

    # Helper for board-specific helpers
    for board_id, helpers in board_helpers.items():
        for helper_name, helper_config in helpers.items():
            helper_target = helper_config.get("target")
            if not helper_target:
                continue

            # When platform is not specified, it is None so the helper domain
            # inherits the platform attribute from the parent domain.
            t_name = "%s_helper_%s_%s" % (name, helper_name, sanitize_board_id(board_id))
            transitioned_dep(
                name = t_name,
                dep = helper_target,
                platform = helper_config.get("platform"),
                sysbuild_context = "%s:%s" % (norm_main, helper_name),
                testonly = testonly,
            )
            all_helpers_targets["%s:%s" % (board_id, helper_name)] = ":" + t_name

    # Build helpers expression
    base_helpers_map = {}
    for helper_name in global_helpers.keys():
        target = all_helpers_targets.get(helper_name)
        if target:
            base_helpers_map[helper_name] = target

    board_select_dict = {
        "//conditions:default": list(base_helpers_map.values()),
    }

    # Add board-specific helpers
    board_helper_keys = []
    for board_id, helpers in board_helpers.items():
        safe_board = sanitize_board_id(board_id)
        if safe_board not in board_helper_keys:
            board_helper_keys.append(safe_board)
        cond_name = "%s_board_%s" % (name, safe_board)
        if not native.existing_rule(cond_name):
            native.config_setting(
                name = cond_name,
                flag_values = {
                    Label("//bazel:sysbuild_board"): safe_board,
                },
            )
        board_condition = ":" + cond_name

        current_board_helpers_map = dict(base_helpers_map)
        for helper_name in helpers.keys():
            target = all_helpers_targets.get("%s:%s" % (board_id, helper_name))
            if target:
                current_board_helpers_map[helper_name] = target

        if board_condition in board_select_dict:
            for t in current_board_helpers_map.values():
                if t not in board_select_dict[board_condition]:
                    board_select_dict[board_condition].append(t)
        else:
            board_select_dict[board_condition] = list(current_board_helpers_map.values())

    # Instantiate the underlying rule
    _zephyr_sysbuild_rule(
        name = name,
        board_helper_keys = board_helper_keys,
        main = main,
        helpers = select(board_select_dict),
        **kwargs
    )

def _add_domain_symlinks(ctx, domain_id, exec_file, domain_rf, root_symlinks):
    prefix = "_domain_%s/" % domain_id
    if exec_file:
        root_symlinks[prefix + resolve_runfiles_path(ctx, exec_file)] = exec_file
    if domain_rf:
        for f in domain_rf.files.to_list():
            root_symlinks[prefix + resolve_runfiles_path(ctx, f)] = f
        for entry in domain_rf.symlinks.to_list():
            root_symlinks[prefix + ctx.workspace_name + "/" + entry.path] = entry.target_file
        for entry in domain_rf.root_symlinks.to_list():
            root_symlinks[prefix + entry.path] = entry.target_file

def _zephyr_sysbuild_rule_impl(ctx):
    all_files = []
    all_files.extend(ctx.attr.main[DefaultInfo].files.to_list())
    for helper in ctx.attr.helpers:
        all_files.extend(helper[DefaultInfo].files.to_list())

    root_symlinks = {}

    runner_cmds = [
        "#!/usr/bin/env bash",
        "set -e",
        'BASE_RUNFILES_DIR="${RUNFILES_DIR:-${0}.runfiles}"',
        'if [[ "${BASE_RUNFILES_DIR}" != /* ]]; then',
        '  BASE_RUNFILES_DIR="$(cd "${BASE_RUNFILES_DIR}" 2>/dev/null && pwd || echo "$(pwd)/${BASE_RUNFILES_DIR}")"',
        "fi",
        "unset RUNFILES_MANIFEST_FILE",
        "HELPER_ARGS=()",
        'for arg in "$@"; do',
        '  if [[ "$arg" != "--monitor" && "$arg" != "-m" ]]; then',
        '    HELPER_ARGS+=("$arg")',
        "  fi",
        "done",
    ]

    for idx, helper in enumerate(ctx.attr.helpers):
        domain_id = str(idx)
        exec_file = None
        domain_rf = helper[DefaultInfo].default_runfiles
        if SysbuildHelperInfo in helper:
            exec_file = helper[SysbuildHelperInfo].executable
            if helper[SysbuildHelperInfo].runfiles:
                domain_rf = helper[SysbuildHelperInfo].runfiles
        elif helper[DefaultInfo].files_to_run and helper[DefaultInfo].files_to_run.executable:
            exec_file = helper[DefaultInfo].files_to_run.executable

        _add_domain_symlinks(ctx, domain_id, exec_file, domain_rf, root_symlinks)

        if exec_file:
            exec_rloc = resolve_runfiles_path(ctx, exec_file)
            runner_cmds.append(
                '[[ -f "${{BASE_RUNFILES_DIR}}/_repo_mapping" ]] && ln -sf "${{BASE_RUNFILES_DIR}}/_repo_mapping" "${{BASE_RUNFILES_DIR}}/_domain_{id}/_repo_mapping" 2>/dev/null || true'.format(
                    id = domain_id,
                ),
            )
            runner_cmds.append(
                'RUNFILES_DIR="${{BASE_RUNFILES_DIR}}/_domain_{id}" "${{BASE_RUNFILES_DIR}}/_domain_{id}/{rloc}" "${{HELPER_ARGS[@]}}"'.format(
                    id = domain_id,
                    rloc = exec_rloc,
                ),
            )

    main_exec = ctx.attr.main[DefaultInfo].files_to_run.executable if ctx.attr.main[DefaultInfo].files_to_run else None
    main_rf = ctx.attr.main[DefaultInfo].default_runfiles
    _add_domain_symlinks(ctx, "main", main_exec, main_rf, root_symlinks)

    if main_exec:
        main_rloc = resolve_runfiles_path(ctx, main_exec)
        runner_cmds.append(
            '[[ -f "${BASE_RUNFILES_DIR}/_repo_mapping" ]] && ln -sf "${BASE_RUNFILES_DIR}/_repo_mapping" "${BASE_RUNFILES_DIR}/_domain_main/_repo_mapping" 2>/dev/null || true',
        )
        runner_cmds.append(
            'RUNFILES_DIR="${{BASE_RUNFILES_DIR}}/_domain_main" "${{BASE_RUNFILES_DIR}}/_domain_main/{rloc}" "$@"'.format(
                rloc = main_rloc,
            ),
        )

    runfiles = ctx.runfiles(
        transitive_files = main_rf.files if main_rf else None,
        root_symlinks = root_symlinks,
    )

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

    runner_script = ctx.actions.declare_file(ctx.label.name + "_runner.sh")
    ctx.actions.write(
        output = runner_script,
        content = "\n".join(runner_cmds) + "\n",
        is_executable = True,
    )

    providers = [DefaultInfo(
        executable = runner_script,
        files = depset([runner_script] + all_files),
        runfiles = runfiles,
    )]
    if output_groups:
        merged_groups = {k: depset(transitive = v) for k, v in output_groups.items()}
        providers.append(OutputGroupInfo(**merged_groups))
    return providers

_zephyr_sysbuild_rule = rule(
    implementation = _zephyr_sysbuild_rule_impl,
    executable = True,
    attrs = {
        "board_helper_keys": attr.string_list(),
        "main": attr.label(mandatory = True),
        "helpers": attr.label_list(),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    cfg = _zephyr_sysbuild_transition,
)
