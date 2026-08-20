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
    name = "x86_stdlib",
    srcs = glob([
        "x86_64-zephyr-elf/include/**",
        "x86_64-zephyr-elf/lib/**",
    ]),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "x86-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "x86-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "x86-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "x86-g++",
        "@rules_cc//cc/toolchains/actions:strip": "x86-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "x86-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "x86-ar",
    },
)

cc_tool(
    name = "x86-ar",
    src = "//:bin/x86_64-zephyr-elf-ar",
)

cc_tool(
    name = "x86-g++",
    src = "//:bin/x86_64-zephyr-elf-g++",
    data = glob([
        "lib/gcc/x86_64-zephyr-elf/14.3.0/include/**",
        "lib/gcc/x86_64-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/x86_64-zephyr-elf/14.3.0/**",
        "x86_64-zephyr-elf/bin/**",
    ]) + [":x86_stdlib"],
)

cc_tool(
    name = "x86-gcc",
    src = "//:bin/x86_64-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/x86_64-zephyr-elf/14.3.0/include/**",
        "lib/gcc/x86_64-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/x86_64-zephyr-elf/14.3.0/**",
        "x86_64-zephyr-elf/bin/**",
    ]) + [":x86_stdlib"],
)

cc_tool(
    name = "x86-objcopy",
    src = "//:bin/x86_64-zephyr-elf-objcopy",
)

cc_tool(
    name = "x86-objdump",
    src = "//:bin/x86_64-zephyr-elf-objdump",
)

cc_tool(
    name = "x86-strip",
    src = "//:bin/x86_64-zephyr-elf-strip",
)
