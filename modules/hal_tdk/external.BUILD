# Copyright 2026 Google LLC
# Google Confidential

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "module_files",
    srcs = [
        "zephyr/module.yml",
    ],
)

cc_library(
    name = "hal_tdk",
    srcs = [
        "icm456xx/imu/inv_imu_driver.c",
        "icm456xx/imu/inv_imu_driver_advanced.c",
        "icm456xx/imu/inv_imu_transport.c",
        "icm456xx/imu/inv_imu_edmp.c",
    ],
    hdrs = glob([
        "common/**/*.h",
        "icm456xx/**/*.h",
    ], allow_empty = True),
    includes = [
        "common",
        "common/Invn",
        "icm456xx",
        "icm456xx/icm456xx_h",
    ],
)
