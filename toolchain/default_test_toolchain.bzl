# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""A helper macro for defining Bazel 9 default test toolchains."""

load("@bazel_supports//:bazel_supports.bzl", "bazel_supports")

def default_test_toolchain(*, name = None, **kwargs):
    """Bazel compatibility shim for toolchains with default_test_toolchain_type.

    The toolchain type "@bazel_tools//tools/test:default_test_toolchain_type"
    was added with Bazel 9, and does not exist under Bazel 8. Bazel 9 uses
    toolchains registered with this type to determine how to execute tests.

    This shim allows toolchains to be defined in `//toolchain:BUILD.bazel`
    (which is registered via `//toolchain:all`) so that if the end user is
    using Bazel 8, the toolchain definition is skipped and does not cause an
    evaluation error for the missing toolchain type.
    """
    if bazel_supports.default_test_toolchain_type:
        native.toolchain(
            name = name,
            **kwargs
        )
