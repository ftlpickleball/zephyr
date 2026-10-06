# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain", "use_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")

def _xtensa_zsr_header_impl(ctx):
    all_files = ctx.attr.core_files.files.to_list()

    core_isa_header = None
    for f in all_files:
        if f.basename == "core-isa.h":
            core_isa_header = f
            break

    if not core_isa_header:
        fail("Could not find core-isa.h in the provided filegroup.")

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    xt_cc_executable = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.c_compile,
    )

    c_compile_variables = cc_common.create_compile_variables(
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
    )
    c_compile_flags = cc_common.get_memory_inefficient_command_line(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.c_compile,
        variables = c_compile_variables,
    )

    core_isa_dm = ctx.actions.declare_file("include/generated/zephyr/core-isa-dM.h")

    # Zephyr uses the Xtensa compiler to preprocess the core-isa header.
    # We do the same. The result, called core-isa-dM.h, will be used to
    # generate zsr.h below.
    command_str = (
        "{xt_cc} {c_flags} -E -dM -U__XCC__ {core_isa} > {core_isa_dm}"
    ).format(
        xt_cc = shell.quote(xt_cc_executable),
        c_flags = " ".join([shell.quote(f) for f in c_compile_flags]),
        core_isa = shell.quote(core_isa_header.path),
        core_isa_dm = shell.quote(core_isa_dm.path),
    )
    ctx.actions.run_shell(
        inputs = [core_isa_header] + cc_toolchain.all_files.to_list(),
        outputs = [core_isa_dm],
        command = command_str,
        mnemonic = "ZephyrPreprocessCoreIsa",
    )

    zsr_header = ctx.actions.declare_file("include/generated/zephyr/zsr.h")
    ctx.actions.run(
        inputs = [core_isa_dm],
        outputs = [zsr_header],
        executable = ctx.attr._gen_zsr[DefaultInfo].files_to_run.executable,
        arguments = [
            core_isa_dm.path,
            zsr_header.path,
        ],
        mnemonic = "GenXtensaZsrHeader",
        progress_message = "Generating Xtensa zsr header",
    )
    xtensa_vectors_ld = ctx.actions.declare_file("include/generated/xtensa_vectors.ld")
    gen_vectors_exe = ctx.attr._gen_vectors[DefaultInfo].files_to_run.executable
    ctx.actions.run_shell(
        inputs = [core_isa_dm],
        outputs = [xtensa_vectors_ld],
        tools = [gen_vectors_exe],
        command = "%s %s > %s" % (
            shell.quote(gen_vectors_exe.path),
            shell.quote(core_isa_dm.path),
            shell.quote(xtensa_vectors_ld.path),
        ),
        mnemonic = "GenXtensaVectorsLd",
        progress_message = "Generating xtensa_vectors.ld",
    )
    return [DefaultInfo(files = depset([zsr_header, xtensa_vectors_ld]))]

# Rule to generate zsr.h and xtensa_vectors.ld from the specific core's
# core-isa.h
xtensa_zsr_header = rule(
    implementation = _xtensa_zsr_header_impl,
    attrs = {
        "core_files": attr.label(
            mandatory = True,
            allow_files = True,
        ),
        "_gen_zsr": attr.label(
            default = "//arch/xtensa/core:gen_zsr",
            executable = True,
            cfg = "exec",
        ),
        "_gen_vectors": attr.label(
            default = "//arch/xtensa/core:gen_vectors",
            executable = True,
            cfg = "exec",
        ),
    },
    output_to_genfiles = True,
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)
