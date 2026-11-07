# SPDX-License-Identifier: Apache-2.0
#
# BUILD for nrfconnect/sdk-nrfxlib (LicenseRef-Nordic-5-Clause). Prebuilt
# archives link as-is; cc.bzl never whole-archives source .a files.

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_module")
load("@zephyr//modules/nordic_sdk:nordic_sdk.bzl", "nordic_variant_settings", "per_variant")

package(default_visibility = ["//visibility:public"])

exports_files(["zephyr/module.yml"])

nordic_variant_settings()

cc_library(
    name = "mpsl_hdrs",
    hdrs = glob([
        "mpsl/include/**/*.h",
        "mpsl/fem/include/**/*.h",
        "mpsl/fem/*/include/**/*.h",
    ]),
    includes = [
        "mpsl/fem/include",
        "mpsl/fem/include/protocol",
        "mpsl/include",
        "mpsl/include/protocol",
    ],
)

cc_library(
    name = "softdevice_controller_hdrs",
    hdrs = glob(["softdevice_controller/include/**/*.h"]),
    includes = ["softdevice_controller/include"],
)

# MPSL plus every FEM archive for the SoC, as mpsl/fem/CMakeLists.txt links them.
cc_library(
    name = "mpsl_libs",
    srcs = per_variant("mpsl/lib/{soc}/{abi}/libmpsl.a") +
           per_variant("mpsl/fem/*/lib/{soc}/{abi}/libmpsl_fem_*.a"),
)

# SDC calls into MPSL/FEM; depending on mpsl_libs puts SDC first on the
# single-pass link line.
[
    cc_library(
        name = "softdevice_controller_" + role,
        srcs = per_variant(
            "softdevice_controller/lib/{soc}/{abi}/libsoftdevice_controller_" + role + ".a",
        ),
        deps = [":mpsl_libs"],
    )
    for role in [
        "peripheral",
        "central",
        "multirole",
    ]
]

cc_library(
    name = "softdevice_controller_lib",
    deps = select({
        "@zephyr_kconfig//:CONFIG_BT_LL_SOFTDEVICE_PERIPHERAL=true": [":softdevice_controller_peripheral"],
        "@zephyr_kconfig//:CONFIG_BT_LL_SOFTDEVICE_CENTRAL=true": [":softdevice_controller_central"],
        "@zephyr_kconfig//:CONFIG_BT_LL_SOFTDEVICE_MULTIROLE=true": [":softdevice_controller_multirole"],
        "//conditions:default": [],
    }),
)

zephyr_module(
    name = "nrfxlib",
    config = "CONFIG_MPSL",
    deps = [
        ":mpsl_hdrs",
        ":mpsl_libs",
        ":softdevice_controller_hdrs",
        ":softdevice_controller_lib",
    ],
)
