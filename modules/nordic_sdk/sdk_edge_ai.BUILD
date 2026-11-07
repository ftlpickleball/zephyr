# SPDX-License-Identifier: Apache-2.0
#
# BUILD for the nrfconnect/sdk-edge-ai Axon NPU slice (LicenseRef-Nordic-5-Clause).
# Mirrors drivers/axon, lib/axon and lib/axon/platform CMakeLists.txt (Zephyr branch).

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_module")

package(default_visibility = ["//visibility:public"])

exports_files(["zephyr/module.yml"])

# lib/axon/CMakeLists.txt: the -fpu archive when CONFIG_FPU, else the plain one.
cc_library(
    name = "axon_driver_internal",
    srcs = select({
        "@zephyr_kconfig//:CONFIG_FPU=true": ["lib/axon/bin/arm/libnrf-axon-driver-internal-fpu.a"],
        "//conditions:default": ["lib/axon/bin/arm/libnrf-axon-driver-internal.a"],
    }),
)

# Global defines from lib/axon/platform/CMakeLists.txt; values resolve from autoconf.h
# (sizes default 0 = buffer unused; region name is already a string literal).
_BUFFER_DEFINES = [
    "NRF_AXON_INTERLAYER_BUFFER_SIZE=CONFIG_NRF_AXON_INTERLAYER_BUFFER_SIZE",
    "NRF_AXON_PSUM_BUFFER_SIZE=CONFIG_NRF_AXON_PSUM_BUFFER_SIZE",
    "NRF_AXON_INTERLAYER_BUFFER_MEMREGION=CONFIG_NRF_AXON_INTERLAYER_BUFFER_MEMREGION_NAME",
]

zephyr_module(
    name = "edge_ai",
    srcs = [
        "drivers/axon/nrf_axon_nn_infer.c",
        "drivers/axon/nrf_axon_nn_infer_test.c",
        "drivers/axon/nrf_axon_nn_op_extensions.c",
        "drivers/axon/nrf_axon_nn_op_extensions_const.h",
        "lib/axon/platform/src/nrf_axon_logging.c",
        "lib/axon/platform/src/nrf_axon_vector_compare.c",
        "lib/axon/platform/src/zephyr/nrf_axon_platform_zephyr.c",
    ],
    hdrs = glob([
        "include/axon/*.h",
        "include/drivers/axon/*.h",
    ]),
    config = "CONFIG_NRF_AXON",
    defines = _BUFFER_DEFINES,
    includes = ["include"],
    deps = [":axon_driver_internal"],
)
