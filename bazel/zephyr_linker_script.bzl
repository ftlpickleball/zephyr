# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Rules for declaring preprocessed linker scripts."""

load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain", "use_cpp_toolchain")
load("@rules_cc//cc:action_names.bzl", "C_COMPILE_ACTION_NAME")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _preprocess_linker_script_impl(ctx):
    cc_toolchain = find_cpp_toolchain(ctx)
    output_script = ctx.actions.declare_file(ctx.label.name + ".ld")
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features + [
            "module_maps",
        ],
    )
    cxx_compiler_path = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = C_COMPILE_ACTION_NAME,
    )
    compilation_context = cc_common.merge_compilation_contexts(
        compilation_contexts = [dep[CcInfo].compilation_context for dep in ctx.attr.deps],
    )
    c_compile_variables = cc_common.create_compile_variables(
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        user_compile_flags = ctx.fragments.cpp.copts + ctx.fragments.cpp.conlyopts +
                             # Provide autoconf.h to the linker scripts via a compiler flag.
                             ["-include", ctx.file.autoconf_file.path],
        include_directories = compilation_context.includes,
        quote_include_directories = compilation_context.quote_includes,
        system_include_directories = compilation_context.system_includes,
        preprocessor_defines = depset(ctx.attr.defines, transitive = [compilation_context.defines]),
    )
    cmd_line = cc_common.get_memory_inefficient_command_line(
        feature_configuration = feature_configuration,
        action_name = C_COMPILE_ACTION_NAME,
        variables = c_compile_variables,
    )
    env = cc_common.get_environment_variables(
        feature_configuration = feature_configuration,
        action_name = C_COMPILE_ACTION_NAME,
        variables = c_compile_variables,
    )
    ctx.actions.run(
        outputs = [output_script],
        inputs = depset(
            [ctx.file.linker_script, ctx.file.autoconf_file],
            transitive = [compilation_context.headers, cc_toolchain.all_files],
        ),
        executable = cxx_compiler_path,
        arguments = [
            "-E",
            "-P",
            "-xc",
            ctx.file.linker_script.path,
            "-o",
            output_script.path,
        ] + cmd_line + [
            # Args added last to ensure they are not overridden.

            # Undefined preprcoessor symbols should not be treated as an error
            # in the linker scripts.
            "-Wno-error=undef",
        ],
        env = env,
    )
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        user_link_flags = ["-T", output_script.path],
        additional_inputs = depset(direct = [output_script]),
    )
    linking_context = cc_common.create_linking_context(
        linker_inputs = depset(direct = [linker_input]),
    )
    return [
        DefaultInfo(files = depset([output_script])),
        CcInfo(linking_context = linking_context),
    ]

zephyr_linker_script = rule(
    _preprocess_linker_script_impl,
    doc = """Create a linker script target. Supports preprocessing with the C
    preprocessor and adding the resulting linker script to linkopts. Also
    provides a DefaultInfo containing the processed linker script.
    """,
    attrs = {
        "autoconf_file": attr.label(
            allow_single_file = True,
            default = "//:autoconf_file",
            doc = "Autoconf.h to include in the linker script.",
        ),
        "defines": attr.string_list(doc = "C preprocessor defines."),
        "deps": attr.label_list(
            providers = [CcInfo],
            doc = """Dependencies of this linker script. Can be used to provide
                     header files and defines. Only the CompilationContext of
                     the provided dependencies are used.""",
        ),
        "linker_script": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "Linker script to preprocess.",
        ),
    },
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)
