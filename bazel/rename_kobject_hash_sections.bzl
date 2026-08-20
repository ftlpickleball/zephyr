# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _rename_kobject_sections_impl(ctx):
    # Collect input kobject object file.
    target_files = ctx.attr.dep[DefaultInfo].files.to_list()
    in_lib = None
    for f in target_files:
        if f.extension in ["a", "o", "lo"]:
            in_lib = f
            break

    if not in_lib:
        fail("Could not find a .a, .lo, or .o file directly output by %s" % ctx.attr.dep.label)

    # Declare the renamed output file
    out_lib = ctx.actions.declare_file(ctx.label.name + "_renamed." + in_lib.extension)

    # Find the objcopy tool.
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

    command = """{objcopy} --rename-section .literal=.kobject_data.literal \
        --rename-section .data=.kobject_data.data \
        --rename-section .sdata=.kobject_data.sdata \
        --rename-section .text=.kobject_data.text \
        --rename-section .rodata=.kobject_data.rodata {in_lib} {out_lib}""".format(
        objcopy = objcopy_executable,
        in_lib = in_lib.path,
        out_lib = out_lib.path,
    )

    ctx.actions.run_shell(
        inputs = depset(direct = [in_lib], transitive = [cc_toolchain.all_files]),
        outputs = [out_lib],
        command = command,
        mnemonic = "ObjcopyRenameSections",
        progress_message = "Renaming kobject sections in %s" % in_lib.short_path,
    )

    # Wrap the modified archive back into a CcInfo provider
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
    )

    library_to_link = cc_common.create_library_to_link(
        actions = ctx.actions,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        static_library = out_lib,
        # Force the linker to keep this table even if no direct function calls exist
    )

    linking_context = cc_common.create_linking_context(
        linker_inputs = depset([
            cc_common.create_linker_input(
                owner = ctx.label,
                libraries = depset([library_to_link]),
            ),
        ]),
    )

    return [
        DefaultInfo(files = depset([out_lib])),
        CcInfo(linking_context = linking_context),
    ]

rename_kobject_sections = rule(
    implementation = _rename_kobject_sections_impl,
    attrs = {
        "dep": attr.label(
            providers = [CcInfo, DefaultInfo],
            mandatory = True,
            doc = "The original kobject cc_library",
        ),
        "_cc_toolchain": attr.label(
            default = Label("@bazel_tools//tools/cpp:current_cc_toolchain"),
        ),
    },
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
    fragments = ["cpp"],
)
