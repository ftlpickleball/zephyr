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
    name = "sparc_stdlib",
    srcs = glob(
        [
            "sparc-zephyr-elf/include/**",
            "sparc-zephyr-elf/lib/**",
            "sparc-zephyr-elf/sys-include/**",
        ],
        allow_empty = True,
    ),
)

cc_tool_map(
    name = "all_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:assembly_actions": "sparc-gcc",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": "sparc-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": "sparc-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": "sparc-g++",
        "@rules_cc//cc/toolchains/actions:strip": "sparc-strip",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": "sparc-objcopy",
        "@rules_cc//cc/toolchains/actions:ar_actions": "sparc-ar",
    },
)

cc_tool(
    name = "sparc-ar",
    src = "//:bin/sparc-zephyr-elf-ar",
)

cc_tool(
    name = "sparc-g++",
    src = "//:bin/sparc-zephyr-elf-g++",
    data = glob([
        "lib/gcc/sparc-zephyr-elf/14.3.0/**",
        "libexec/gcc/sparc-zephyr-elf/14.3.0/**",
        "sparc-zephyr-elf/bin/**",
    ]) + [":sparc_stdlib"],
)

cc_tool(
    name = "sparc-gcc",
    src = "//:bin/sparc-zephyr-elf-gcc",
    data = glob([
        "lib/gcc/sparc-zephyr-elf/14.3.0/**",
        "libexec/gcc/sparc-zephyr-elf/14.3.0/**",
        "sparc-zephyr-elf/bin/**",
    ]) + [":sparc_stdlib"],
)

cc_tool(
    name = "sparc-objcopy",
    src = "//:bin/sparc-zephyr-elf-objcopy",
)

cc_tool(
    name = "sparc-objdump",
    src = "//:bin/sparc-zephyr-elf-objdump",
)

cc_tool(
    name = "sparc-strip",
    src = "//:bin/sparc-zephyr-elf-strip",
)
