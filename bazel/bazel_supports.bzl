# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""A repository rule that defines what features are supported by Bazel.

Zephyr's Bazel files are sometimes meant to be used across multiple Bazel
versions. This can be challenging when the latest version of Bazel requires
changes where backwards compatibility becomes an issue.

For most cases, we attempt to determine compatibility by using calls like
`hasattr()` to determine if a structure has an attribute, or by some other
similar way of determining if a feature is available directly in Starlark.

However, not all features have an easy built-in way to detect if they are
available. The Bazel repo this repository rule creates allows corner cases to
be handled by defining a `bazel_supports` structure with boolean constants for
critical features that Zephyr uses.

Determining what features are supported is done in a repository rule context
(where built-in @bazel_tools files and `native.bazel_version` can be inspected,
which is not possible in regular BUILD or .bzl files). To keep things
maintainable and readable, this file intentionally makes itself the source of
truth about feature availability, and only exposes the support status of each
feature through the `bazel_supports` struct constants.
"""

def _bazel_supports_repo_impl(rctx):
    rctx.file("BUILD.bazel", 'exports_files(["bazel_supports.bzl"])\n')

    test_build = rctx.read(rctx.path(Label("@bazel_tools//tools/test:BUILD")))

    # Only add entries below if there is no other way to determine support.
    # True if @bazel_tools//tools/test:default_test_toolchain_type is available
    # (added in Bazel 9.0.0).
    has_default_test_toolchain_type = "default_test_toolchain_type" in test_build
    # Only add entries above if there is no other way to determine support.

    rctx.file(
        "bazel_supports.bzl",
        """bazel_supports = struct(
    default_test_toolchain_type = {default_test_toolchain_type},
)
""".format(
            default_test_toolchain_type = has_default_test_toolchain_type,
        ),
    )

    # rctx.repo_metadata is only available in Bazel>=8.3.0
    if hasattr(rctx, "repo_metadata"):
        return rctx.repo_metadata(reproducible = True)
    return None

bazel_supports_repo = repository_rule(
    implementation = _bazel_supports_repo_impl,
    doc = "Creates a repo where @repo//:bazel_supports.bzl contains Bazel feature support metadata.",
)
