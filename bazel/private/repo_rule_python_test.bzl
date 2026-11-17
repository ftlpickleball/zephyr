# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for repository-rule Python wheel selection helpers."""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//bazel/private:repo_rule_python.bzl", "host_whl_platform_tag", "select_whl_repo_name")

def _host_whl_platform_tag_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.equals(env, "cp311_linux_x86_64", host_whl_platform_tag("Linux", "amd64", "311"))
    asserts.equals(env, "cp311_linux_x86_64", host_whl_platform_tag("linux", "x86_64", "311"))
    asserts.equals(env, "cp311_linux_aarch64", host_whl_platform_tag("Linux", "aarch64", "311"))
    asserts.equals(env, "cp311_osx_aarch64", host_whl_platform_tag("Mac OS X", "aarch64", "311"))
    asserts.equals(env, "cp312_osx_aarch64", host_whl_platform_tag("darwin", "arm64", "312"))
    asserts.equals(env, "cp311_osx_x86_64", host_whl_platform_tag("Mac OS X", "x86_64", "311"))
    asserts.equals(env, "cp311_linux_x86_64", host_whl_platform_tag("linux", "x64", "311"))
    asserts.equals(env, "cp311_windows_x86_64", host_whl_platform_tag("Windows 11", "amd64", "311"))
    asserts.equals(env, "cp311_windows_aarch64", host_whl_platform_tag("Windows 11", "arm64", "311"))
    return unittest.end(env)

def _select_whl_repo_name_single_platform_test_impl(ctx):
    env = unittest.begin(ctx)
    build_content = """\
load("@rules_python//python/private/pypi:pkg_aliases.bzl", "pkg_aliases")
load("@rules_python//python/private/pypi:whl_config_setting.bzl", "whl_config_setting")

pkg_aliases(
    name = "pyyaml",
    actual = {
        whl_config_setting(
            target_platforms = ("cp311_osx_aarch64",),
            version = "3.11",
        ): "zephyr_pip_deps_311_pyyaml_cp311_macosx_arm64_aaaa1111",
        whl_config_setting(
            target_platforms = ("cp311_linux_x86_64",),
            version = "3.11",
        ): "zephyr_pip_deps_311_pyyaml_cp311_manylinux_x86_64_bbbb2222",
        whl_config_setting(
            target_platforms = ("cp312_linux_x86_64",),
            version = "3.12",
        ): "zephyr_pip_deps_312_pyyaml_cp312_manylinux_x86_64_cccc3333",
    },
)
"""
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyyaml_cp311_macosx_arm64_aaaa1111",
        select_whl_repo_name(build_content, "311", "cp311_osx_aarch64"),
    )
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyyaml_cp311_manylinux_x86_64_bbbb2222",
        select_whl_repo_name(build_content, "311", "cp311_linux_x86_64"),
    )
    asserts.equals(
        env,
        "zephyr_pip_deps_312_pyyaml_cp312_manylinux_x86_64_cccc3333",
        select_whl_repo_name(build_content, "312", "cp312_linux_x86_64"),
    )
    asserts.equals(
        env,
        None,
        select_whl_repo_name(build_content, "311", "cp311_windows_x86_64"),
    )
    asserts.equals(
        env,
        None,
        select_whl_repo_name(build_content, "311", "cp311_linux_x86"),
    )
    return unittest.end(env)

def _select_whl_repo_name_multiline_target_platforms_test_impl(ctx):
    env = unittest.begin(ctx)
    build_content = """\
pkg_aliases(
    name = "pyyaml",
    actual = {
        whl_config_setting(
            target_platforms = (
                "cp311_osx_x86_64",
            ),
            version = "3.11",
        ): "zephyr_pip_deps_311_pyyaml_osx_x86_64_1111",
        whl_config_setting(
            target_platforms = (
                "cp311_linux_aarch64",
                "cp311_linux_x86_64",
                "cp311_osx_aarch64",
            ),
            version = "3.11",
        ): "zephyr_pip_deps_311_pyyaml_multi_2222",
    },
)
"""
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyyaml_multi_2222",
        select_whl_repo_name(build_content, "311", "cp311_linux_x86_64"),
    )
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyyaml_multi_2222",
        select_whl_repo_name(build_content, "311", "cp311_osx_aarch64"),
    )
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyyaml_osx_x86_64_1111",
        select_whl_repo_name(build_content, "311", "cp311_osx_x86_64"),
    )
    return unittest.end(env)

def _select_whl_repo_name_version_only_and_multiline_value_test_impl(ctx):
    env = unittest.begin(ctx)
    version_only_build = """\
pkg_aliases(
    name = "pcpp",
    actual = {
        "//_config:is_cp311": "zephyr_pip_deps_311_pcpp_py2_none_any_05fe0829",
        "//_config:is_cp312": "zephyr_pip_deps_312_pcpp_py2_none_any_05fe0829",
    },
)
"""
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pcpp_py2_none_any_05fe0829",
        select_whl_repo_name(version_only_build, "311", "cp311_linux_x86_64"),
    )

    split_value_build = """\
pkg_aliases(
    name = "rpds_py",
    actual = {
        whl_config_setting(
            target_platforms = (
                "cp311_osx_aarch64",
            ),
            version = "3.11",
        ):
            "zephyr_pip_deps_311_rpds_py_osx_1111",
        whl_config_setting(
            target_platforms = (
                "cp311_linux_x86_64",
            ),
            version = "3.11",
        ):
            "zephyr_pip_deps_311_rpds_py_linux_2222",
    },
)
"""
    asserts.equals(
        env,
        "zephyr_pip_deps_311_rpds_py_linux_2222",
        select_whl_repo_name(split_value_build, "311", "cp311_linux_x86_64"),
    )

    whl_config_version_only_build = """\
pkg_aliases(
    name = "pyserial",
    actual = {
        whl_config_setting(
            version = "3.11",
        ): "zephyr_pip_deps_311_pyserial_py2_none_any_1234",
    },
)
"""
    asserts.equals(
        env,
        "zephyr_pip_deps_311_pyserial_py2_none_any_1234",
        select_whl_repo_name(whl_config_version_only_build, "311", "cp311_linux_x86_64"),
    )
    return unittest.end(env)

host_whl_platform_tag_test = unittest.make(_host_whl_platform_tag_test_impl)
select_whl_repo_name_single_platform_test = unittest.make(
    _select_whl_repo_name_single_platform_test_impl,
)
select_whl_repo_name_multiline_target_platforms_test = unittest.make(
    _select_whl_repo_name_multiline_target_platforms_test_impl,
)
select_whl_repo_name_version_only_and_multiline_value_test = unittest.make(
    _select_whl_repo_name_version_only_and_multiline_value_test_impl,
)

def repo_rule_python_test_suite(name = "repo_rule_python_test_suite"):
    unittest.suite(
        name,
        host_whl_platform_tag_test,
        select_whl_repo_name_single_platform_test,
        select_whl_repo_name_multiline_target_platforms_test,
        select_whl_repo_name_version_only_and_multiline_value_test,
    )
