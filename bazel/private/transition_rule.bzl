# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Rule to transition a dependency to a specific platform."""

def _transition_impl(settings, attr):
    # Made optional to let sysbuild helper domains inherit the platform
    # attribute of the parent domain.
    if attr.platform:
        return {"//command_line_option:platforms": [str(attr.platform)]}
    return {}

platform_transition = transition(
    implementation = _transition_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

def _transitioned_dep_impl(ctx):
    # Forward DefaultInfo from the actual target
    return [ctx.attr.dep[DefaultInfo]]

transitioned_dep = rule(
    implementation = _transitioned_dep_impl,
    attrs = {
        "dep": attr.label(cfg = platform_transition),
        # Optional to let sysbuild helper domains inherit the platform
        # attribute of the parent domain.
        "platform": attr.string(mandatory = False),
    },
)
