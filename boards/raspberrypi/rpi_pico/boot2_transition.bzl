# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

def _boot2_transition_impl(settings, attrs):
    # The second-stage bootloader (boot2) is extremely size-constrained (256 bytes)
    # and runs in a minimal pre-RAM environment. We transition custom_malloc and
    # link_extra_libs to empty libraries to prevent the toolchain from linking the
    # standard memory allocator or other helper/Pigweed libraries that would exceed
    # the size limit or reference missing runtime symbols.
    return {
        "//command_line_option:custom_malloc": str(attrs._malloc),
        "@bazel_tools//tools/cpp:link_extra_libs": str(attrs._link_extra_libs),
    }

_boot2_transition = transition(
    implementation = _boot2_transition_impl,
    inputs = [],
    outputs = [
        "//command_line_option:custom_malloc",
        "@bazel_tools//tools/cpp:link_extra_libs",
    ],
)

def _boot2_binary_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = out, target_file = ctx.executable.src)
    return [DefaultInfo(files = depset([out]), executable = out)]

boot2_binary = rule(
    implementation = _boot2_binary_impl,
    executable = True,
    attrs = {
        "src": attr.label(
            cfg = _boot2_transition,
            executable = True,
            mandatory = True,
        ),
        "_malloc": attr.label(default = "@rules_cc//:empty_lib"),
        "_link_extra_libs": attr.label(default = "@rules_cc//:empty_lib"),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)
