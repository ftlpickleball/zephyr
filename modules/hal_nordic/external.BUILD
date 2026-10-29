# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:selects.bzl", "selects")
load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_module")

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

# Mirrors MDK compile definitions from modules/hal_nordic/nrfx/CMakeLists.txt (lines 39-115).
_CHIP_DEFINES = select({
    "@zephyr_kconfig//:CONFIG_SOC_SERIES_NRF51=true": ["NRF51"],
    "//conditions:default": [],
}) + select({
    # nrfx/CMakeLists.txt maps CONFIG_SOC_NRF51822_QF* to NRF51422_XX* (lines 40-42).
    "@zephyr_kconfig//:CONFIG_SOC_NRF51822_QFAA=true": ["NRF51422_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF51822_QFAB=true": ["NRF51422_XXAB"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF51822_QFAC=true": ["NRF51422_XXAC"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52805=true": ["NRF52805_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52810=true": ["NRF52810_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52811=true": ["NRF52811_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52820=true": ["NRF52820_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52832=true": ["NRF52832_XXAA"],
    "//conditions:default": [],
}) + select({
    # nrfx/CMakeLists.txt uses CONFIG_SOC_COMPATIBLE_* for MDK defines (line 48)
    # while gating system_nrf52833.c on CONFIG_SOC_NRF52833 (line 124).
    "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF52833=true": ["NRF52833_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF52840=true": ["NRF52840_XXAA"],
    "//conditions:default": [],
}) + select({
    # nrfx/CMakeLists.txt lines 50-51 & 109-110 (compatible targets share MDK defines).
    "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF5340_CPUAPP=true": [
        "NRF5340_XXAA_APPLICATION",
        "NRF_SKIP_FICR_NS_COPY_TO_RAM",
    ],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF5340_CPUNET=true": [
        "NRF5340_XXAA_NETWORK",
    ],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54H20_CPUAPP=true": [
        "NRF54H20_XXAA",
        "NRF_APPLICATION",
    ],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54H20_CPURAD=true": [
        "NRF54H20_XXAA",
        "NRF_RADIOCORE",
    ],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54H20_CPUPPR=true": [
        "NRF54H20_XXAA",
        "NRF_PPR",
    ],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54H20_CPUFLPR=true": [
        "NRF54H20_XXAA",
        "NRF_FLPR",
    ],
    "//conditions:default": [],
}) + select({
    # nrfx/CMakeLists.txt lines 68-70 (SOC_COMPATIBLE_NRF54L15_CPUFLPR does not exist in Kconfig).
    "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF54L15=true": ["NRF54L15_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_COMPATIBLE_NRF54L15_CPUAPP=true": ["NRF_APPLICATION"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF54L15_CPUFLPR=true": ["NRF_FLPR"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF7120_ENGA=true": ["NRF7120_ENGA_XXAA"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF7120_ENGA_CPUAPP=true": ["NRF_APPLICATION"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF7120_ENGA_CPUFLPR=true": ["NRF_FLPR"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_SOC_NRF9160=true": ["NRF9160_XXAA", "NRF_SKIP_FICR_NS_COPY_TO_RAM"],
    "//conditions:default": [],
}) + select({
    "@zephyr_kconfig//:CONFIG_ARM_NONSECURE_FIRMWARE=true": ["NRF_TRUSTZONE_NONSECURE"],
    "//conditions:default": [],
})

cc_library(
    name = "dt_interface",
    hdrs = glob(["nrfx/**/*.h"], allow_empty = True),
    textual_hdrs = glob(["nrfx/bsp/**/*.c"], allow_empty = True),
    includes = _NORDIC_INCLUDES,
    defines = _CHIP_DEFINES,
    deps = [
        "@zephyr//modules/hal_nordic/nrfx:nrfx_hdrs",
    ],
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
        "@zephyr_kconfig//:CONFIG_HAS_NORDIC_RAM_CTRL=true": ["nrfx/helpers/nrfx_ram_ctrl.c"],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "nrfx_driver_srcs",
    srcs = select({
        "@zephyr_kconfig//:CONFIG_NRFX_CLOCK=true": [
            "nrfx/drivers/src/nrfx_clock.c",
            "nrfx/drivers/src/nrfx_clock_hfclk.c",
            "nrfx/drivers/src/nrfx_clock_hfclkaudio.c",
            "nrfx/drivers/src/nrfx_clock_hfclk192m.c",
            "nrfx/drivers/src/nrfx_clock_lfclk.c",
            "nrfx/drivers/src/nrfx_clock_xo.c",
            "nrfx/drivers/src/nrfx_clock_xo24m.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_GPIOTE=true": ["nrfx/drivers/src/nrfx_gpiote.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_IPC=true": ["nrfx/drivers/src/nrfx_ipc.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_POWER=true": ["nrfx/drivers/src/nrfx_power.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_PPI=true": ["nrfx/drivers/src/nrfx_ppi.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_DPPI=true": ["nrfx/drivers/src/nrfx_dppi.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_TIMER=true": ["nrfx/drivers/src/nrfx_timer.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_RTC=true": ["nrfx/drivers/src/nrfx_rtc.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_RNG=true": ["nrfx/drivers/src/nrfx_rng.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_WDT=true": ["nrfx/drivers/src/nrfx_wdt.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_UART=true": ["nrfx/drivers/src/nrfx_uart.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_UARTE=true": ["nrfx/drivers/src/nrfx_uarte.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_NVMC=true": ["nrfx/drivers/src/nrfx_nvmc.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_PDM=true": ["nrfx/drivers/src/nrfx_pdm.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_TWI=true": ["nrfx/drivers/src/nrfx_twi.c"],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_NRFX_TWIM=true": ["nrfx/drivers/src/nrfx_twim.c"],
        "//conditions:default": [],
    }) + select({
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
