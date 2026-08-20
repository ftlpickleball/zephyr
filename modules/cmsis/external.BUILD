# SPDX-FileCopyrightText: Copyright 2024 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "core",
    hdrs = glob(["CMSIS/Core/Include/*.h"]),
    defines = ["__PROGRAM_START"],
    includes = ["CMSIS/Core/Include"],
)

cc_library(
    name = "core_a",
    hdrs = glob(["CMSIS/Core_A/Include/*.h"]),
    defines = ["__PROGRAM_START"],
    includes = ["CMSIS/Core_A/Include"],
)

cc_library(
    name = "core_r",
    hdrs = glob(["CMSIS/Core_R/Include/*.h"]),
    defines = ["__PROGRAM_START"],
    includes = ["CMSIS/Core_R/Include"],
)
