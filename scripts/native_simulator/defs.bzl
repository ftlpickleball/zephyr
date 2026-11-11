# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Bazel macros for native_simulator runner libraries."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")

def nsi_runner_cc_library(*, name, **kwargs):
    """Declares a C/C++ library compiled in the NSI host runner context.

    Compiles *_bottom.c sources with NSI_RUNNER_BUILD defined and Zephyr
    kernel header/type overrides disabled so host libraries (such as SDL2)
    do not collide with Zephyr kernel headers.

    Args:
        name: The target name.
        **kwargs: Additional arguments forwarded to cc_library.
    """
    copts = [
        "-U__ZEPHYR__",
        "-UKERNEL",
        "-Wno-cast-qual",
        "-Wno-sign-compare",
        "-Wno-unused-parameter",
    ] + kwargs.pop("copts", [])
    features = [
        "-zephyr_force_include_autoconf",
        "-zephyr_app_main",
        "-zephyr_errno",
        "-zephyr_stdint",
        "zephyr_warning_suppressions",
    ] + kwargs.pop("features", [])
    local_defines = ["NSI_RUNNER_BUILD"] + kwargs.pop("local_defines", [])
    target_compatible_with = kwargs.pop(
        "target_compatible_with",
        [
            Label("@platforms//os:linux"),
            Label("//boards:sim"),
        ],
    )
    cc_library(
        name = name,
        copts = copts,
        features = features,
        local_defines = local_defines,
        target_compatible_with = target_compatible_with,
        **kwargs
    )
