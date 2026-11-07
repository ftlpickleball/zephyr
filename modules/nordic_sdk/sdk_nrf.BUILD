# SPDX-License-Identifier: Apache-2.0
#
# BUILD for the nrfconnect/sdk-nrf SoftDevice Controller + MPSL glue slice
# (sources LicenseRef-Nordic-5-Clause). Mirrors the slice's CMakeLists.txt files.

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_module")

package(default_visibility = ["//visibility:public"])

exports_files(["zephyr/module.yml"])

# nordic,bt-hci-sdc: BT_LL_SOFTDEVICE depends on DT_HAS_NORDIC_BT_HCI_SDC_ENABLED.
filegroup(
    name = "dts_bindings",
    srcs = ["dts/bindings/bluetooth/nordic,bt-hci-sdc.yaml"],
)

# NCS prepends this dir to every compile (drivers/mpsl/clock_control/CMakeLists.txt):
# its nrfx_power_clock.h shadows nrfx's when MPSL owns the clock. Boards list it
# first in hal_soc_headers_library so it wins include order.
cc_library(
    name = "mpsl_clock_override",
    hdrs = ["drivers/mpsl/clock_control/nrfx_power_clock.h"],
    includes = ["drivers/mpsl/clock_control"],
)

# Kconfig symbol -> sources, one filegroup each (zephyr_module allows one select level).
_GATED_SRCS = {
    "CLOCK_CONTROL_MPSL": [
        "drivers/mpsl/clock_control/nrfx_clock_mpsl.c",
        "drivers/mpsl/clock_control/nrfx_power_clock.h",
    ],
    "SOC_FLASH_NRF_RADIO_SYNC_MPSL": ["drivers/mpsl/flash_sync/flash_sync_mpsl.c"],
    "TEMP_NRF5_MPSL": ["drivers/mpsl/temp_nrf5/temp_nrf5_mpsl.c"],
    "BT_LL_SOFTDEVICE": [
        "subsys/bluetooth/controller/hci_driver.c",
        "subsys/bluetooth/controller/hci_internal.c",
        "subsys/bluetooth/controller/hci_internal_wrappers.c",
    ],
    "BT_CTLR_CRYPTO": ["subsys/bluetooth/controller/crypto.c"],
    "BT_CTLR_SDC_CS_MULTIPLE_ANTENNA_SUPPORT": ["subsys/bluetooth/controller/cs_antenna_switch.c"],
}

[
    filegroup(
        name = "srcs_" + sym.lower(),
        srcs = select({
            "@zephyr_kconfig//:CONFIG_{}=true".format(sym): files,
            "//conditions:default": [],
        }),
    )
    for sym, files in _GATED_SRCS.items()
]

zephyr_module(
    name = "nrf",
    srcs = [
        # subsys/mpsl/{init,hwres} (CONFIG_MPSL && !MPSL_FEM_ONLY) + lib/multithreading_lock.
        "subsys/mpsl/init/mpsl_init.c",
        "subsys/mpsl/hwres/mpsl_hwres.c",
        "lib/multithreading_lock/multithreading_lock.c",
    ] + [":srcs_" + sym.lower() for sym in _GATED_SRCS],
    hdrs = glob([
        "include/mpsl/*.h",
        "lib/multithreading_lock/*.h",
        "subsys/bluetooth/controller/*.h",
    ]),
    config = "CONFIG_MPSL",
    includes = [
        "include",
        "lib/multithreading_lock",
        "subsys/bluetooth/controller",
    ],
    deps = ["@nrfxlib//:nrfxlib"],
)
