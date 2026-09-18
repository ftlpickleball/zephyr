# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//lib:selects.bzl", "selects")
load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_cc_library")

package(default_visibility = ["//visibility:public"])

exports_files(["zephyr/module.yml"])

_PERIPH_INCLUDES = [
    "MAX/Include",
    "MAX/Libraries/PeriphDrivers/Source/ADC",
    "MAX/Libraries/PeriphDrivers/Source/AES",
    "MAX/Libraries/PeriphDrivers/Source/CAN",
    "MAX/Libraries/PeriphDrivers/Source/CRC",
    "MAX/Libraries/PeriphDrivers/Source/CTB",
    "MAX/Libraries/PeriphDrivers/Source/DMA",
    "MAX/Libraries/PeriphDrivers/Source/EMCC",
    "MAX/Libraries/PeriphDrivers/Source/FLC",
    "MAX/Libraries/PeriphDrivers/Source/GPIO",
    "MAX/Libraries/PeriphDrivers/Source/HPB",
    "MAX/Libraries/PeriphDrivers/Source/I2C",
    "MAX/Libraries/PeriphDrivers/Source/I2S",
    "MAX/Libraries/PeriphDrivers/Source/ICC",
    "MAX/Libraries/PeriphDrivers/Source/LP",
    "MAX/Libraries/PeriphDrivers/Source/LPCMP",
    "MAX/Libraries/PeriphDrivers/Source/OWM",
    "MAX/Libraries/PeriphDrivers/Source/PT",
    "MAX/Libraries/PeriphDrivers/Source/RTC",
    "MAX/Libraries/PeriphDrivers/Source/SDHC",
    "MAX/Libraries/PeriphDrivers/Source/SEMA",
    "MAX/Libraries/PeriphDrivers/Source/SIMO",
    "MAX/Libraries/PeriphDrivers/Source/SPI",
    "MAX/Libraries/PeriphDrivers/Source/SPIXF",
    "MAX/Libraries/PeriphDrivers/Source/SPIXR",
    "MAX/Libraries/PeriphDrivers/Source/SYS",
    "MAX/Libraries/PeriphDrivers/Source/TMR",
    "MAX/Libraries/PeriphDrivers/Source/TRNG",
    "MAX/Libraries/PeriphDrivers/Source/UART",
    "MAX/Libraries/PeriphDrivers/Source/WDT",
    "MAX/Libraries/PeriphDrivers/Source/WUT",
]

_COMMON_DEFINES = [
    "TARGET_REV=0x4131",
    "MSDK_NO_GPIO_CLK_INIT=1",
    "MSDK_NO_LOCKING=1",
]

_MAX32655_INCLUDES = _PERIPH_INCLUDES + [
    "MAX/Libraries/CMSIS/Device/Maxim/MAX32655/Include",
    "MAX/Libraries/PeriphDrivers/Include/MAX32655",
    "MAX/Source/MAX32655",
]

_MAX32690_INCLUDES = _PERIPH_INCLUDES + [
    "MAX/Libraries/CMSIS/Device/Maxim/MAX32690/Include",
    "MAX/Libraries/PeriphDrivers/Include/MAX32690",
    "MAX/Source/MAX32690",
]

_MAX78002_INCLUDES = _PERIPH_INCLUDES + [
    "MAX/Libraries/CMSIS/Device/Maxim/MAX78002/Include",
    "MAX/Libraries/PeriphDrivers/Include/MAX78002",
    "MAX/Source/MAX78002",
]

selects.config_setting_group(
    name = "flc_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_SOC_FLASH_MAX32=true",
        "@zephyr_kconfig//:CONFIG_HWINFO_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "rtc_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_COUNTER_RTC_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "gpio_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_GPIO_MAX32=true",
        "@zephyr_kconfig//:CONFIG_PINCTRL_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "tmr_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_PWM_MAX32=true",
        "@zephyr_kconfig//:CONFIG_COUNTER_TIMER_MAX32=true",
        "@zephyr_kconfig//:CONFIG_MAX32_RV32_SYS_TIMER=true",
    ],
)

selects.config_setting_group(
    name = "max32655_aes_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_BT=true",
        "@zephyr_kconfig//:CONFIG_HWINFO_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "max32690_ctb_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_HWINFO_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "max78002_aes_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_HWINFO_MAX32=true",
    ],
)

selects.config_setting_group(
    name = "max78002_trng_enabled",
    match_any = [
        "@zephyr_kconfig//:CONFIG_ENTROPY_MAX32_TRNG=true",
        "@zephyr_kconfig//:CONFIG_HWINFO_MAX32=true",
    ],
)

# --- MAX32655 ---

cc_library(
    name = "max32655_arm_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX32655"] + _COMMON_DEFINES,
    includes = _MAX32655_INCLUDES,
    deps = [
        "@zephyr//modules/cmsis_6",
    ],
)

cc_library(
    name = "max32655_riscv_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX32655"] + _COMMON_DEFINES,
    includes = _MAX32655_INCLUDES + ["MAX/Libraries/CMSIS/Include"],
)

alias(
    name = "max32655_hdrs",
    actual = ":max32655_arm_hdrs",
)

