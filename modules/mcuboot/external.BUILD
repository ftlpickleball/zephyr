# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:selects.bzl", "selects")
load("@rules_cc//cc:defs.bzl", "cc_library")
load("@rules_python//python:defs.bzl", "py_binary")
load("@zephyr//:cc.bzl", "zephyr_app", "zephyr_cc_library")

package(default_visibility = ["//visibility:public"])

exports_files([
    "boot/zephyr/prj.conf",
    "zephyr/module.yml",
    "scripts/imgtool.py",
    "root-rsa-2048.pem",
    "root-rsa-3072.pem",
    "root-ec-p256.pem",
    "root-ec-p384.pem",
    "root-ed25519.pem",
    "enc-rsa2048-pub.pem",
    "enc-rsa2048-priv.pem",
    "enc-ec256-pub.pem",
    "enc-ec256-priv.pem",
    "enc-x25519-pub.pem",
    "enc-x25519-priv.pem",
])

filegroup(
    name = "boot_zephyr_hdrs",
    srcs = glob(["boot/zephyr/include/**/*.h"]),
)

# ------------------------------------------------------------------------------
# imgtool binary
# ------------------------------------------------------------------------------
py_binary(
    name = "imgtool",
    srcs = ["scripts/imgtool.py"] + glob(["scripts/imgtool/**/*.py"]),
    imports = ["scripts"],
    main = "scripts/imgtool.py",
    deps = [
        "@zephyr_pip_deps//cbor2",
        "@zephyr_pip_deps//click",
        "@zephyr_pip_deps//cryptography",
        "@zephyr_pip_deps//intelhex",
        "@zephyr_pip_deps//pyyaml",
    ],
)

# ------------------------------------------------------------------------------
# MCUboot Signing Key & Public Key Code Generation
# ------------------------------------------------------------------------------
label_flag(
    name = "mcuboot_key",
    build_setting_default = ":default_key",
)

filegroup(
    name = "default_key",
    srcs = ["root-rsa-2048.pem"],
)

genrule(
    name = "autogen_pubkey",
    srcs = [":mcuboot_key"],
    outs = ["autogen-pubkey.c"],
    cmd = "$(execpath :imgtool) getpub -k $(location :mcuboot_key) > $@",
    tools = [":imgtool"],
)

# ------------------------------------------------------------------------------
# Cryptographic Backends
# ------------------------------------------------------------------------------
zephyr_cc_library(
    name = "tinycrypt",
    srcs = glob([
        "ext/tinycrypt/lib/source/*.c",
        "ext/tinycrypt-sha512/lib/source/*.c",
        "ext/mbedtls-asn1/src/*.c",
    ]),
    copts = [
        "-DMBEDTLS_CONFIG_FILE=\"mcuboot-mbedtls-cfg.h\"",
    ],
    hdrs = glob([
        "ext/tinycrypt/lib/include/**/*.h",
        "ext/tinycrypt-sha512/lib/include/**/*.h",
        "ext/mbedtls-asn1/include/**/*.h",
    ]) + [
        ":boot_zephyr_hdrs",
    ],
    includes = [
        "ext/tinycrypt/lib/include",
        "ext/tinycrypt/lib/source",
        "ext/tinycrypt-sha512/lib/include",
        "ext/mbedtls-asn1/include",
        "boot/zephyr/include",
    ],
)

zephyr_cc_library(
    name = "crypto_backend",
    deps = select({
        "@zephyr_kconfig//:CONFIG_BOOT_USE_MBEDTLS=true": ["@zephyr//modules/mcuboot:mbedtls"],
        "@zephyr_kconfig//:CONFIG_BOOT_USE_PSA_CRYPTO=true": ["@zephyr//modules/mcuboot:mbedtls"],
        "@zephyr_kconfig//:CONFIG_BOOT_USE_TINYCRYPT=true": [":tinycrypt"],
        "//conditions:default": [],
    }),
)

# ------------------------------------------------------------------------------
# Application-facing mcuboot_util (CONFIG_MCUBOOT_BOOTUTIL_LIB=y)
# ------------------------------------------------------------------------------
cc_library(
    name = "headers",
    hdrs = glob([
        "boot/bootutil/include/**/*.h",
        "boot/bootutil/src/**/*.h",
    ]) + [
        ":boot_zephyr_hdrs",
    ],
    includes = [
        "boot/bootutil",
        "boot/bootutil/include",
        "boot/bootutil/src",
        "boot/zephyr/include",
    ],
)

zephyr_cc_library(
    name = "mcuboot_util",
    srcs = ["boot/bootutil/src/bootutil_public.c"],
    deps = [
        ":crypto_backend",
        ":headers",
    ],
)

