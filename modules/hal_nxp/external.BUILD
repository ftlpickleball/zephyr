# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")
load("@zephyr//bazel:cc.bzl", "zephyr_cc_library", "zephyr_module")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "dts_includes",
    includes = ["dts"],
)

filegroup(
    name = "dt_bindings",
    srcs = glob(["dts/**/*"]),
)

# filegroup instead of cc_library because we want these to be compiled with
# defines created by Zephyr.
filegroup(
    name = "fsl_common_arm_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/common/fsl_common.c",
        "mcux/mcux-sdk/drivers/common/fsl_common_arm.c",
    ],
)

filegroup(
    name = "fsl_common_dsp_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/common/fsl_common.c",
        "mcux/mcux-sdk/drivers/common/fsl_common_dsp.c",
    ],
)

cc_library(
    name = "fsl_common_arm_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/common/fsl_common.h",
        "mcux/mcux-sdk/drivers/common/fsl_common_arm.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/common",
)

cc_library(
    name = "fsl_common_dsp_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/common/fsl_common.h",
        "mcux/mcux-sdk/drivers/common/fsl_common_dsp.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/common",
)

filegroup(
    name = "fsl_dma_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/lpc_dma/fsl_dma.c",
    ],
)

cc_library(
    name = "fsl_dma_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lpc_dma/fsl_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lpc_dma",
)

filegroup(
    name = "fsl_crc_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/lpc_crc/fsl_crc.c",
    ],
)

cc_library(
    name = "fsl_crc_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lpc_crc/fsl_crc.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lpc_crc",
)

filegroup(
    name = "fsl_flexspi_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexspi/fsl_flexspi.c",
    ],
)

cc_library(
    name = "fsl_flexspi_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexspi/fsl_flexspi.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexspi",
)

filegroup(
    name = "fsl_i3c_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/i3c/fsl_i3c.c",
        "mcux/mcux-sdk/drivers/i3c/fsl_i3c_dma.c",
    ],
)

cc_library(
    name = "fsl_i3c_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/i3c/fsl_i3c.h",
        "mcux/mcux-sdk/drivers/i3c/fsl_i3c_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/i3c",
)

filegroup(
    name = "fsl_inputmux_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/inputmux/fsl_inputmux.c",
    ],
)

cc_library(
    name = "fsl_inputmux_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/inputmux/fsl_inputmux.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/inputmux",
)

cc_library(
    name = "fsl_iopctl_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lpc_iopctl/fsl_iopctl.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lpc_iopctl",
)

filegroup(
    name = "fsl_gpio_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/lpc_gpio/fsl_gpio.c",
    ],
)

cc_library(
    name = "fsl_gpio_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lpc_gpio/fsl_gpio.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lpc_gpio",
)

filegroup(
    name = "fsl_lcdif_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/lcdif/fsl_lcdif.c",
    ],
)

cc_library(
    name = "fsl_lcdif_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lcdif/fsl_lcdif.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lcdif",
)

filegroup(
    name = "fsl_mipi_dsi_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/mipi_dsi/fsl_mipi_dsi.c",
    ],
)

cc_library(
    name = "fsl_mipi_dsi_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/mipi_dsi/fsl_mipi_dsi.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/mipi_dsi",
)

filegroup(
    name = "fsl_mu_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/mu/fsl_mu.c",
    ],
)

cc_library(
    name = "fsl_mu_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/mu/fsl_mu.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/mu",
)

filegroup(
    name = "fsl_pint_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/pint/fsl_pint.c",
    ],
)

cc_library(
    name = "fsl_pint_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/pint/fsl_pint.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/pint",
)

filegroup(
    name = "fsl_rtc_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/lpc_rtc/fsl_rtc.c",
    ],
)

cc_library(
    name = "fsl_rtc_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/lpc_rtc/fsl_rtc.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/lpc_rtc",
)

filegroup(
    name = "fsl_dmic_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/dmic/fsl_dmic.c",
        "mcux/mcux-sdk/drivers/dmic/fsl_dmic_dma.c",
    ],
)

cc_library(
    name = "fsl_dmic_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/dmic/fsl_dmic.h",
        "mcux/mcux-sdk/drivers/dmic/fsl_dmic_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/dmic",
)

filegroup(
    name = "fsl_flexcomm_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/fsl_flexcomm.c",
    ],
)

cc_library(
    name = "fsl_flexcomm_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/fsl_flexcomm.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm",
)

