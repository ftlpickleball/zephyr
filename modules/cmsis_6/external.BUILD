# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "core",
    hdrs = glob(["CMSIS/Core/Include/**/*.h"]),
    defines = ["__PROGRAM_START"],
    includes = ["CMSIS/Core/Include"],
)
