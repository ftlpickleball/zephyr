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
    name = "arc_stdlib",
    srcs = glob(
        [
            "arc-zephyr-elf/include/**",
            "arc-zephyr-elf/lib/**",
            "arc-zephyr-elf/sys-include/**",
        ],
        allow_empty = True,
    ),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "arc-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "arc-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "arc-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "arc-g++",
        "@rules_cc//cc/toolchains/actions:strip": "arc-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "arc-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "arc-ar",
    },
)

cc_tool(
    name = "arc-ar",
    src = "//:bin/arc-zephyr-elf-ar",
)

cc_tool(
    name = "arc-g++",
    src = "//:bin/arc-zephyr-elf-g++",
    data = glob([
        "lib/gcc/arc-zephyr-elf/14.3.0/**",
        "libexec/gcc/arc-zephyr-elf/14.3.0/**",
        "arc-zephyr-elf/bin/**",
    ]) + [":arc_stdlib"],
)

cc_tool(
    name = "arc-gcc",
    src = "//:bin/arc-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/arc-zephyr-elf/14.3.0/**",
        "libexec/gcc/arc-zephyr-elf/14.3.0/**",
        "arc-zephyr-elf/bin/**",
    ]) + [":arc_stdlib"],
)

cc_tool(
    name = "arc-objcopy",
    src = "//:bin/arc-zephyr-elf-objcopy",
)

cc_tool(
    name = "arc-objdump",
    src = "//:bin/arc-zephyr-elf-objdump",
)

cc_tool(
    name = "arc-strip",
    src = "//:bin/arc-zephyr-elf-strip",
)
