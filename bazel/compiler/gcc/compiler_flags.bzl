# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

# Compiler flags are appended to "copts" of cc_libraries and can only have
# one level of selects, so we have to create a config_setting_group for every
# compiler flag we might need to add.

GCC_ARM_C_FLAGS = select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc": ["-mabi=aapcs"],
}) + select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc_compiler_isa_thumb2": ["-mthumb"],
}) + select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc_fp_hardabi": ["-mfloat-abi=hard"],
    "//bazel/compiler/gcc:is_arm_gcc_fp_softabi": ["-mfloat-abi=softfp"],
}) + select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc_fp16_ieee": ["-mfp16-format=ieee"],
    "//bazel/compiler/gcc:is_arm_gcc_fp16_alt": ["-mfp16-format=alternative"],
}) + select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc_thread_local_storage": ["-mtp=soft"],
}) + select({
    "//conditions:default": [],
    "//bazel/compiler/gcc:is_arm_gcc_secure_firmware": ["-mcmse"],
})
