# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

def select_drivers(drivers_map):
    srcs = []
    for config, files in drivers_map.items():
        srcs += select({
            "@zephyr_kconfig//:" + config + "=true": files,
            "//conditions:default": [],
        })
    return srcs

def safe_glob(patterns, exclude = []):
    return native.glob(patterns, exclude = exclude, allow_empty = True)
