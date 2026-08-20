# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc/toolchains:tool.bzl", "cc_tool")
load("@rules_cc//cc/toolchains:tool_map.bzl", "cc_tool_map")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

cc_tool_map(
    name = "arm_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:ar_actions": ":arm-zephyr-eabi-ar",
        "@rules_cc//cc/toolchains/actions:assembly_actions": ":arm-zephyr-eabi-asm",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": ":arm-zephyr-eabi-gcc",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": ":arm-zephyr-eabi-g++",
        "@rules_cc//cc/toolchains/actions:link_actions": ":arm-zephyr-eabi-g++",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": ":arm-zephyr-eabi-objcopy",
    },
)

cc_tool(
    name = "arm-zephyr-eabi-ar",
    src = "//:bin/arm-zephyr-eabi-ar",
)

cc_tool(
    name = "arm-zephyr-eabi-g++",
    src = "//:bin/arm-zephyr-eabi-g++",
    data = glob([
        "arm-zephyr-eabi/bin/**",
        "arm-zephyr-eabi/include/**",
        "arm-zephyr-eabi/lib/**",
        "lib/gcc/arm-zephyr-eabi/*/include/**",
        "lib/gcc/arm-zephyr-eabi/*/include-fixed/**",
        "libexec/gcc/arm-zephyr-eabi/*/**",
    ]),
)

# TODO: https://github.com/bazelbuild/rules_cc/issues/235 - Workaround until
# Bazel has a more robust way to implement `cc_tool_map`.
alias(
    name = "arm-zephyr-eabi-asm",
    actual = ":arm-zephyr-eabi-gcc",
)

cc_tool(
    name = "arm-zephyr-eabi-gcc",
    src = "//:bin/arm-zephyr-eabi-gcc",
    data = glob([
        "arm-zephyr-eabi/bin/**",
        "arm-zephyr-eabi/include/**",
        "arm-zephyr-eabi/lib/**",
        "lib/gcc/arm-zephyr-eabi/*/include/**",
        "lib/gcc/arm-zephyr-eabi/*/include-fixed/**",
        "libexec/gcc/arm-zephyr-eabi/*/**",
    ]),
)

cc_tool(
    name = "arm-zephyr-eabi-objcopy",
    src = "//:bin/arm-zephyr-eabi-objcopy",
)

filegroup(
    name = "sysroot_files",
    srcs = glob(
        include = [
            "picolibc/**",
            "arm-zephyr-eabi/bin/**",
            "arm-zephyr-eabi/include/**",
            "arm-zephyr-eabi/lib/**",
            "lib/gcc/arm-zephyr-eabi/*/include/**",
            "lib/gcc/arm-zephyr-eabi/*/include-fixed/**",
            "libexec/gcc/arm-zephyr-eabi/*/**",
        ],
        allow_empty = True,
    ),
)
