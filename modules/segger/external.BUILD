# SPDX-License-Identifier: Apache-2.0
#
# BUILD for zephyrproject-rtos/segger (RTT only; SystemView and DebugMon not wired).

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "module_files",
    srcs = [
        "zephyr/module.yml",
    ],
)

# Compiled by @zephyr//modules/segger with Zephyr flags: SEGGER_RTT_Conf.h needs autoconf.
filegroup(
    name = "rtt_srcs",
    srcs = ["SEGGER/SEGGER_RTT.c"],
)

cc_library(
    name = "headers",
    hdrs = [
        "Config/Global.h",
        "Config/SEGGER_RTT_Conf.h",
        "SEGGER/SEGGER.h",
        "SEGGER/SEGGER_RTT.h",
    ],
    includes = [
        "Config",
        "SEGGER",
    ],
)
