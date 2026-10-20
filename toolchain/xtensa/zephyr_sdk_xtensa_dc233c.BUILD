# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc/toolchains:tool.bzl", "cc_tool")
load("@rules_cc//cc/toolchains:tool_map.bzl", "cc_tool_map")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

# This build file defines a complete set of tools for an Xtensa toolchain.

filegroup(
    name = "all",
    srcs = glob(["**"]),
    visibility = ["//visibility:public"],
)

filegroup(
    name = "xtensa_core_stdlib",
    srcs = glob(
        [
            "xtensa-dc233c_zephyr-elf/include/**",
            "xtensa-dc233c_zephyr-elf/lib/**",
            "xtensa-dc233c_zephyr-elf/sys-include/**",
        ],
        allow_empty = True,
    ),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "xt-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "xt-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "xt-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "xt-g++",
        "@rules_cc//cc/toolchains/actions:strip": "xt-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "xt-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "xt-ar",
    },
)

cc_tool(
    name = "xt-ar",
    src = "//:bin/xtensa-dc233c_zephyr-elf-ar",
)

cc_tool(
    name = "xt-g++",
    src = "//:bin/xtensa-dc233c_zephyr-elf-g++",
    data = glob([
        "lib/gcc/xtensa-dc233c_zephyr-elf/14.3.0/**",
        "libexec/gcc/xtensa-dc233c_zephyr-elf/14.3.0/**",
        "xtensa-dc233c_zephyr-elf/bin/**",
    ]) + [":xtensa_core_stdlib"],
)

cc_tool(
    name = "xt-gcc",
    src = "//:bin/xtensa-dc233c_zephyr-elf-gcc",
    data = glob([
        "lib/gcc/xtensa-dc233c_zephyr-elf/14.3.0/**",
        "libexec/gcc/xtensa-dc233c_zephyr-elf/14.3.0/**",
        "xtensa-dc233c_zephyr-elf/bin/**",
    ]) + [":xtensa_core_stdlib"],
)

cc_tool(
    name = "xt-objcopy",
    src = "//:bin/xtensa-dc233c_zephyr-elf-objcopy",
)

cc_tool(
    name = "xt-objdump",
    src = "//:bin/xtensa-dc233c_zephyr-elf-objdump",
)

cc_tool(
    name = "xt-strip",
    src = "//:bin/xtensa-dc233c_zephyr-elf-strip",
)
