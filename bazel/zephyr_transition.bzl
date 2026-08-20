# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Public entry point for Zephyr incoming rule transition."""

load("//bazel/private:zephyr_transition.bzl", _zephyr_transition = "zephyr_transition")

zephyr_transition = _zephyr_transition