filegroup(
    name = "fsl_i2s_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/i2s/fsl_i2s.c",
        "mcux/mcux-sdk/drivers/flexcomm/i2s/fsl_i2s_dma.c",
    ],
)

cc_library(
    name = "fsl_i2s_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/i2s/fsl_i2s.h",
        "mcux/mcux-sdk/drivers/flexcomm/i2s/fsl_i2s_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm/i2s",
)

filegroup(
    name = "fsl_i2c_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/i2c/fsl_i2c.c",
        "mcux/mcux-sdk/drivers/flexcomm/i2c/fsl_i2c_dma.c",
    ],
)

cc_library(
    name = "fsl_i2c_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/i2c/fsl_i2c.h",
        "mcux/mcux-sdk/drivers/flexcomm/i2c/fsl_i2c_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm/i2c",
)

filegroup(
    name = "fsl_usart_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/usart/fsl_usart.c",
        "mcux/mcux-sdk/drivers/flexcomm/usart/fsl_usart_dma.c",
    ],
)

cc_library(
    name = "fsl_usart_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/usart/fsl_usart.h",
        "mcux/mcux-sdk/drivers/flexcomm/usart/fsl_usart_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm/usart",
)

filegroup(
    name = "fsl_spi_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/spi/fsl_spi.c",
    ],
)

cc_library(
    name = "fsl_spi_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/spi/fsl_spi.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm/spi",
    deps = [
        ":fsl_flexcomm_hdrs",
    ],
)

filegroup(
    name = "fsl_spi_dma_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/flexcomm/spi/fsl_spi_dma.c",
    ],
)

cc_library(
    name = "fsl_spi_dma_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/flexcomm/spi/fsl_spi_dma.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/flexcomm/spi",
    deps = [
        ":fsl_dma_hdrs",
        ":fsl_spi_hdrs",
    ],
)

filegroup(
    name = "fsl_smartdma_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/smartdma/fsl_smartdma.c",
        "mcux/mcux-sdk/drivers/smartdma/fsl_smartdma_rt500.c",
    ],
)

cc_library(
    name = "fsl_smartdma_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/smartdma/fsl_smartdma.h",
        "mcux/mcux-sdk/drivers/smartdma/fsl_smartdma_rt500.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/smartdma",
)

filegroup(
    name = "fsl_ostimer_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/ostimer/fsl_ostimer.c",
    ],
)

cc_library(
    name = "fsl_ostimer_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/ostimer/fsl_ostimer.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/ostimer",
)

filegroup(
    name = "fsl_ctimer_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/ctimer/fsl_ctimer.c",
    ],
)

cc_library(
    name = "fsl_ctimer_hdrs",
    hdrs = [
        "mcux/mcux-sdk/drivers/ctimer/fsl_ctimer.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/drivers/ctimer",
)

filegroup(
    name = "fsl_cache_srcs",
    srcs = [
        "mcux/mcux-sdk/drivers/cache/cache64/fsl_cache.c",
    ],
)

cc_library(
    name = "fsl_cache_hdrs",
    hdrs = ["mcux/mcux-sdk/drivers/cache/cache64/fsl_cache.h"],
    strip_include_prefix = "mcux/mcux-sdk/drivers/cache/cache64",
)

filegroup(
    name = "mimxrt595s_cm33_srcs",
    srcs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/system_MIMXRT595S_cm33.c",
    ],
)

filegroup(
    name = "mimxrt595s_dsp_srcs",
    srcs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/system_MIMXRT595S_dsp.c",
    ],
)

cc_library(
    name = "mimxrt595s_cm33_hdrs",
    hdrs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/MIMXRT595S_cm33.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/MIMXRT595S_cm33_features.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/fsl_device_registers.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/system_MIMXRT595S_cm33.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/devices/MIMXRT595S",
)

cc_library(
    name = "mimxrt595s_dsp_hdrs",
    hdrs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/MIMXRT595S_dsp.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/MIMXRT595S_dsp_features.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/fsl_device_registers.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/system_MIMXRT595S_dsp.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/devices/MIMXRT595S",
)

# Shared between mimxrt595s cm33 and dsp.
filegroup(
    name = "mimxrt595s_shared_driver_srcs",
    srcs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_clock.c",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_iap.c",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_reset.c",
    ],
)

