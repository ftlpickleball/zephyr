# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "legacy_private_headers",
    hdrs = [
        "drivers/builtin/include/mbedtls/private/aes.h",
        "drivers/builtin/include/mbedtls/private/bignum.h",
        "drivers/builtin/include/mbedtls/private/cipher.h",
        "drivers/builtin/include/mbedtls/private/cmac.h",
        "drivers/builtin/include/mbedtls/private/ecdsa.h",
        "drivers/builtin/include/mbedtls/private/ecp.h",
        "drivers/builtin/include/mbedtls/private/error_common.h",
        "drivers/builtin/include/mbedtls/private/pkcs5.h",
        "drivers/builtin/include/mbedtls/private/rsa.h",
        "drivers/builtin/include/mbedtls/private/sha256.h",
    ],
    include_prefix = "mbedtls",
    strip_include_prefix = "drivers/builtin/include/mbedtls/private",
)

cc_library(
    name = "headers",
    hdrs = glob([
        "core/*.h",
        "dispatch/*.h",
        "drivers/builtin/include/**/*.h",
        "drivers/builtin/src/*.h",
        "drivers/everest/include/**/*.h",
        "drivers/p256-m/**/*.h",
        "drivers/pqcp/include/**/*.h",
        "drivers/pqcp/src/*.h",
        "extras/*.h",
        "include/**/*.h",
        "platform/*.h",
        "utilities/*.h",
    ]),
    includes = [
        "core",
        "dispatch",
        "drivers/builtin/include",
        "drivers/builtin/src",
        "drivers/everest/include",
        "drivers/everest/include/tf-psa-crypto/private/everest",
        "drivers/everest/include/tf-psa-crypto/private/everest/kremlib",
        "drivers/p256-m",
        "drivers/p256-m/p256-m",
        "drivers/pqcp/include",
        "drivers/pqcp/src",
        "extras",
        "include",
        "platform",
        "utilities",
    ],
    deps = [
        "@mbedtls//:mbedtls_config",
    ] + select({
        "@zephyr_kconfig//:CONFIG_MBEDTLS_DECLARE_PRIVATE_IDENTIFIERS=true": [
            ":legacy_private_headers",
        ],
        "//conditions:default": [],
    }),
)

cc_library(
    name = "tf_psa_crypto",
    srcs = glob([
        "core/*.c",
        "drivers/builtin/src/*.c",
        "drivers/pqcp/src/*.c",
        "extras/*.c",
        "platform/*.c",
        "utilities/*.c",
    ]) + [
        "drivers/code_share.c",
        "drivers/everest/library/Hacl_Curve25519_joined.c",
        "drivers/everest/library/x25519.c",
        "drivers/p256-m/p256-m/p256-m.c",
        "drivers/p256-m/p256-m_driver_entrypoints.c",
    ],
    features = ["zephyr_warning_suppressions"],
    local_defines = [
        "BUILDING_MBEDTLS_CRYPTO",
    ],
    deps = [
        ":headers",
    ],
)
