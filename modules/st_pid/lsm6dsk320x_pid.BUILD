# SPDX-License-Identifier: Apache-2.0
#
# BUILD for STMicroelectronics/lsm6dsk320x-pid (BSD-3-Clause): the register-level
# driver a Zephyr lsm6dsk320x sensor driver builds on. Not in hal_st yet.

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "lsm6dsk320x_pid",
    srcs = ["lsm6dsk320x_reg.c"],
    hdrs = ["lsm6dsk320x_reg.h"],
    includes = ["."],
)
