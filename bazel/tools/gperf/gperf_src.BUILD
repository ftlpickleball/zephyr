# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:defs.bzl", "cc_binary", "cc_library")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

write_file(
    name = "config_h",
    out = "config.h",
)

cc_library(
    name = "gperf_c_lib",
    srcs = glob(
        [
            "lib/*.c",
            "lib/*.h",
        ],
        allow_empty = True,
    ),
    copts = ["-w"],
    includes = ["lib"],
    visibility = ["//visibility:private"],
)

cc_binary(
    name = "gperf",
    srcs = glob(
        [
            "src/*.inc",
            "src/*.cc",
            "src/*.h",
            "lib/*.cc",
            "lib/*.h",
        ],
        allow_empty = True,
    ) + [":config_h"],
    copts = [
        "-std=c++11",
        "-w",
    ],
    includes = [
        "lib",
        "src",
    ],
    deps = [":gperf_c_lib"],
)
