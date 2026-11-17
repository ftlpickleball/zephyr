# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Custom wrapper macro around zephyr_module for downstream integration tests."""

load("@zephyr//bazel:cc.bzl", "zephyr_module")

def custom_sample_module(*, name, config, **kwargs):
    zephyr_module(
        name = name,
        config = config,
        **kwargs
    )
