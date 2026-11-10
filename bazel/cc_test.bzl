# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Defines the zephyr_cc_unit_test rule."""

load("//bazel:cc.bzl", "zephyr_app", "zephyr_cc_library")
load("//bazel:runfiles.bzl", "resolve_runfiles_path")

def _combine_compatible_with(base, caller):
    if not caller:
        return base
    res = list(base)
    for c in caller:
        if c not in res:
            res.append(c)
    return res

def zephyr_cc_test(**kw_args):
    """Creates a Zephyr test library for use with a test runner."""
    zephyr_cc_library(
        deps = kw_args.pop("deps", []),
        testonly = True,
        **kw_args
    )

def _zephyr_test_impl(ctx):
    runner = ctx.attr.runner[DefaultInfo]
    script = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.write(
        output = script,
        is_executable = True,
        content = """#!/usr/bin/env bash
set -euo pipefail
runfiles="${{RUNFILES_DIR:-$0.runfiles}}"
export RUNFILES_DIR="$runfiles"
exec "$runfiles/{runner}" "$@"
""".format(runner = resolve_runfiles_path(ctx, ctx.executable.runner)),
    )
    runfiles = ctx.runfiles(files = [ctx.executable.runner] + ctx.files.data)
    runfiles = runfiles.merge_all(
        [runner.default_runfiles] +
        [dep[DefaultInfo].default_runfiles for dep in ctx.attr.data],
    )
    return [DefaultInfo(executable = script, runfiles = runfiles)]

# A ztest runner: runs `runner` with the test's `args`, in which Bazel expands
# $(rlocationpath) for `data`. `data` (the Zephyr binary) is built for the
# board, the target platform, but the runner runs on the machine running the
# test, so it's built for the exec platform, and its Python dependencies
# resolve for that machine (e.g. rules_python picks its wheels), even when the
# board is bare metal.
_zephyr_test = rule(
    implementation = _zephyr_test_impl,
    test = True,
    attrs = {
        "data": attr.label_list(allow_files = True),
        "runner": attr.label(
            cfg = "exec",
            default = Label("//bazel/tools/runners:ztest_runner_bin"),
            executable = True,
        ),
    },
)

def ztest(
        name,
        deps,
        tags = None,
        visibility = None,
        stop_at = 10,
        success_signature = "PROJECT EXECUTION SUCCESSFUL",
        **kwargs):
    """Creates a Zephyr ZTest target runnable with `bazel test`.

    This macro compiles the target application binary under the hood and wraps
    it in an automated simulator runner validating the ZTest suite output.
    """
    tags = tags or []
    timeout = kwargs.pop("timeout", None)
    internal_tags = list(tags) + ([] if "manual" in tags else ["manual"])
    bin_name = name + "_bin"

    caller_compatible_with = kwargs.get("target_compatible_with")
    outer_compatible_with = (
        caller_compatible_with
        if type(caller_compatible_with) == "list"
        else None
    )

    # 1. Compile the executable Zephyr application (forwarding compilation kwargs)
    zephyr_app(
        name = bin_name,
        deps = deps,
        tags = internal_tags,
        testonly = True,
        visibility = ["//visibility:private"],
        **kwargs
    )

    # 2. Simulator test target (sandboxed, cached)
    _zephyr_test(
        name = name + "_sim",
        data = select({
            Label("//boards:sim"): [
                ":" + bin_name + ".elf",
                ":" + bin_name + "_runners_yaml",
            ],
            "//conditions:default": [],
        }),
        args = [
            "--binary",
            "$(rlocationpath :" + bin_name + ".elf)",
            "--runners-yaml",
            "$(rlocationpath :" + bin_name + "_runners_yaml)",
            "--stop-at",
            str(stop_at),
            "--success-signature",
            '"{}"'.format(success_signature),
        ],
        tags = tags,
        timeout = timeout,
        visibility = visibility,
        target_compatible_with = _combine_compatible_with(
            [Label("//boards:sim")],
            outer_compatible_with,
        ),
    )

    # 3. Hardware test target (local, no-cache, exclusive)
    _zephyr_test(
        name = name + "_hw",
        data = select({
            Label("//boards:hw"): [
                ":" + bin_name,
                ":" + bin_name + "_runners_yaml",
            ],
            "//conditions:default": [],
        }),
        args = [
            "--binary",
            "$(rlocationpath :" + bin_name + ")",
            "--runners-yaml",
            "$(rlocationpath :" + bin_name + "_runners_yaml)",
            "--stop-at",
            str(stop_at),
            "--success-signature",
            '"{}"'.format(success_signature),
        ],
        tags = tags + ["local", "exclusive"],
        timeout = timeout,
        visibility = visibility,
        target_compatible_with = _combine_compatible_with(
            [Label("//boards:hw")],
            outer_compatible_with,
        ),
    )

    # 4. Unified test suite
    native.test_suite(
        name = name,
        tests = [
            ":" + name + "_sim",
            ":" + name + "_hw",
        ],
        visibility = visibility,
    )