filegroup(
    name = "mimxrt595s_cm33_driver_srcs",
    srcs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_dsp.c",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_power.c",
        "mcux/middleware/mcux-sdk-middleware-usb/phy/usb_phy.c",
        ":mimxrt595s_shared_driver_srcs",
    ],
)

# Shared between mimxrt595s cm33 and dsp.
cc_library(
    name = "mimxrt595s_shared_driver_hdrs",
    hdrs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_clock.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_iap.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_inputmux_connections.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_reset.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/devices/MIMXRT595S/drivers",
)

cc_library(
    name = "mimxrt595s_cm33_driver_hdrs",
    hdrs = [
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_dsp.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_power.h",
        "mcux/mcux-sdk/devices/MIMXRT595S/drivers/fsl_soc_mipi_dsi.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/devices/MIMXRT595S/drivers",
    deps = [":mimxrt595s_shared_driver_hdrs"],
)

cc_library(
    name = "mimxrt595s_usb_phy_hdrs",
    hdrs = ["mcux/middleware/mcux-sdk-middleware-usb/phy/usb_phy.h"],
    strip_include_prefix = "mcux/middleware/mcux-sdk-middleware-usb/phy",
)

cc_library(
    name = "mimxrt595s_usb_hdrs",
    hdrs = [
        "mcux/middleware/mcux-sdk-middleware-usb/include/usb.h",
        "mcux/middleware/mcux-sdk-middleware-usb/include/usb_misc.h",
        "mcux/middleware/mcux-sdk-middleware-usb/include/usb_spec.h",
    ],
    strip_include_prefix = "mcux/middleware/mcux-sdk-middleware-usb/include",
)

filegroup(
    name = "fsl_os_abstraction_srcs",
    srcs = [
        "mcux/mcux-sdk/components/osa/fsl_os_abstraction_zephyr.c",
    ],
)

cc_library(
    name = "fsl_os_abstraction_hdrs",
    hdrs = [
        "mcux/mcux-sdk/components/osa/fsl_os_abstraction.h",
        "mcux/mcux-sdk/components/osa/fsl_os_abstraction_config.h",
        "mcux/mcux-sdk/components/osa/fsl_os_abstraction_zephyr.h",
    ],
    strip_include_prefix = "mcux/mcux-sdk/components/osa",
)

cc_library(
    name = "linker_includes",
    hdrs = [
        "mcux/quick_access_code.ld",
        "mcux/quick_access_data.ld",
    ],
)

zephyr_cc_library(
    name = "hal_nxp_lib",
    srcs = select({
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_IMXRT5XX=true": [
            ":fsl_cache_srcs",
            ":fsl_common_arm_srcs",
            ":fsl_dma_srcs",
            ":fsl_flexcomm_srcs",
            ":fsl_gpio_srcs",
            ":fsl_i2c_srcs",
            ":fsl_inputmux_srcs",
            ":fsl_ostimer_srcs",
            ":fsl_pint_srcs",
            ":fsl_spi_srcs",
            ":fsl_usart_srcs",
            ":mimxrt595s_cm33_driver_srcs",
            ":mimxrt595s_cm33_srcs",
        ],
        "//conditions:default": [],
    }),
    defines = select({
        "@zephyr_kconfig//:CONFIG_SOC_MIMXRT595S_CM33=true": ["CPU_MIMXRT595SFAWC_cm33"],
        "//conditions:default": [],
    }),
    deps = select({
        "@zephyr_kconfig//:CONFIG_SOC_SERIES_IMXRT5XX=true": [
            ":fsl_cache_hdrs",
            ":fsl_common_arm_hdrs",
            ":fsl_dma_hdrs",
            ":fsl_flexcomm_hdrs",
            ":fsl_flexspi_hdrs",
            ":fsl_gpio_hdrs",
            ":fsl_i2c_hdrs",
            ":fsl_inputmux_hdrs",
            ":fsl_iopctl_hdrs",
            ":fsl_os_abstraction_hdrs",
            ":fsl_ostimer_hdrs",
            ":fsl_pint_hdrs",
            ":fsl_spi_hdrs",
            ":fsl_usart_hdrs",
            ":mimxrt595s_cm33_driver_hdrs",
            ":mimxrt595s_cm33_hdrs",
            ":mimxrt595s_usb_hdrs",
            ":mimxrt595s_usb_phy_hdrs",
        ],
        "//conditions:default": [],
    }),
)

zephyr_module(
    name = "hal_nxp",
    config = "CONFIG_HAS_MCUX",
    deps = [":hal_nxp_lib"],
)
