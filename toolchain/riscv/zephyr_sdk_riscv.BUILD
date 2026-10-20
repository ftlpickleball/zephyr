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
    name = "riscv_stdlib",
    srcs = glob(
        [
            "riscv64-zephyr-elf/include/**",
            "riscv64-zephyr-elf/lib/**",
            "riscv64-zephyr-elf/sys-include/**",
        ],
        allow_empty = True,
    ),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "riscv-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "riscv-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "riscv-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "riscv-g++",
        "@rules_cc//cc/toolchains/actions:strip": "riscv-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "riscv-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "riscv-ar",
    },
)

cc_tool(
    name = "riscv-ar",
    src = "//:bin/riscv64-zephyr-elf-ar",
)

cc_tool(
    name = "riscv-g++",
    src = "//:bin/riscv64-zephyr-elf-g++",
    data = glob([
        "lib/gcc/riscv64-zephyr-elf/14.3.0/**",
        "libexec/gcc/riscv64-zephyr-elf/14.3.0/**",
        "riscv64-zephyr-elf/bin/**",
    ]) + [":riscv_stdlib"],
)

cc_tool(
    name = "riscv-gcc",
    src = "//:bin/riscv64-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/riscv64-zephyr-elf/14.3.0/**",
        "libexec/gcc/riscv64-zephyr-elf/14.3.0/**",
        "riscv64-zephyr-elf/bin/**",
    ]) + [":riscv_stdlib"],
)

cc_tool(
    name = "riscv-objcopy",
    src = "//:bin/riscv64-zephyr-elf-objcopy",
)

cc_tool(
    name = "riscv-objdump",
    src = "//:bin/riscv64-zephyr-elf-objdump",
)

cc_tool(
    name = "riscv-strip",
    src = "//:bin/riscv64-zephyr-elf-strip",
)
