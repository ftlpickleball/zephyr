# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//rules:native_binary.bzl", "native_binary")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

exports_files(["bin/gperf"])

native_binary(
    name = "gperf",
    src = "bin/gperf",
)

filegroup(
    name = "all",
    srcs = glob(
        include = ["**"],
        allow_empty = True,
    ),
)
