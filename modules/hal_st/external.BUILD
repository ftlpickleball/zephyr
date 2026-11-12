# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "module_files",
    srcs = [
        "zephyr/module.yml",
    ],
)

[
    cc_library(
        name = part + "_stdc",
        srcs = ["sensor/stmemsc/{0}_STdC/driver/{0}_reg.c".format(part)],
        hdrs = ["sensor/stmemsc/{0}_STdC/driver/{0}_reg.h".format(part)],
        includes = ["sensor/stmemsc/{}_STdC/driver".format(part)],
    )
    for part in [
        "ilps22qs",
        "lps22df",
        "lps28dfw",
    ]
]

cc_library(
    name = "lsm6dsv16x_stdc",
    srcs = [
        "sensor/stmemsc/lsm6dsv16x_STdC/driver/lsm6dsv16x_reg.c",
    ],
    hdrs = [
        "sensor/stmemsc/lsm6dsv16x_STdC/driver/lsm6dsv16x_reg.h",
    ],
    includes = [
        "sensor/stmemsc/lsm6dsv16x_STdC/driver",
    ],
)
