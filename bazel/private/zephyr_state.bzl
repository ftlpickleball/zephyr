# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Repository rule for the global Zephyr discovery state."""

def _zephyr_state_repo_impl(rctx):
    rctx.file("BUILD.bazel", 'exports_files(["state.json"])')
    rctx.file("state.json", rctx.attr.content)
    return rctx.repo_metadata(reproducible = True)

zephyr_state_repo = repository_rule(
    implementation = _zephyr_state_repo_impl,
    attrs = {
        "content": attr.string(mandatory = True),
    },
)

def _zephyr_index_repo_impl(rctx):
    build_content = 'package(default_visibility = ["//visibility:public"])\n\n'
    build_content += 'exports_files(["index.bzl"])\n\n'

    rctx.file("BUILD.bazel", build_content)
    rctx.file("index.bzl", rctx.attr.content)
    return rctx.repo_metadata(reproducible = True)

zephyr_index_repo = repository_rule(
    implementation = _zephyr_index_repo_impl,
    attrs = {
        "content": attr.string(mandatory = True),
    },
)
