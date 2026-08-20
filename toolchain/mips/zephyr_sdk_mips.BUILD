# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc/toolchains:tool.bzl", "cc_tool")
load("@rules_cc//cc/toolchains:tool_map.bzl", "cc_tool_map")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

filegroup(
    name = "all",
    srcs = glob(["**"]),
    visibility = ["//visibility:public"],
)

filegroup(
    name = "mips_stdlib",
    srcs = glob([
        "mips-zephyr-elf/include/**",
        "mips-zephyr-elf/lib/**",
    ]),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "mips-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "mips-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "mips-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "mips-g++",
        "@rules_cc//cc/toolchains/actions:strip": "mips-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "mips-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "mips-ar",
    },
)

cc_tool(
    name = "mips-ar",
    src = "//:bin/mips-zephyr-elf-ar",
)

cc_tool(
    name = "mips-g++",
    src = "//:bin/mips-zephyr-elf-g++",
    data = glob([
        "lib/gcc/mips-zephyr-elf/14.3.0/include/**",
        "lib/gcc/mips-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/mips-zephyr-elf/14.3.0/**",
        "mips-zephyr-elf/bin/**",
    ]) + [":mips_stdlib"],
)

cc_tool(
    name = "mips-gcc",
    src = "//:bin/mips-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/mips-zephyr-elf/14.3.0/include/**",
        "lib/gcc/mips-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/mips-zephyr-elf/14.3.0/**",
        "mips-zephyr-elf/bin/**",
    ]) + [":mips_stdlib"],
)

cc_tool(
    name = "mips-objcopy",
    src = "//:bin/mips-zephyr-elf-objcopy",
)

cc_tool(
    name = "mips-objdump",
    src = "//:bin/mips-zephyr-elf-objdump",
)

cc_tool(
    name = "mips-strip",
    src = "//:bin/mips-zephyr-elf-strip",
)
