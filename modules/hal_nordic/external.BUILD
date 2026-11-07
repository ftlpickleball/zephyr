# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:selects.bzl", "selects")
load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_module")
load("@zephyr//modules/hal_nordic:nrfx_cmake.bzl", "nrfx_compile_definitions", "nrfx_driver_filegroups")

package(default_visibility = ["//visibility:public"])

exports_files(["zephyr/module.yml"])


_NORDIC_INCLUDES = [
    ".",
    "nrfx",
    "nrfx/drivers/include",
    "nrfx/hal",
    "nrfx/haly",
    "nrfx/helpers",
    "nrfx/bsp/stable",
    "nrfx/bsp/stable/mdk",
    "nrfx/bsp/stable/templates",
]

# MDK compile definitions: generated from nrfx/CMakeLists.txt, plus the one
# CMake derives from devicetree (nrfx/CMakeLists.txt:233-240: /clocks/hfpll is
# 128 MHz on every nRF54L dtsi).
_CHIP_DEFINES = nrfx_compile_definitions() + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54L_CPUAPP_COMMON=true": ["NRF_CONFIG_CPU_FREQ_MHZ=128"],
    "//conditions:default": [],
})

cc_library(
    name = "dt_interface",
    hdrs = glob(["nrfx/**/*.h"], allow_empty = True),
    textual_hdrs = glob(["nrfx/bsp/**/*.c"], allow_empty = True),
    includes = _NORDIC_INCLUDES,
    defines = _CHIP_DEFINES,
    # nrfx_reserved_resources.h includes <bt_ctlr_used_resources.h> from the SW
    # controller's nrfx_glue dir when the Nordic LLL is built.
    deps = [
        "@zephyr//modules/hal_nordic/nrfx:nrfx_hdrs",
    ] + select({
        "@zephyr_kconfig//:CONFIG_BT_LLL_VENDOR_NORDIC=true": [
            "@zephyr//subsys/bluetooth/controller/ll_sw/nordic:hdrs",
        ],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "nrfx_system_srcs",
    srcs = select({
        "@zephyr_kconfig//:CONFIG_SOC_NRF5340_CPUAPP=true": ["nrfx/bsp/stable/mdk/system_nrf5340_application.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF5340_CPUNET=true": ["nrfx/bsp/stable/mdk/system_nrf5340_network.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52805=true": ["nrfx/bsp/stable/mdk/system_nrf52805.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52810=true": ["nrfx/bsp/stable/mdk/system_nrf52810.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52811=true": ["nrfx/bsp/stable/mdk/system_nrf52811.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52820=true": ["nrfx/bsp/stable/mdk/system_nrf52820.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52832=true": ["nrfx/bsp/stable/mdk/system_nrf52.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52833=true": ["nrfx/bsp/stable/mdk/system_nrf52833.c"],
        "@zephyr_kconfig//:CONFIG_SOC_NRF52840=true": ["nrfx/bsp/stable/mdk/system_nrf52840.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF51=true": ["nrfx/bsp/stable/mdk/system_nrf51.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF54H=true": ["nrfx/bsp/stable/mdk/system_nrf54h.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF54L=true": ["nrfx/bsp/stable/mdk/system_nrf54l.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF71=true": ["nrfx/bsp/stable/mdk/system_nrf7120_enga.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF91=true": ["nrfx/bsp/stable/mdk/system_nrf91.c"],
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF92=true": ["nrfx/bsp/stable/mdk/system_nrf92.c"],
        "//conditions:default": [],
    }),
)

config_setting(
    name = "not_config_nrfx_gppi_v1",
    flag_values = {
        "@zephyr_kconfig//:CONFIG_NRFX_GPPI_V1": "false",
    },
)

selects.config_setting_group(
    name = "gppi_ppi_enabled",
    match_all = [
        "@zephyr_kconfig//:CONFIG_NRFX_GPPI=true",
        "@zephyr_kconfig//:CONFIG_HAS_HW_NRF_PPI=true",
        ":not_config_nrfx_gppi_v1",
    ],
)

selects.config_setting_group(
    name = "gppi_dppi_enabled",
    match_all = [
        "@zephyr_kconfig//:CONFIG_NRFX_GPPI=true",
        "@zephyr_kconfig//:CONFIG_HAS_HW_NRF_DPPIC=true",
        ":not_config_nrfx_gppi_v1",
    ],
)

# nrfx/CMakeLists.txt: GPPI && !GPPI_V1 && (SOC_COMPATIBLE_NRF54LX || SOC_SERIES_NRF71).
selects.config_setting_group(
    name = "d2ppi_soc",
    match_any = [
        "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF54LX=true",
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF71=true",
    ],
)

selects.config_setting_group(
    name = "gppi_d2ppi_enabled",
    match_all = [
        "@zephyr_kconfig//:CONFIG_NRFX_GPPI=true",
        ":not_config_nrfx_gppi_v1",
        ":d2ppi_soc",
    ],
)

filegroup(
    name = "nrfx_helper_srcs",
    srcs = [
        "nrfx/helpers/nrfx_flag32_allocator.c",
    ] + select({
        ":gppi_ppi_enabled": ["nrfx/helpers/nrfx_gppi_ppi.c"],
        "//conditions:default": [],
    }) + select({
        ":gppi_dppi_enabled": ["nrfx/helpers/nrfx_gppi_dppi.c"],
        "//conditions:default": [],
    }) + select({
        ":gppi_d2ppi_enabled": ["nrfx/bsp/soc/interconnect/nrfx_gppi_d2ppi.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_HAS_NORDIC_RAM_CTRL=true": ["nrfx/helpers/nrfx_ram_ctrl.c"],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "nrfx_driver_srcs",
    # One filegroup per CONFIG_NRFX_* source line in nrfx/CMakeLists.txt (generated).
    srcs = nrfx_driver_filegroups("nrfx_driver_srcs") + select({
        ":twi_or_twim_enabled": ["nrfx/drivers/src/nrfx_twi_twim.c"],
        "//conditions:default": [],
    }),
)

selects.config_setting_group(
    name = "twi_or_twim_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_NRFX_TWI=true",
        "@zephyr_kconfig//:CONFIG_NRFX_TWIM=true",
    ],
)

zephyr_module(
    name = "hal_nordic",
    srcs = [
        ":nrfx_system_srcs",
        ":nrfx_helper_srcs",
        ":nrfx_driver_srcs",
        "@zephyr//modules/hal_nordic/nrfx:nrfx_srcs",
    ],
    config = "CONFIG_HAS_NRFX",
    deps = [
        ":dt_interface",
        "@zephyr//modules/hal_nordic/nrfx:nrfx_hdrs",
    ],
)
