# SPDX-FileCopyrightText: Copyright 2024 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Zephyr C/C++ library and module macros without transition or @zephyr_index loads."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//bazel:compatibility.bzl", "zephyr")

def if_compiler_is_clang(then, *, otherwise = []):
    return select({
        Label("//:compiler_is_clang"): then,
        "//conditions:default": otherwise,
    })

def if_compiler_is_gcc(then, *, otherwise = []):
    return select({
        Label("//:compiler_is_gcc"): then,
        "//conditions:default": otherwise,
    })

def if_linker_is_clang(then, *, otherwise = []):
    return select({
        Label("//:linker_is_clang"): then,
        "//conditions:default": otherwise,
    })

def if_linker_is_gcc(then, *, otherwise = []):
    return select({
        Label("//:linker_is_gcc"): then,
        "//conditions:default": otherwise,
    })

def manual_tags(tags):
    if not tags:
        return ["manual"]
    if "manual" in tags:
        return list(tags)
    return list(tags) + ["manual"]

def with_zephyr_compatible(caller_compatible_with):
    if type(caller_compatible_with) == "select":
        return zephyr() + caller_compatible_with
    if caller_compatible_with:
        res = list(zephyr())
        for c in caller_compatible_with:
            if c not in res:
                res.append(c)
        return res
    return zephyr()

def if_zephyr_platform(val, otherwise = None):
    return select({
        Label("//constraints:zephyr_autoconf_force_included"): val,
        "//conditions:default": otherwise,
    })

def _if_zephyr_list(val):
    if not val:
        return []
    if type(val) == "select":
        return val
    return if_zephyr_platform(list(val), otherwise = [])

def _zephyr_library_deps(user_deps, mandatory_deps):
    if not user_deps:
        return if_zephyr_platform(mandatory_deps, otherwise = [])
    if type(user_deps) == "select":
        return user_deps + if_zephyr_platform(mandatory_deps, otherwise = [])
    return if_zephyr_platform(list(user_deps) + mandatory_deps, otherwise = [])

def zephyr_soc_library(*, name, **kwargs):
    """
    A macro that builds a SOC with Zephyr-specific dependencies and options.

    Args:
        name: The name of the library
        **kwargs: Keyword arguments to pass to the cc_library rule.
    """
    srcs = _zephyr_library_deps(
        kwargs.pop("srcs", []),
        [Label("//:hal_soc_extra_srcs")],
    )
    user_deps = kwargs.pop("deps", [])
    mandatory_soc_deps = [
        Label("//:internal_zephyr_soc_mandatory_deps"),
        Label("//:arch_headers_library"),
        Label("//:hal_soc_headers_library"),
        Label("//:arch_specific_deps"),
        ":" + name + "_hdrs",
        Label("//:offsets_header_lib"),
    ]
    features = kwargs.pop("features", []) + ["zephyr_warning_suppressions"]
    target_compatible_with = with_zephyr_compatible(
        kwargs.pop("target_compatible_with", None),
    )

    implementation_deps = _if_zephyr_list(kwargs.pop("implementation_deps", []))
    copts = kwargs.pop("copts", [])
    cxxopts = kwargs.pop("cxxopts", [])
    defines = kwargs.pop("defines", [])
    additional_compiler_inputs = _if_zephyr_list(
        kwargs.pop("additional_compiler_inputs", []),
    )
    hdrs = kwargs.get("hdrs", [])
    includes = kwargs.get("includes", [])
    visibility = kwargs.get("visibility", None)

    cc_library(
        name = name + "_hdrs",
        hdrs = hdrs,
        includes = includes,
        defines = defines,
        deps = _if_zephyr_list(user_deps),
        target_compatible_with = target_compatible_with,
        visibility = visibility,
    )

    cc_library(
        name = name,
        srcs = srcs,
        deps = _zephyr_library_deps(user_deps, mandatory_soc_deps),
        implementation_deps = implementation_deps,
        copts = copts,
        cxxopts = cxxopts,
        defines = defines,
        additional_compiler_inputs = additional_compiler_inputs,
        features = features,
        target_compatible_with = target_compatible_with,
        **kwargs
    )

