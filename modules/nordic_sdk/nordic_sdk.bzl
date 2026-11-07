# SPDX-License-Identifier: Apache-2.0
"""Helpers for the Nordic nrfxlib external BUILD file."""

load("@bazel_skylib//lib:selects.bzl", "selects")

# Mirrors CONFIG_MPSL_LIB_DIR in nrfxlib mpsl/Kconfig (secure builds only).
SOCS = ["nrf54l", "nrf54lm"]

# Float ABI dir -> setting, mirroring CONFIG_MPSL_LIB_FLOAT_ABI_DIR.
ABIS = {
    "hard-float": "@zephyr_kconfig//:CONFIG_FP_HARDABI=true",
    "softfp-float": "@zephyr_kconfig//:CONFIG_FP_SOFTABI=true",
    "soft-float": ":fp_soft",
}

def nordic_variant_settings():
    """Declares :fp_soft, :soc_<soc> and :<soc>_<abi> config settings."""
    native.config_setting(
        name = "fp_soft",
        flag_values = {
            "@zephyr_kconfig//:CONFIG_FP_HARDABI": "false",
            "@zephyr_kconfig//:CONFIG_FP_SOFTABI": "false",
        },
    )
    selects.config_setting_group(
        name = "soc_nrf54lm",
        match_any = [
            "@zephyr_kconfig//:CONFIG_SOC_NRF54LM20A=true",
            "@zephyr_kconfig//:CONFIG_SOC_NRF54LM20B=true",
        ],
    )
    selects.config_setting_group(
        name = "soc_nrf54l",
        match_any = [
            "@zephyr_kconfig//:CONFIG_SOC_NRF54L05=true",
            "@zephyr_kconfig//:CONFIG_SOC_NRF54L10=true",
            "@zephyr_kconfig//:CONFIG_SOC_NRF54L15=true",
        ],
    )
    for soc in SOCS:
        for abi, setting in ABIS.items():
            selects.config_setting_group(
                name = "{}_{}".format(soc, abi),
                match_all = [":soc_" + soc, setting],
            )

def per_variant(pattern):
    """Globs `pattern` ({soc}, {abi} placeholders) for the active SoC + float ABI."""
    branches = {
        ":{}_{}".format(soc, abi): native.glob(
            [pattern.format(soc = soc, abi = abi)],
            allow_empty = True,
        )
        for soc in SOCS
        for abi in ABIS
    }
    branches["//conditions:default"] = []
    return select(branches)
