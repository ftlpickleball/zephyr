# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Rules and providers for Zephyr hardware runners configuration."""

load("@rules_python//python:py_info.bzl", "PyInfo")
load("//bazel:runfiles.bzl", "resolve_runfiles_path")
load("//bazel/private:zephyr_transition.bzl", "zephyr_transition")

ZephyrRunnerConfigInfo = provider(
    doc = "Carries configuration for Zephyr hardware runners.",
    fields = {
        "args": "List of arguments for the runner.",
        "board_dir": "The directory of the board.",
        "deps": "List of library/dependency targets required by the runner.",
        "runner": "The name of the runner (e.g. jlink, openocd).",
        "runner_source": "Optional Python file implementing the runner.",
        "tools": "Depset or list of tool targets required by the runner.",
    },
)

def _zephyr_runner_config_impl(ctx):
    # Retrieve the package path of the board.
    # For OOT boards in the main workspace, this will be the package path.
    # For in-tree boards, it will be the package path in the @zephyr repo.
    board_dir = ctx.label.package
    return [
        ZephyrRunnerConfigInfo(
            runner = ctx.attr.runner,
            args = ctx.attr.args,
            board_dir = board_dir,
            runner_source = ctx.file.runner_source,
            tools = ctx.attr.tools,
            deps = ctx.attr.deps,
        ),
    ]

zephyr_runner_config = rule(
    implementation = _zephyr_runner_config_impl,
    doc = "Defines the hardware runner configuration for a board.",
    attrs = {
        "args": attr.string_list(doc = "Default list of arguments for the runner."),
        "deps": attr.label_list(cfg = "exec", doc = "Libraries or dependencies required by the runner."),
        "runner": attr.string(mandatory = True, doc = "The name of the runner (e.g. jlink, openocd)."),
        "runner_source": attr.label(allow_single_file = [".py"], doc = "Optional Python file implementing the runner."),
        "tools": attr.label_list(allow_files = True, cfg = "exec", doc = "Tools required by the runner (e.g. @openocd//:all)"),
    },
)

def _zephyr_runners_yaml_impl(ctx):
    config_info = ctx.attr.runner_config[ZephyrRunnerConfigInfo]
    runner = config_info.runner
    runner_source = getattr(config_info, "runner_source", None)

    deps = getattr(config_info, "deps", [])
    python_paths = []
    for dep in deps:
        if PyInfo in dep:
            for imp in dep[PyInfo].imports.to_list():
                if imp not in python_paths:
                    python_paths.append(imp)

    content = []
    content.append("config:")
    content.append("  board_dir: %s" % config_info.board_dir)
    content.append("  elf_file: %s" % resolve_runfiles_path(ctx, ctx.file.elf))
    if ctx.file.hex:
        content.append("  hex_file: %s" % resolve_runfiles_path(ctx, ctx.file.hex))
    if ctx.file.bin:
        content.append("  bin_file: %s" % resolve_runfiles_path(ctx, ctx.file.bin))
    if runner_source:
        content.append("  runner_source: %s" % resolve_runfiles_path(ctx, runner_source))
    if python_paths:
        content.append("  python_paths:")
        for p in python_paths:
            content.append("    - %s" % p)

    content.append("runners:")
    if runner:
        content.append("  - %s" % runner)
    content.append("flash-runner: %s" % runner)

    content.append("args:")
    if runner:
        content.append("  %s:" % runner)
        for arg in config_info.args:
            content.append("    - %s" % arg)

    out_file = ctx.actions.declare_file(ctx.label.name + ".yaml")
    ctx.actions.write(out_file, "\n".join(content) + "\n")

    runfiles_files = [ctx.file.elf]
    if ctx.file.hex:
        runfiles_files.append(ctx.file.hex)
    if ctx.file.bin:
        runfiles_files.append(ctx.file.bin)
    if runner_source:
        runfiles_files.append(runner_source)

    tool_runfiles = []
    tools = getattr(config_info, "tools", [])
    for tool in tools:
        if DefaultInfo in tool:
            tool_runfiles.append(tool[DefaultInfo].default_runfiles)
            tool_runfiles.append(ctx.runfiles(transitive_files = tool[DefaultInfo].files))

    deps = getattr(config_info, "deps", [])
    for dep in deps:
        if DefaultInfo in dep:
            tool_runfiles.append(dep[DefaultInfo].default_runfiles)
            tool_runfiles.append(ctx.runfiles(transitive_files = dep[DefaultInfo].files))

    runfiles = ctx.runfiles(files = runfiles_files)
    if tool_runfiles:
        runfiles = runfiles.merge_all(tool_runfiles)

    return [
        DefaultInfo(
            files = depset([out_file]),
            runfiles = runfiles,
        ),
    ]

zephyr_runners_yaml = rule(
    implementation = _zephyr_runners_yaml_impl,
    doc = "Generates a runners.yaml file for flashing and debugging.",
    attrs = {
        "app_label": attr.string(
            mandatory = True,
            doc = "The label of the application target.",
        ),
        "bin": attr.label(
            allow_single_file = True,
            doc = "Optional BIN file to flash.",
        ),
        "elf": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "The ELF binary to flash.",
        ),
        "hex": attr.label(
            allow_single_file = True,
            doc = "Optional HEX file to flash.",
        ),
        "runner_config": attr.label(
            mandatory = True,
            providers = [ZephyrRunnerConfigInfo],
            doc = "The runner configuration to use.",
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
            doc = "Allowlist for function transitions.",
        ),
    },
    cfg = zephyr_transition,
)
