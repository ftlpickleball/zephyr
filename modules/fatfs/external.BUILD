# Copyright 2026 Google LLC
#
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//:cc.bzl", "zephyr_cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "headers",
    hdrs = glob(["include/*.h"]),
    strip_include_prefix = "include",
    deps = [
        "@zephyr//modules/fatfs:fatfs_config",
    ],
)

zephyr_cc_library(
    name = "fatfs",
    srcs = [
        "ff.c",
    ] + select({
        "@zephyr_kconfig//:CONFIG_FS_FATFS_LFN=true": ["option/ffunicode.c"],
        "//conditions:default": [],
    }),
    deps = [
        ":headers",
        "@zephyr//modules/fatfs:zephyr_fatfs_support",
    ],
)
