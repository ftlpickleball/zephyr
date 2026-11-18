# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Analysis tests for SysbuildInfo and helper target forwarding."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//bazel:sysbuild.bzl", "SysbuildInfo", "zephyr_sysbuild_rule")
load("//bazel/private:transition_rule.bzl", "SysbuildHelperInfo", "transitioned_dep")

_DummyDomainInfo = provider(fields = ["domain"])

def _dummy_domain_impl(ctx):
    exe = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        output = exe,
        content = "#!/bin/sh\necho " + ctx.attr.domain + "\n",
        is_executable = True,
    )
    og_file = ctx.actions.declare_file(ctx.label.name + ".og")
    ctx.actions.write(output = og_file, content = ctx.attr.domain + "\n")
    rf_file = ctx.actions.declare_file(ctx.label.name + ".rf")
    ctx.actions.write(output = rf_file, content = ctx.attr.domain + "\n")
    return [
        DefaultInfo(
            executable = exe,
            files = depset([exe]),
            runfiles = ctx.runfiles(files = [rf_file]),
        ),
        _DummyDomainInfo(domain = ctx.attr.domain),
        OutputGroupInfo(custom_group = depset([og_file])),
    ]

_dummy_domain = rule(
    implementation = _dummy_domain_impl,
    executable = True,
    attrs = {
        "domain": attr.string(mandatory = True),
    },
)

def _sysbuild_info_test_impl(ctx):
    env = analysistest.begin(ctx)
    target_under_test = analysistest.target_under_test(env)

    asserts.true(env, SysbuildInfo in target_under_test)
    sb = target_under_test[SysbuildInfo]

    asserts.equals(
        env,
        Label("//bazel/private:sysbuild_test_main_app"),
        sb.main.label,
    )
    asserts.true(env, _DummyDomainInfo in sb.main)
    asserts.equals(env, "main", sb.main[_DummyDomainInfo].domain)
    asserts.true(env, sb.main[DefaultInfo].files_to_run != None)
    asserts.true(env, sb.main[DefaultInfo].files_to_run.executable != None)

    asserts.true(env, "mcuboot" in sb.helpers)
    helper = sb.helpers["mcuboot"]
    asserts.equals(
        env,
        Label("//bazel/private:sysbuild_test_helper_app"),
        helper.label,
    )
    asserts.true(env, _DummyDomainInfo in helper)
    asserts.equals(env, "mcuboot", helper[_DummyDomainInfo].domain)
    asserts.true(env, OutputGroupInfo in helper)
    asserts.true(env, helper[DefaultInfo].files_to_run != None)
    asserts.true(env, helper[DefaultInfo].files_to_run.executable != None)
    asserts.false(env, SysbuildHelperInfo in helper)

    return analysistest.end(env)

sysbuild_info_test = analysistest.make(_sysbuild_info_test_impl)

def sysbuild_test_suite(name = "sysbuild_test_suite"):
    _dummy_domain(
        name = "sysbuild_test_main_app",
        domain = "main",
        tags = ["manual"],
    )
    _dummy_domain(
        name = "sysbuild_test_helper_app",
        domain = "mcuboot",
        tags = ["manual"],
    )
    transitioned_dep(
        name = "sysbuild_test_helper_wrapper",
        dep = ":sysbuild_test_helper_app",
        sysbuild_context = "apps/main:mcuboot",
        tags = ["manual"],
    )
    zephyr_sysbuild_rule(
        name = "sysbuild_test_bundle",
        main = ":sysbuild_test_main_app",
        helpers = [":sysbuild_test_helper_wrapper"],
        tags = ["manual"],
    )
    sysbuild_info_test(
        name = "sysbuild_info_test",
        target_under_test = ":sysbuild_test_bundle",
    )
    native.test_suite(
        name = name,
        tests = [":sysbuild_info_test"],
    )