filegroup(
    name = "max32655_common_srcs",
    srcs = [
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/LP/lp_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SEMA/sema_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/SEMA/sema_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SIMO/simo_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/SIMO/simo_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_assert.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_delay.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/pins_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/sys_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_me17.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_reva.c",
        "MAX/Source/MAX32655/max32xxx_system.c",
    ] + select({
        ":gpio_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_common.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":tmr_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_common.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_UART_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_common.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_SPI_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_reva1.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2C_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2S_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_WDT_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_common.c",
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":rtc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":flc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_common.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ADC_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_W1_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ENTROPY_MAX32_TRNG=true": [
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":max32655_aes_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/AES/aes_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/AES/aes_revb.c",
        ],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "max32655_arm_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX32655/Source/system_max32655.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_lock.c",
        ":max32655_common_srcs",
    ],
)

filegroup(
    name = "max32655_riscv_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX32655/Source/system_riscv_max32655.c",
        ":max32655_common_srcs",
    ],
)

# --- MAX32690 ---

cc_library(
    name = "max32690_arm_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX32690"] + _COMMON_DEFINES,
    includes = _MAX32690_INCLUDES,
    deps = [
        "@zephyr//modules/cmsis_6",
    ],
)

cc_library(
    name = "max32690_riscv_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX32690"] + _COMMON_DEFINES,
    includes = _MAX32690_INCLUDES + ["MAX/Libraries/CMSIS/Include"],
)

alias(
    name = "max32690_hdrs",
    actual = ":max32690_arm_hdrs",
)

filegroup(
    name = "max32690_common_srcs",
    srcs = [
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/EMCC/emcc_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/EMCC/emcc_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/HPB/hpb_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/HPB/hpb_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/LP/lp_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SEMA/sema_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/SEMA/sema_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SPIXF/spixf_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/SPIXF/spixf_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SPIXR/spixr_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/SPIXR/spixr_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_assert.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_delay.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/pins_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/sys_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_me18.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_reva.c",
        "MAX/Source/MAX32690/max32xxx_system.c",
    ] + select({
        ":gpio_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_common.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":tmr_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_common.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_UART_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_common.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_SPI_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_reva1.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2C_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2S_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_WDT_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_common.c",
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":rtc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":flc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_common.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ADC_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_W1_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ENTROPY_MAX32_TRNG=true": [
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":max32690_ctb_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/CTB/ctb_common.c",
            "MAX/Libraries/PeriphDrivers/Source/CTB/ctb_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/CTB/ctb_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_CAN_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/CAN/can_me18.c",
            "MAX/Libraries/PeriphDrivers/Source/CAN/can_reva.c",
        ],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "max32690_arm_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX32690/Source/system_max32690.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_lock.c",
        ":max32690_common_srcs",
    ],
)

filegroup(
    name = "max32690_riscv_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX32690/Source/system_riscv_max32690.c",
        ":max32690_common_srcs",
    ],
)

# --- MAX78002 ---

cc_library(
    name = "max78002_arm_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX78002"] + _COMMON_DEFINES,
    includes = _MAX78002_INCLUDES,
    deps = [
        "@zephyr//modules/cmsis_6",
    ],
)

cc_library(
    name = "max78002_riscv_hdrs",
    hdrs = glob(["MAX/**/*.h"]),
    defines = ["TARGET=MAX78002"] + _COMMON_DEFINES,
    includes = _MAX78002_INCLUDES + ["MAX/Libraries/CMSIS/Include"],
)

alias(
    name = "max78002_hdrs",
    actual = ":max78002_arm_hdrs",
)

filegroup(
    name = "max78002_common_srcs",
    srcs = [
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/DMA/dma_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/ICC/icc_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/LP/lp_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/LPCMP/lpcmp_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/PT/pt_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SDHC/sdhc_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/SDHC/sdhc_reva.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_assert.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_delay.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/pins_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/sys_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_ai87.c",
        "MAX/Libraries/PeriphDrivers/Source/WUT/wut_reva.c",
        "MAX/Source/MAX78002/max78xxx_system.c",
    ] + select({
        ":gpio_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_common.c",
            "MAX/Libraries/PeriphDrivers/Source/GPIO/gpio_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":tmr_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_common.c",
            "MAX/Libraries/PeriphDrivers/Source/TMR/tmr_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_UART_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_common.c",
            "MAX/Libraries/PeriphDrivers/Source/UART/uart_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_SPI_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/SPI/spi_reva1.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2C_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/I2C/i2c_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_I2S_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/I2S/i2s_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_WDT_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_common.c",
            # MAX78002 (TARGET_NUM == 78002) shares wdt_me17.c in hal_adi.
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_me17.c",
            "MAX/Libraries/PeriphDrivers/Source/WDT/wdt_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":rtc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/RTC/rtc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":flc_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_common.c",
            "MAX/Libraries/PeriphDrivers/Source/FLC/flc_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_ADC_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/ADC/adc_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        "@zephyr_kconfig//:CONFIG_W1_MAX32=true": [
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/OWM/owm_reva.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":max78002_trng_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/TRNG/trng_revb.c",
        ],
        "//conditions:default": [],
    }) + select({
        ":max78002_aes_enabled": [
            "MAX/Libraries/PeriphDrivers/Source/AES/aes_ai87.c",
            "MAX/Libraries/PeriphDrivers/Source/AES/aes_revb.c",
        ],
        "//conditions:default": [],
    }),
)

filegroup(
    name = "max78002_arm_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX78002/Source/system_max78002.c",
        "MAX/Libraries/PeriphDrivers/Source/SYS/mxc_lock.c",
        ":max78002_common_srcs",
    ],
)

filegroup(
    name = "max78002_riscv_srcs",
    srcs = [
        "MAX/Libraries/CMSIS/Device/Maxim/MAX78002/Source/system_riscv_max78002.c",
        ":max78002_common_srcs",
    ],
)
