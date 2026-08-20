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
    name = "rx_stdlib",
    srcs = glob([
        "rx-zephyr-elf/include/**",
        "rx-zephyr-elf/lib/**",
    ]),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "rx-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "rx-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "rx-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "rx-g++",
        "@rules_cc//cc/toolchains/actions:strip": "rx-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "rx-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "rx-ar",
    },
)

cc_tool(
    name = "rx-ar",
    src = "//:bin/rx-zephyr-elf-ar",
)

cc_tool(
    name = "rx-g++",
    src = "//:bin/rx-zephyr-elf-g++",
    data = glob([
        "lib/gcc/rx-zephyr-elf/14.3.0/include/**",
        "lib/gcc/rx-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/rx-zephyr-elf/14.3.0/**",
        "rx-zephyr-elf/bin/**",
    ]) + [":rx_stdlib"],
)

cc_tool(
    name = "rx-gcc",
    src = "//:bin/rx-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/rx-zephyr-elf/14.3.0/include/**",
        "lib/gcc/rx-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/rx-zephyr-elf/14.3.0/**",
        "rx-zephyr-elf/bin/**",
    ]) + [":rx_stdlib"],
)

cc_tool(
    name = "rx-objcopy",
    src = "//:bin/rx-zephyr-elf-objcopy",
)

cc_tool(
    name = "rx-objdump",
    src = "//:bin/rx-zephyr-elf-objdump",
)

cc_tool(
    name = "rx-strip",
    src = "//:bin/rx-zephyr-elf-strip",
)