# ------------------------------------------------------------------------------
# Core bootutil Library (Bootloader verification & staging)
# ------------------------------------------------------------------------------
zephyr_cc_library(
    name = "bootutil",
    srcs = [
        "boot/bootutil/src/boot_record.c",
        "boot/bootutil/src/bootutil_area.c",
        "boot/bootutil/src/bootutil_find_key.c",
        "boot/bootutil/src/bootutil_img_hash.c",
        "boot/bootutil/src/bootutil_img_security_cnt.c",
        "boot/bootutil/src/bootutil_loader.c",
        "boot/bootutil/src/bootutil_misc.c",
        "boot/bootutil/src/caps.c",
        "boot/bootutil/src/encrypted.c",
        "boot/bootutil/src/fault_injection_hardening.c",
        "boot/bootutil/src/image_validate.c",
        "boot/bootutil/src/tlv.c",
    ] + select({
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD=true": [],
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT=true": [],
        "//conditions:default": [
            "boot/bootutil/src/loader.c",
            "boot/bootutil/src/swap_misc.c",
        ],
    }) + select({
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_RSA=true": [
            "boot/bootutil/src/image_rsa.c",
        ],
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=true": [
            "boot/bootutil/src/image_ecdsa.c",
        ],
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_ED25519=true": [
            "boot/bootutil/src/image_ed25519.c",
            "ext/fiat/src/curve25519.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_BOOT_RAM_LOAD=true": [
            "boot/bootutil/src/ram_load.c",
        ],
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD=true": [
            "boot/bootutil/src/ram_load.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD=true": [],
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT=true": [],
        "@zephyr_kconfig//:CONFIG_BOOT_SWAP_USING_MOVE=true": [
            "boot/bootutil/src/swap_move.c",
        ],
        "@zephyr_kconfig//:CONFIG_BOOT_SWAP_USING_OFFSET=true": [
            "boot/bootutil/src/swap_offset.c",
        ],
        "//conditions:default": [
            "boot/bootutil/src/swap_scratch.c",
        ],
    }),
    hdrs = glob([
        "ext/fiat/src/*.h",
    ]),
    includes = [
        "ext/fiat/src",
    ],
    local_defines = [
        "ZEPHYR_VER_INCLUDE=1",
    ],
    deps = [
        ":crypto_backend",
        ":mcuboot_util",
    ],
)

# ------------------------------------------------------------------------------
# Architecture Handoff & Core Cleanup Backends
# ------------------------------------------------------------------------------
zephyr_cc_library(
    name = "arch_cleanup",
    srcs = select({
        "@zephyr_kconfig//:CONFIG_CPU_CORTEX_M=true": [
            "boot/zephyr/cleanup/arm_cortex_m.c",
        ],
        "@zephyr_kconfig//:CONFIG_ARMV7_R=true": [
            "boot/zephyr/cleanup/arm_cortex_r.c",
        ],
        "//conditions:default": [],
    }),
    deps = [":bootutil"],
)

# ------------------------------------------------------------------------------
# Platform-specific MCUboot Hooks
# ------------------------------------------------------------------------------
label_flag(
    name = "mcuboot_hooks",
    build_setting_default = "@zephyr//modules/mcuboot:mcuboot_hooks",
)

selects.config_setting_group(
    name = "has_mcuboot_hooks",
    match_any = [
        "@zephyr_kconfig//:CONFIG_BOOT_FLASH_AREA_HOOKS=true",
        "@zephyr_kconfig//:CONFIG_BOOT_GO_HOOKS=true",
        "@zephyr_kconfig//:CONFIG_BOOT_IMAGE_ACCESS_HOOKS=true",
        "@zephyr_kconfig//:CONFIG_FIND_NEXT_SLOT_HOOKS=true",
        "@zephyr_kconfig//:CONFIG_MCUBOOT_ACTION_HOOKS=true",
    ],
)

# ------------------------------------------------------------------------------
# Standard Upstream MCUboot Bootloader App
# ------------------------------------------------------------------------------
zephyr_cc_library(
    name = "mcuboot_main",
    srcs = [
        "boot/zephyr/flash_map_extended.c",
        "boot/zephyr/io.c",
        "boot/zephyr/keys.c",
        "boot/zephyr/main.c",
        "boot/zephyr/os.c",
        "boot/zephyr/watchdog.c",
    ] + select({
        "@zephyr_kconfig//:CONFIG_BOOT_SHARE_BACKEND_RETENTION=true": ["boot/zephyr/shared_data.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD=true": [
            "boot/zephyr/single_loader.c",
        ],
        "@zephyr_kconfig//:CONFIG_SINGLE_APPLICATION_SLOT=true": [
            "boot/zephyr/single_loader.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_MULTIPLE_EXECUTABLE_RAM_REGIONS_DEFAULT_FILE=true": [
            "boot/zephyr/ram_load.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_RSA=true": [":autogen_pubkey"],
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=true": [":autogen_pubkey"],
        "@zephyr_kconfig//:CONFIG_BOOT_SIGNATURE_TYPE_ED25519=true": [":autogen_pubkey"],
        "//conditions:default": [],
    }),
    hdrs = [":boot_zephyr_hdrs"],
    includes = ["boot/zephyr/include"],
    deps = [
        ":bootutil",
        ":crypto_backend",
    ] + select({
        "@zephyr_kconfig//:CONFIG_MCUBOOT_CLEANUP_ARM_CORE=true": [":arch_cleanup"],
        "//conditions:default": [],
    }),
)

zephyr_app(
    name = "mcuboot",
    deps = [
        ":mcuboot_main",
    ] + select({
        ":has_mcuboot_hooks": [":mcuboot_hooks"],
        "//conditions:default": [],
    }),
)
