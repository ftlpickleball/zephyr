# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "headers",
    hdrs = glob(
        [
            "decoder/include/**/*.h",
            "decoder/srce/**/*.h",
            "encoder/include/**/*.h",
        ],
        allow_empty = True,
    ),
    includes = [
        "decoder/include",
        "decoder/srce",
        "encoder/include",
    ],
)

cc_library(
    name = "libsbc",
    srcs = [
        "decoder/srce/alloc.c",
        "decoder/srce/bitalloc.c",
        "decoder/srce/bitalloc-sbc.c",
        "decoder/srce/bitstream-decode.c",
        "decoder/srce/decoder-oina.c",
        "decoder/srce/decoder-private.c",
        "decoder/srce/decoder-sbc.c",
        "decoder/srce/dequant.c",
        "decoder/srce/framing.c",
        "decoder/srce/framing-sbc.c",
        "decoder/srce/oi_codec_version.c",
        "decoder/srce/synthesis-8-generated.c",
        "decoder/srce/synthesis-dct8.c",
        "decoder/srce/synthesis-sbc.c",
        "encoder/srce/sbc_analysis.c",
        "encoder/srce/sbc_dct.c",
        "encoder/srce/sbc_dct_coeffs.c",
        "encoder/srce/sbc_enc_bit_alloc_mono.c",
        "encoder/srce/sbc_enc_bit_alloc_ste.c",
        "encoder/srce/sbc_enc_coeffs.c",
        "encoder/srce/sbc_encoder.c",
        "encoder/srce/sbc_packing.c",
    ],
    copts = [
        "-O3",
        "-std=c11",
        "-ffast-math",
    ],
    features = ["zephyr_warning_suppressions"],
    hdrs = glob(
        [
            "decoder/srce/**/*.h",
            "encoder/srce/**/*.h",
        ],
        allow_empty = True,
    ),
    includes = [
        "decoder/srce",
        "encoder/srce",
    ],
    textual_hdrs = [
        "decoder/srce/readsamplesjoint.inc",
    ],
    deps = [
        ":headers",
    ],
)
