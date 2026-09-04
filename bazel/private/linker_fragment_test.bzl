# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for zephyr_linker_fragment rule and provider merging."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//bazel:linker_fragment.bzl", "LinkerFragmentInfo", "zephyr_linker_fragment")

def _linker_fragment_test_impl(ctx):
    env = analysistest.begin(ctx)
    target_under_test = analysistest.target_under_test(env)

    # Verify LinkerFragmentInfo is present.
    asserts.true(env, LinkerFragmentInfo in target_under_test)
    fragments = target_under_test[LinkerFragmentInfo].fragments.to_list()
    asserts.equals(env, 2, len(fragments))

    # Verify fragment attributes.
    locations = [f.location for f in fragments]
    asserts.true(env, "SECTIONS" in locations)
    asserts.true(env, "RODATA" in locations)

    # Verify CcInfo is propagated from deps.
    asserts.true(env, CcInfo in target_under_test)
    cc_info = target_under_test[CcInfo]
    asserts.true(env, cc_info.compilation_context != None)
    asserts.true(env, cc_info.linking_context != None)

    return analysistest.end(env)

def _aggregator_fragment_test_impl(ctx):
    env = analysistest.begin(ctx)
    target_under_test = analysistest.target_under_test(env)

    # Aggregator with no direct srcs and no location should collect transitive fragments.
    asserts.true(env, LinkerFragmentInfo in target_under_test)
    fragments = target_under_test[LinkerFragmentInfo].fragments.to_list()
    asserts.equals(env, 2, len(fragments))

    # Should also propagate CcInfo.
    asserts.true(env, CcInfo in target_under_test)
    return analysistest.end(env)

linker_fragment_test = analysistest.make(_linker_fragment_test_impl)
aggregator_fragment_test = analysistest.make(_aggregator_fragment_test_impl)

def _setup_test_targets():
    native.genrule(
        name = "test_frag1_gen",
        outs = ["test_frag1.ld"],
        cmd = "echo '/* test frag 1 */' > $@",
        tags = ["manual"],
    )

    native.genrule(
        name = "test_frag2_gen",
        outs = ["test_frag2.ld"],
        cmd = "echo '/* test frag 2 */' > $@",
        tags = ["manual"],
    )

    native.cc_library(
        name = "test_cc_dep",
        hdrs = ["test_frag1.ld"],
        tags = ["manual"],
    )

    zephyr_linker_fragment(
        name = "test_child_fragment",
        srcs = [":test_frag1.ld"],
        location = "RODATA",
        sort_key = "10_child",
        deps = [":test_cc_dep"],
        tags = ["manual"],
    )

    zephyr_linker_fragment(
        name = "test_parent_fragment",
        srcs = [":test_frag2.ld"],
        location = "SECTIONS",
        sort_key = "20_parent",
        deps = [":test_child_fragment"],
        tags = ["manual"],
    )

    zephyr_linker_fragment(
        name = "test_aggregator_fragment",
        deps = [":test_parent_fragment"],
        tags = ["manual"],
    )

def linker_fragment_test_suite(name = "linker_fragment_test_suite"):
    _setup_test_targets()

    linker_fragment_test(
        name = "linker_fragment_propagation_test",
        target_under_test = ":test_parent_fragment",
    )

    aggregator_fragment_test(
        name = "linker_fragment_aggregator_test",
        target_under_test = ":test_aggregator_fragment",
    )

    native.test_suite(
        name = name,
        tests = [
            ":linker_fragment_propagation_test",
            ":linker_fragment_aggregator_test",
        ],
    )
