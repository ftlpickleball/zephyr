# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

label_flag(
    name = "mbedtls_config",
    build_setting_default = "@zephyr//modules/mbedtls:mbedtls_config",
)

cc_library(
    name = "headers",
    hdrs = glob(
        [
            "include/**/*.h",
            "library/*.h",
        ],
        exclude = ["include/mbedtls/mbedtls_config.h"],
    ),
    includes = [
        "include",
        "library",
    ],
    deps = [
        ":mbedtls_config",
        "@tf_psa_crypto//:headers",
    ],
)

cc_library(
    name = "mbedtls_core",
    features = ["zephyr_warning_suppressions"],
    srcs = glob(["library/*.c"]),
    deps = [
        ":headers",
        "@tf_psa_crypto",
    ],
)

cc_library(
    name = "mbedtls",
    deps = [
        ":mbedtls_core",
        "@tf_psa_crypto",
        "@zephyr//modules/mbedtls:zephyr_mbedtls_support",
    ],
)