def zephyr_freestanding_library(*, name, **kwargs):
    """
    Macro for building libc itself or low-level HALs.
    """
    deps = _zephyr_library_deps(
        kwargs.pop("deps", []),
        [Label("//:zephyr")],
    )
    features = kwargs.pop("features", []) + [
        "freestanding",
        "zephyr_warning_suppressions",
    ]
    target_compatible_with = with_zephyr_compatible(
        kwargs.pop("target_compatible_with", None),
    )

    implementation_deps = _if_zephyr_list(kwargs.pop("implementation_deps", []))
    copts = kwargs.pop("copts", [])
    cxxopts = kwargs.pop("cxxopts", [])
    defines = kwargs.pop("defines", [])
    additional_compiler_inputs = _if_zephyr_list(
        kwargs.pop("additional_compiler_inputs", []),
    )
    cc_library(
        name = name,
        deps = deps,
        implementation_deps = implementation_deps,
        copts = copts,
        cxxopts = cxxopts,
        defines = defines,
        additional_compiler_inputs = additional_compiler_inputs,
        features = features,
        target_compatible_with = target_compatible_with,
        **kwargs
    )

def zephyr_cc_library(*, name, **kwargs):
    """
    User-facing macro to declare a cc_library with zephyr dependencies.
    """
    kwargs.pop("_is_zephyr_module_call", False)
    _skip_zephyr_compatible = kwargs.pop("_skip_zephyr_compatible", False)

    deps = _zephyr_library_deps(
        kwargs.pop("deps", []),
        [Label("//:zephyr")],
    )
    features = kwargs.pop("features", []) + ["zephyr_warning_suppressions"]
    caller_compatible_with = kwargs.pop("target_compatible_with", None)
    target_compatible_with = (
        caller_compatible_with
        if _skip_zephyr_compatible
        else with_zephyr_compatible(caller_compatible_with)
    )

    implementation_deps = _if_zephyr_list(kwargs.pop("implementation_deps", []))
    copts = kwargs.pop("copts", [])
    cxxopts = kwargs.pop("cxxopts", [])
    defines = kwargs.pop("defines", [])
    additional_compiler_inputs = _if_zephyr_list(
        kwargs.pop("additional_compiler_inputs", []),
    )
    cc_library(
        name = name,
        deps = deps,
        implementation_deps = implementation_deps,
        copts = copts,
        cxxopts = cxxopts,
        defines = defines,
        additional_compiler_inputs = additional_compiler_inputs,
        features = features,
        target_compatible_with = target_compatible_with,
        **kwargs
    )

def zephyr_module(*, name, config, srcs = [], deps = [], **kwargs):
    """Defines a Zephyr module with Kconfig gating and a marker target.

    Args:
        name: The target name.
        config: The Kconfig symbol that gates this module (e.g., CONFIG_FOO).
        srcs: Source files, compiled only if config is enabled.
        deps: Dependencies, linked only if config is enabled.
        **kwargs: Other arguments passed to zephyr_cc_library.
    """
    gated_args = {}
    gated_attrs = [
        "defines",
        "linkopts",
        "includes",
        "hdrs",
        "copts",
        "local_defines",
    ]

    remaining_kwargs = {}
    for k, v in kwargs.items():
        if k in gated_attrs:
            gated_args[k] = select({
                "@zephyr_kconfig//:" + config + "=true": v,
                "//conditions:default": [],
            })
        else:
            remaining_kwargs[k] = v

    remaining_kwargs.setdefault("visibility", ["//visibility:public"])

    zephyr_cc_library(
        name = name,
        srcs = select({
            "@zephyr_kconfig//:" + config + "=true": srcs,
            "//conditions:default": [],
        }),
        deps = select({
            "@zephyr_kconfig//:" + config + "=true": deps,
            "//conditions:default": [],
        }),
        _is_zephyr_module_call = True,
        **dict(remaining_kwargs, **gated_args)
    )
