# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc/toolchains:tool.bzl", "cc_tool")
load("@rules_cc//cc/toolchains:tool_map.bzl", "cc_tool_map")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

cc_tool_map(
    name = "llvm_tools",
    tools = {
        "@rules_cc//cc/toolchains/actions:ar_actions": ":llvm-ar",
        "@rules_cc//cc/toolchains/actions:assembly_actions": ":llvm-asm",
        "@rules_cc//cc/toolchains/actions:c_compile_actions": ":clang",
        "@rules_cc//cc/toolchains/actions:cpp_compile_actions": ":clang++",
        "@rules_cc//cc/toolchains/actions:link_actions": ":clang++",
        "@rules_cc//cc/toolchains/actions:objcopy_embed_data": ":llvm-objcopy",
    },
)

cc_tool(
    name = "llvm-ar",
    src = "//:llvm/bin/llvm-ar",
)

# Clang needs headers and runtime libraries to perform cross-compilation.
# We include all of llvm/bin because clang might invoke ld.lld or other tools internally.
_CLANG_DATA = glob([
    "llvm/bin/**",
    "llvm/lib/clang/19/**",
], allow_empty = True) + ["@zephyr_sdk_arm//:sysroot_files"]

cc_tool(
    name = "clang",
    src = "//:llvm/bin/clang",
    data = _CLANG_DATA,
)

cc_tool(
    name = "clang++",
    src = "//:llvm/bin/clang++",
    data = _CLANG_DATA,
)

# Workaround until rules_cc has a better way to handle assembly actions.
alias(
    name = "llvm-asm",
    actual = ":clang",
)

cc_tool(
    name = "llvm-objcopy",
    src = "//:llvm/bin/llvm-objcopy",
)

filegroup(
    name = "cxx_armv6m_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv6m_soft_nofp/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv7m_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_soft_nofp/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8m_base_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.base_soft_nofp/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8m_main_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.main_soft_nofp/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8_1m_main_soft_nofp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_soft_nofp_nomve/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv7m_hard_fpv4_sp_d16",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_hard_fpv4_sp_d16/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv7m_hard_fpv5_d16",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_hard_fpv5_d16/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8m_main_hard_fp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.main_hard_fp/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8_1m_main_hard_fp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_hard_fp_nomve/include/**"], allow_empty = True),
)

filegroup(
    name = "cxx_armv8_1m_main_hard_fpdp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_hard_fpdp_nomve/include/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv6m_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv6m_soft_nofp/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv7m_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_soft_nofp/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8m_base_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.base_soft_nofp/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8m_main_soft_nofp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.main_soft_nofp/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8_1m_main_soft_nofp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_soft_nofp_nomve/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv7m_hard_fpv4_sp_d16",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_hard_fpv4_sp_d16/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv7m_hard_fpv5_d16",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv7m_hard_fpv5_d16/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8m_main_hard_fp",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8m.main_hard_fp/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8_1m_main_hard_fp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_hard_fp_nomve/lib/**"], allow_empty = True),
)

filegroup(
    name = "lib_armv8_1m_main_hard_fpdp_nomve",
    srcs = glob(["llvm/lib/clang-runtimes/arm-none-eabi/armv8.1m.main_hard_fpdp_nomve/lib/**"], allow_empty = True),
)
