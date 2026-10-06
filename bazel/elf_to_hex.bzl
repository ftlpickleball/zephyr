# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Rule to convert ELF to HEX using the toolchain's objcopy."""

load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")

def _elf_to_hex_impl(ctx):
    elf = ctx.file.src
    hex_file = ctx.actions.declare_file(ctx.label.name + ".hex")

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    objcopy_executable = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.objcopy_embed_data,
    )
    objcopy_flags = cc_common.get_memory_inefficient_command_line(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.objcopy_embed_data,
        variables = cc_common.create_compile_variables(
            feature_configuration = feature_configuration,
            cc_toolchain = cc_toolchain,
        ),
    )

    ctx.actions.run(
        outputs = [hex_file],
        inputs = depset(direct = [elf], transitive = [cc_toolchain.all_files]),
        executable = objcopy_executable,
        arguments = objcopy_flags + ["-O", "ihex", elf.path, hex_file.path],
        mnemonic = "ElfToHex",
        progress_message = "Converting %s to HEX" % elf.short_path,
    )

    return [DefaultInfo(files = depset([hex_file]))]

elf_to_hex = rule(
    implementation = _elf_to_hex_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "The ELF input file",
        ),
        "_cc_toolchain": attr.label(
            default = Label("@bazel_tools//tools/cpp:current_cc_toolchain"),
        ),
    },
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
    fragments = ["cpp"],
)
