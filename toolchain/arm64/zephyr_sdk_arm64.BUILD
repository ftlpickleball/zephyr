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
    name = "arm64_stdlib",
    srcs = glob([
        "aarch64-zephyr-elf/include/**",
        "aarch64-zephyr-elf/lib/**",
    ]),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "aarch64-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "aarch64-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "aarch64-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "aarch64-g++",
        "@rules_cc//cc/toolchains/actions:strip": "aarch64-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "aarch64-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "aarch64-ar",
    },
)

cc_tool(
    name = "aarch64-ar",
    src = "//:bin/aarch64-zephyr-elf-ar",
)

cc_tool(
    name = "aarch64-g++",
    src = "//:bin/aarch64-zephyr-elf-g++",
    data = glob([
        "lib/gcc/aarch64-zephyr-elf/14.3.0/include/**",
        "lib/gcc/aarch64-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/aarch64-zephyr-elf/14.3.0/**",
        "aarch64-zephyr-elf/bin/**",
    ]) + [":arm64_stdlib"],
)

cc_tool(
    name = "aarch64-gcc",
    src = "//:bin/aarch64-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/aarch64-zephyr-elf/14.3.0/include/**",
        "lib/gcc/aarch64-zephyr-elf/14.3.0/include-fixed/**",
        "libexec/gcc/aarch64-zephyr-elf/14.3.0/**",
        "aarch64-zephyr-elf/bin/**",
    ]) + [":arm64_stdlib"],
)

cc_tool(
    name = "aarch64-objcopy",
    src = "//:bin/aarch64-zephyr-elf-objcopy",
)

cc_tool(
    name = "aarch64-objdump",
    src = "//:bin/aarch64-zephyr-elf-objdump",
)

cc_tool(
    name = "aarch64-strip",
    src = "//:bin/aarch64-zephyr-elf-strip",
)
