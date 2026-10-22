# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "headers",
    hdrs = glob(["include/**/*.h"]),
    defines = select({
        "@zephyr_kconfig//:CONFIG_ZCBOR_CANONICAL=true": ["ZCBOR_CANONICAL"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ZCBOR_STOP_ON_ERROR=true": ["ZCBOR_STOP_ON_ERROR"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ZCBOR_VERBOSE=true": ["ZCBOR_VERBOSE"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ZCBOR_ASSERT=true": ["ZCBOR_ASSERTS"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ZCBOR_BIG_ENDIAN=true": ["ZCBOR_BIG_ENDIAN"],
        "//conditions:default": [],
    }),
    includes = ["include"],
)

zephyr_cc_library(
    name = "zcbor",
    srcs = [
        "src/zcbor_common.c",
        "src/zcbor_decode.c",
        "src/zcbor_encode.c",
        "src/zcbor_print.c",
    ],
    local_defines = [
        "_POSIX_C_SOURCE=200809L",
    ],
    deps = [
        ":headers",
    ],
)
