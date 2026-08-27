# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Defines the zephyr_cc_unit_test rule."""

load("@bazel_skylib//rules:copy_file.bzl", "copy_file")
load("@rules_python//python:py_test.bzl", "py_test")
load("//bazel:cc.bzl", "zephyr_app", "zephyr_cc_library")

def zephyr_cc_test(**kw_args):
    """Creates a Zephyr test library for use with a test runner."""
    zephyr_cc_library(
        deps = kw_args.pop("deps", []),
        testonly = True,
        **kw_args
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
    bin_name = name + "_bin"

    # 1. Compile the executable Zephyr application (forwarding compilation kwargs)
    zephyr_app(
        name = bin_name,
        deps = deps,
        testonly = True,
        visibility = ["//visibility:private"],
        **kwargs
    )

    # 2. Copy the runner script to the local package to satisfy py_test constraints
    runner_script = name + "_runner.py"
    copy_file(
        name = name + "_runner_copy",
        src = Label("//bazel/tools/runners:ztest_runner.py"),
        out = runner_script,
        testonly = True,
    )

    # 3. Simulator test target (sandboxed, cached)
    py_test(
        name = name + "_sim",
        srcs = [runner_script],
        main = runner_script,
        data = [
            ":" + bin_name + ".elf",
            ":" + bin_name + "_runners_yaml",
        ],
        deps = [
            Label("//bazel/tools/runners:ztest_runner"),
        ],
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
        visibility = visibility,
        target_compatible_with = [Label("//boards:sim")],
    )

    # 4. Hardware test target (local, no-cache, exclusive)
    py_test(
        name = name + "_hw",
        srcs = [runner_script],
        main = runner_script,
        data = [
            ":" + bin_name,
            ":" + bin_name + "_runners_yaml",
        ],
        deps = [
            Label("//bazel/tools/runners:ztest_runner"),
        ],
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
        visibility = visibility,
        target_compatible_with = [Label("//boards:hw")],
    )

    # 5. Unified test suite
    native.test_suite(
        name = name,
        tests = [
            ":" + name + "_sim",
            ":" + name + "_hw",
        ],
        visibility = visibility,
    )
