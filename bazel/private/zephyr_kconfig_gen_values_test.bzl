# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the zc_* input filter in zephyr_kconfig_gen_values.bzl."""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//bazel/private:zephyr_kconfig_gen_values.bzl", "filter_zc_deps")

_ZEPHYR = "/src/zephyr/"
_APP = "/src/zephyr/samples/hello_world/"
_BOARD = "/src/zephyr/boards/qemu/cortex_m3/"

def _filter_zc_deps_test_impl(ctx):
    env = unittest.begin(ctx)
    kept = [
        # Outside @zephyr.
        "/ws/apps/main_app/prj.conf",
        "/ws/modules/m1/Kconfig",
        # Application and board directories.
        _APP + "VERSION",
        _APP + "CMakeLists.txt",
        _BOARD + "Kconfig.defconfig",
        # DTS, conf, header, Python files and hardware/module metadata.
        _ZEPHYR + "dts/arm/armv7-m.dtsi",
        _ZEPHYR + "soc/ti/lm3s6965/soc.yml",
        _ZEPHYR + "modules/foo/zephyr/module.yml",
        _ZEPHYR + "modules/bar/zephyr/module.yaml",
        _ZEPHYR + "scripts/dts/gen_defines.py",
        # Bindings matched by edtlib.
        _ZEPHYR + "dts/bindings/serial/ti,stellaris-uart.yaml",
        # `app_version.h` template, which kconfig_inputs_sha256 does not cover.
        _ZEPHYR + "version.h.in",
        # Sysbuild Kconfig files, which @zephyr_kconfig does not parse.
        _ZEPHYR + "share/sysbuild/Kconfig",
        _ZEPHYR + "share/sysbuild/images/bootloader/Kconfig",
        _ZEPHYR + "boards/nordic/nrf5340dk/Kconfig.sysbuild",
        _ZEPHYR + "soc/nordic/nrf53/Kconfig.sysbuild",
    ]
    dropped = [
        # Covered by kconfig_inputs_sha256 in @zephyr_kconfig//:Kconfig.dts.
        _ZEPHYR + "Kconfig",
        _ZEPHYR + "subsys/logging/Kconfig",
        _ZEPHYR + "boards/nordic/nrf5340dk/Kconfig.defconfig",
        _ZEPHYR + "subsys/logging/Kconfig.sysbuild_extra",
    ]
    asserts.equals(
        env,
        kept,
        filter_zc_deps(dropped + kept, _ZEPHYR, [_APP, _BOARD]),
    )
    return unittest.end(env)

filter_zc_deps_test = unittest.make(_filter_zc_deps_test_impl)

def zephyr_kconfig_gen_values_test_suite(name = "zephyr_kconfig_gen_values_test_suite"):
    unittest.suite(
        name,
        filter_zc_deps_test,
    )
