# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Rule to transition a dependency to a specific platform."""

SysbuildHelperInfo = provider(
    doc = "Carries executable and runfiles from a transitioned sysbuild helper target.",
    fields = ["executable", "runfiles"],
)

def _transition_impl(settings, attr):
    # Made optional to let sysbuild helper domains inherit the platform
    # attribute of the parent domain.
    platforms = [str(attr.platform)] if attr.platform else settings["//command_line_option:platforms"]
    sysbuild_ctx = attr.sysbuild_context if getattr(attr, "sysbuild_context", "") else settings["//bazel:sysbuild_context"]
    return {
        "//command_line_option:platforms": platforms,
        "//bazel:sysbuild_context": sysbuild_ctx,
    }

platform_transition = transition(
    implementation = _transition_impl,
    inputs = [
        "//command_line_option:platforms",
        "//bazel:sysbuild_context",
    ],
    outputs = [
        "//command_line_option:platforms",
        "//bazel:sysbuild_context",
    ],
)

def _transitioned_dep_impl(ctx):
    # Forward DefaultInfo files, executable, and runfiles from the actual target
    target = ctx.attr.dep[0] if type(ctx.attr.dep) == "list" else ctx.attr.dep
    exec_file = target[DefaultInfo].files_to_run.executable if target[DefaultInfo].files_to_run else None
    providers = [
        DefaultInfo(
            files = target[DefaultInfo].files,
            runfiles = target[DefaultInfo].default_runfiles,
        ),
        SysbuildHelperInfo(
            executable = exec_file,
            runfiles = target[DefaultInfo].default_runfiles,
        ),
    ]
    if OutputGroupInfo in target:
        providers.append(target[OutputGroupInfo])
    return providers

transitioned_dep = rule(
    implementation = _transitioned_dep_impl,
    attrs = {
        "dep": attr.label(cfg = platform_transition),
        # Optional to let sysbuild helper domains inherit the platform
        # attribute of the parent domain.
        "platform": attr.string(mandatory = False),
        "sysbuild_context": attr.string(default = ""),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)
