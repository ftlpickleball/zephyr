# SPDX-FileCopyrightText: Copyright 2024 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_skylib//rules:copy_file.bzl", "copy_file")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(
    "//bazel:cc_library.bzl",
    _if_compiler_is_clang = "if_compiler_is_clang",
    _if_compiler_is_gcc = "if_compiler_is_gcc",
    _if_linker_is_clang = "if_linker_is_clang",
    _if_linker_is_gcc = "if_linker_is_gcc",
    _if_zephyr_platform = "if_zephyr_platform",
    _manual_tags = "manual_tags",
    _with_zephyr_compatible = "with_zephyr_compatible",
    _zephyr_cc_library = "zephyr_cc_library",
    _zephyr_freestanding_library = "zephyr_freestanding_library",
    _zephyr_module = "zephyr_module",
    _zephyr_soc_library = "zephyr_soc_library",
)
load("//bazel:defs.bzl", "gen_kobject_placeholders", "userspace_gperf_hash_files")
load("//bazel:linker_fragment.bzl", "generate_app_smem_aligned_linker")
load("//bazel:rename_kobject_hash_sections.bzl", "rename_kobject_sections")
load("//bazel:zephyr_linker_script.bzl", "zephyr_linker_script")
load("//bazel:elf_to_hex.bzl", "elf_to_hex")
load("//bazel:elf_to_bin.bzl", "elf_to_bin")
load("//bazel:runfiles.bzl", "resolve_runfiles_path")
load("//bazel:runner.bzl", "zephyr_runners_yaml")
load("//bazel/private:zephyr_transition.bzl", "zephyr_transition")

if_compiler_is_clang = _if_compiler_is_clang
if_compiler_is_gcc = _if_compiler_is_gcc
if_linker_is_clang = _if_linker_is_clang
if_linker_is_gcc = _if_linker_is_gcc
with_zephyr_compatible = _with_zephyr_compatible
zephyr_cc_library = _zephyr_cc_library
zephyr_freestanding_library = _zephyr_freestanding_library
zephyr_module = _zephyr_module
zephyr_soc_library = _zephyr_soc_library

_RUST_TOOLCHAIN_TYPE = "@rules_rust//rust:toolchain_type"

def _rust_runtime_library_paths(ctx):
    """Returns the paths of the Rust toolchain's runtime libraries.

    rules_rust adds the Rust runtime libraries (core, alloc,
    compiler_builtins, ...) and the toolchain's allocator library to the
    CcInfo of every rust_library (rlib), so C/C++ binaries can link rlibs.
    Like libc and the compiler runtime, these must be linked lazily: forcing
    them into --whole-archive pulls in every object, whose references (e.g.
    alloc's references to the global allocator) must then all resolve, and
    compiler_builtins' definitions would take precedence over the C
    toolchain's runtime library.

    Args:
        ctx: The rule context.

    Returns:
        A dict whose keys are the paths of the runtime library archives.
    """
    rust_toolchain = ctx.toolchains[_RUST_TOOLCHAIN_TYPE]
    if not rust_toolchain:
        return {}
    paths = {}
    for field in [
        "libstd_and_allocator_ccinfo",
        "libstd_and_global_allocator_ccinfo",
        "nostd_and_global_allocator_ccinfo",
    ]:
        cc_info = getattr(rust_toolchain, field, None)
        if not cc_info or not cc_info.linking_context:
            continue
        for linker_input in cc_info.linking_context.linker_inputs.to_list():
            for lib in linker_input.libraries:
                for f in [lib.static_library, lib.pic_static_library]:
                    if f:
                        paths[f.path] = True
    return paths

def _toolchain_runtime_library_flags(cc_toolchain, feature_configuration):
    """Returns the C toolchain's runtime library flags (e.g. -lc, -lm).

    These are the -l flags that the C/C++ toolchain adds to every link of an
    executable, i.e. its C/C++ runtime libraries (libc, libm, the compiler
    runtime, ...).

    Args:
        cc_toolchain: The C/C++ toolchain.
        feature_configuration: The feature configuration of the link.

    Returns:
        A list of flags.
    """
    command_line = cc_common.get_memory_inefficient_command_line(
        feature_configuration = feature_configuration,
        action_name = "c++-link-executable",
        variables = cc_common.create_link_variables(
            cc_toolchain = cc_toolchain,
            feature_configuration = feature_configuration,
        ),
    )
    return [arg for arg in command_line if arg.startswith("-l")]

# Why transitive CcInfo transformation is used over grouped flags:
# Passing archives inside a single -Wl,--whole-archive group on the
# linker command line is brittle in Bazel. If an external library (such
# as from Pigweed or rules_cc) natively carries alwayslink = True, it
# emits an inline -Wl,--no-whole-archive flag mid-stream. This
# silently cancels whole-archive extraction for all subsequent libraries.
# Transitive CcInfo wrapping generates independent flag pairs around
# each static archive, preventing flag cancellation while preserving
# native C++ toolchain topological link ordering and deduplication.
def _zephyr_inject_alwayslink_to_deps_impl(ctx):
    cc_toolchain = find_cpp_toolchain(ctx)
    rust_runtime_libs = _rust_runtime_library_paths(ctx)

    def is_generated_static(lib):
        static_library = lib.static_library or lib.pic_static_library
        return bool(
            static_library and
            not static_library.is_source and
            static_library.path not in rust_runtime_libs,
        )

    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )

    new_linker_inputs = []
    rust_runtime_files = []
    seen = {}
    comp_contexts = []
    for dep in ctx.attr.deps:
        if CcInfo not in dep:
            continue
        cc_info = dep[CcInfo]
        comp_contexts.append(cc_info.compilation_context)
        if not cc_info.linking_context:
            continue
        for linker_input in cc_info.linking_context.linker_inputs.to_list():
            lib_files = tuple([
                lib.static_library or lib.pic_static_library or lib.dynamic_library or lib.interface_library
                for lib in linker_input.libraries
            ])
            owner_key = (
                linker_input.owner,
                lib_files,
                tuple(linker_input.user_link_flags),
            )
            if owner_key in seen:
                continue
            seen[owner_key] = True

            # Take out the Rust runtime libraries; they are linked at the end
            # (see below).
            rust_runtime_in_input = [
                lib.static_library or lib.pic_static_library
                for lib in linker_input.libraries
                if (lib.static_library or lib.pic_static_library) and
                   (lib.static_library or lib.pic_static_library).path in rust_runtime_libs
            ]
            if rust_runtime_in_input:
                rust_runtime_files.extend(rust_runtime_in_input)
                add_inputs = linker_input.additional_inputs
                if type(add_inputs) != "depset":
                    add_inputs = depset(add_inputs or [])
                linker_input = cc_common.create_linker_input(
                    owner = linker_input.owner,
                    libraries = depset([
                        lib
                        for lib in linker_input.libraries
                        if (lib.static_library or lib.pic_static_library) not in rust_runtime_in_input
                    ], order = "topological"),
                    user_link_flags = linker_input.user_link_flags,
                    additional_inputs = add_inputs,
                )

            # Pass through untouched if no library requires alwayslink.
            # Precompiled source archives (is_source == True) are external blobs
            # and must not be forced into --whole-archive, nor must the Rust
            # runtime libraries (see _rust_runtime_library_paths).
            needs_wrap = any([
                not lib.alwayslink and is_generated_static(lib)
                for lib in linker_input.libraries
            ])
            if not needs_wrap:
                new_linker_inputs.append(linker_input)
                continue

            new_libraries = []
            for lib in linker_input.libraries:
                if lib.alwayslink or not is_generated_static(lib):
                    new_libraries.append(lib)
                    continue
                new_libraries.append(cc_common.create_library_to_link(
                    actions = ctx.actions,
                    feature_configuration = feature_configuration,
                    cc_toolchain = cc_toolchain,
                    static_library = lib.static_library,
                    pic_static_library = lib.pic_static_library,
                    dynamic_library = lib.dynamic_library,
                    interface_library = lib.interface_library,
                    alwayslink = True,
                ))

            # In Bazel Starlark C++ providers, linker_input.additional_inputs
            # returns a list of files, but create_linker_input requires a depset.
            add_inputs = linker_input.additional_inputs
            if type(add_inputs) != "depset":
                add_inputs = depset(add_inputs or [])

            new_linker_inputs.append(cc_common.create_linker_input(
                owner = linker_input.owner,
                libraries = depset(new_libraries, order = "topological"),
                user_link_flags = linker_input.user_link_flags,
                additional_inputs = add_inputs,
            ))

    # Link the Rust runtime libraries after the C toolchain's runtime
    # libraries. Rust's compiler_builtins defines many symbols that the C
    # runtime also defines (C math functions, mem*, __aeabi_*, ...), as weak
    # symbols. The linker resolves an undefined symbol from the first
    # archive that defines it, so if the Rust runtime libraries came first,
    # C code would use compiler_builtins' definitions instead of the C
    # runtime's, e.g. a math function built for a different float ABI.
    #
    # The C runtime libraries are added by the toolchain at the end of the
    # link, after all user link flags, so list them again here, after all
    # other libraries of the binary and before the Rust runtime libraries.
    # compiler_builtins still provides the symbols that only it defines
    # (e.g. 128-bit integer intrinsics).
    if rust_runtime_files:
        rust_runtime_files = depset(rust_runtime_files).to_list()
        new_linker_inputs.append(cc_common.create_linker_input(
            owner = ctx.label,
            user_link_flags = _toolchain_runtime_library_flags(
                cc_toolchain,
                feature_configuration,
            ) + [f.path for f in rust_runtime_files],
            additional_inputs = depset(rust_runtime_files),
        ))

    if comp_contexts:
        comp_ctx = cc_common.merge_compilation_contexts(
            compilation_contexts = comp_contexts,
        )
    else:
        comp_ctx = cc_common.create_compilation_context()

    runfiles = ctx.runfiles().merge_all([
        dep[DefaultInfo].default_runfiles
        for dep in ctx.attr.deps
        if DefaultInfo in dep and dep[DefaultInfo].default_runfiles
    ])

    return [
        DefaultInfo(runfiles = runfiles),
        CcInfo(
            compilation_context = comp_ctx,
            linking_context = cc_common.create_linking_context(
                linker_inputs = depset(new_linker_inputs, order = "topological"),
            ),
        ),
    ]

_zephyr_inject_alwayslink_to_deps = rule(
    implementation = _zephyr_inject_alwayslink_to_deps_impl,
    attrs = {
        "deps": attr.label_list(),
        "_cc_toolchain": attr.label(
            default = Label("@bazel_tools//tools/cpp:current_cc_toolchain"),
        ),
    },
    toolchains = [
        "@bazel_tools//tools/cpp:toolchain_type",
        config_common.toolchain_type(_RUST_TOOLCHAIN_TYPE, mandatory = False),
    ],
    fragments = ["cpp"],
)

# Wraps binary targets to mirror Zephyr CMake's use of --whole-archive
# without requiring all cc_library deps in the Bazel universe to set
# alwayslink = True as required by Zephyr firmware link semantics.
#
# Why whole-archive extraction is required in all stages (including final):
# - Iterable sections: Zephyr subsystems rely on unreferenced iterable
#   sections (SYS_INIT, SHELL_CMD_REGISTER, ztest). Without whole-archive
#   in the final link, lazy symbol resolution sees zero references to
#   these object files and discards them from zephyr.elf.
# - Symbol convergence: Dropping whole-archive in final strips object
#   files that were present in _pre1, altering memory layouts and
#   invalidating kobject hash tables and section alignment offsets.
def _zephyr_cc_binary_with_alwayslink_deps(*, name, deps, **kwargs):
    _skip_zephyr_compatible = kwargs.pop("_skip_zephyr_compatible", False)
    testonly = kwargs.get("testonly", False)
    tags = _manual_tags(kwargs.pop("tags", None))
    caller_compatible_with = kwargs.pop("target_compatible_with", None)
    target_compatible_with = (
        caller_compatible_with
        if _skip_zephyr_compatible
        else _with_zephyr_compatible(caller_compatible_with)
    )
    deps_name = name + "_alwayslink_deps"
    _zephyr_inject_alwayslink_to_deps(
        name = deps_name,
        deps = deps,
        tags = tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )
    cc_binary(
        name = name,
        deps = [":" + deps_name],
        tags = tags,
        target_compatible_with = target_compatible_with,
        **kwargs
    )

def _zephyr_cc_binary(*, name, deps = [], **kwargs):
    """
    A macro that creates a cc_binary with Zephyr-specific dependencies and options.

    Args:
        name: The name of the final binary
        deps: The dependencies for the app
        **kwargs: Keyword arguments to pass to the cc_binary rule.
    """
    _skip_zephyr_compatible = kwargs.pop("_skip_zephyr_compatible", False)
    testonly = kwargs.get("testonly", False)
    internal_tags = _manual_tags(kwargs.pop("tags", None))
    caller_compatible_with = kwargs.pop("target_compatible_with", None)
    target_compatible_with = (
        caller_compatible_with
        if _skip_zephyr_compatible
        else _with_zephyr_compatible(caller_compatible_with)
    )
    features = kwargs.pop("features", [])
    copts = kwargs.pop("copts", [])
    defines = kwargs.pop("defines", [])
    local_defines = kwargs.pop("local_defines", [])
    includes = kwargs.pop("includes", [])

    zephyr_cc_library(
        name = name + "_srcs_lib",
        srcs = kwargs.pop("srcs", []),
        hdrs = kwargs.pop("hdrs", []),
        testonly = testonly,
        deps = deps,
        copts = copts,
        defines = defines,
        local_defines = local_defines,
        includes = includes,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        _skip_zephyr_compatible = True,
    )

    deps = [
        Label("//include:zephyr"),
        Label("//:autoconf_library"),
        Label("//:autoconf_symbols_to_link"),
        Label("@zephyr_kconfig//:kconfig_warnings"),
        Label("//:dts_cc_library"),
        Label("//arch"),
        Label("//drivers"),
        Label("//subsys"),
        Label("//lib"),
        Label("//:board_deps"),
        ":" + name + "_srcs_lib",
        Label("@zephyr_index//:local_modules"),
    ] + select({
        "//conditions:default": [],
        # gen_device_deps.py reads _DEVICE_STRUCT_HANDLES_OFFSET and
        # _DEVICE_STRUCT_PM_OFFSET from the pass-1 ELF.
        Label("@zephyr_kconfig//:CONFIG_DEVICE_DEPS=true"): [Label("//:offsets_lib")],
    })

    # TODO convert to symbolic macro (https://bazel.build/extending/macros)
    name_pre0 = name + "._pre0.elf"
    target_pre0 = ":" + name_pre0

    # TODO: Modify zephyr_linker_script() to take an additional attribute that
    # is a label_flag for the platform to specify using non-cortex-m linker.
    zephyr_linker_script(
        name = name + "_linker_pre0",
        defines = [
            "LINKER_SCRIPT",
            "_ASMLANGUAGE=1",
            "_LINKER=1",
            "LINKER_APP_SMEM_UNALIGNED",
            "LINKER_DEVICE_DEPS_PASS1=1",
            "CONFIG_STATIC_INIT_GNU=1",  # Hack
        ] + if_linker_is_clang(
            otherwise = [],
            then = [
                "__LLD_LINKER_CMD__=1",
                "CONFIG_LLVM_USE_LLD=1",
            ],
        ) + if_linker_is_gcc(
            otherwise = [],
            then = ["__GCC_LINKER_CMD__=1"],
        ),
        linker_script = Label("//:soc_linkerscript_template_prefinal"),
        deps = [
            Label("//:app_smem_unaligned_ld"),
            Label("//:autoconf_library"),
            Label("//:device_api_sections_ld"),
            Label("//:dts_cc_library"),
            Label("//:extra_linker_includes"),
            Label("//:generated_linker_snippets"),
            Label("//:offsets_header_lib"),
            Label("//include:zephyr"),
            Label("//arch:linker_includes"),
            Label("//include:linker_includes"),
            Label("//soc:linker_includes"),
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_linker_script(
        name = name + "_linker_pre1",
        defines = [
            "LINKER_SCRIPT",
            "_ASMLANGUAGE=1",
            "_LINKER=1",
            "CONFIG_STATIC_INIT_GNU=1",  # Hack
            "LINKER_ZEPHYR_PREBUILT=1",  # Controls the behavior of kobject-xxx.ld
        ] + if_linker_is_clang(
            otherwise = [],
            then = [
                "__LLD_LINKER_CMD__=1",
                "CONFIG_LLVM_USE_LLD=1",
            ],
        ) + if_linker_is_gcc(
            otherwise = [],
            then = ["__GCC_LINKER_CMD__=1"],
        ),
        linker_script = Label("//:soc_linkerscript_template"),
        deps = [
            ":app_smem_aligned_ld_" + name,
            ":kobject_placeholders_" + name,
            Label("//:autoconf_library"),
            Label("//:device_api_sections_ld"),
            Label("//:dts_cc_library"),
            Label("//:extra_linker_includes"),
            Label("//:generated_linker_snippets"),
            Label("//:offsets_header_lib"),
            Label("//arch:linker_includes"),
            Label("//include:linker_includes"),
            Label("//include:zephyr"),
            Label("//soc:linker_includes"),
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_linker_script(
        name = name + "_linker_final",
        defines = [
            "LINKER_SCRIPT",
            "_ASMLANGUAGE=1",
            "_LINKER=1",
            "CONFIG_STATIC_INIT_GNU=1",  # Hack
            "LINKER_ZEPHYR_FINAL=1",
        ] + if_linker_is_clang(
            otherwise = [],
            then = [
                "__LLD_LINKER_CMD__=1",
                "CONFIG_LLVM_USE_LLD=1",
            ],
        ) + if_linker_is_gcc(
            otherwise = [],
            then = ["__GCC_LINKER_CMD__=1"],
        ),
        linker_script = Label("//:soc_linkerscript_template"),
        deps = [
            Label("//:autoconf_library"),
            Label("//:device_api_sections_ld"),
            Label("//:dts_cc_library"),
            Label("//:extra_linker_includes"),
            Label("//:generated_linker_snippets"),
            Label("//:offsets_header_lib"),
            Label("//arch:linker_includes"),
            Label("//include:linker_includes"),
            Label("//include:zephyr"),
            Label("//soc:linker_includes"),
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    # Right now "linker_final_with_userspace" is the same as "linker_final".
    # In a later CL, "linker_final_with_userspace" will depend on linker
    # snippets generated from kernel objects.
    zephyr_linker_script(
        name = name + "_linker_final_with_userspace",
        defines = [
            "LINKER_SCRIPT",
            "_ASMLANGUAGE=1",
            "_LINKER=1",
            "CONFIG_STATIC_INIT_GNU=1",  # Hack
            "LINKER_ZEPHYR_FINAL=1",
        ] + if_linker_is_clang(
            otherwise = [],
            then = [
                "__LLD_LINKER_CMD__=1",
                "CONFIG_LLVM_USE_LLD=1",
            ],
        ) + if_linker_is_gcc(
            otherwise = [],
            then = ["__GCC_LINKER_CMD__=1"],
        ),
        linker_script = Label("//:soc_linkerscript_template"),
        deps = [
            ":app_smem_aligned_ld_" + name,
            ":kobject_placeholders_" + name,
            ":kobject_hash_renamed_" + name,
            Label("//:autoconf_library"),
            Label("//:device_api_sections_ld"),
            Label("//:dts_cc_library"),
            Label("//:extra_linker_includes"),
            Label("//:generated_linker_snippets"),
            Label("//:offsets_header_lib"),
            Label("//arch:linker_includes"),
            Label("//include:linker_includes"),
            Label("//include:zephyr"),
            Label("//soc:linker_includes"),
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    # Force linkage of metadata symbols required for offline introspection.
    linkopts = kwargs.pop("linkopts", []) + [
        "-Wl,-u,_OffsetAbsSyms",
        "-Wl,-u,_ConfigAbsSyms",
    ]

    _zephyr_cc_binary_with_alwayslink_deps(
        name = name_pre0,
        deps = deps + [
            ":" + name + "_linker_pre0",
        ] + select({
            Label("@zephyr_kconfig//:CONFIG_GEN_ISR_TABLES=true"): [Label("//arch/common:isr_tables")],
            "//conditions:default": [],
        }) + select({
            Label("@zephyr_kconfig//:CONFIG_SYMTAB=true"): [Label("//subsys/debug/symtab:symtab_stub")],
            "//conditions:default": [],
        }),
        srcs = [],
        linkopts = linkopts,
        features = features,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        _skip_zephyr_compatible = True,
        **kwargs
    )

    # This requires --strip=never on the bazel build command line.
    userspace_gperf_hash_files(
        name = "prebuilt_gperf_files_" + name,
        kernel = target_pre0,
        struct_tags_json = Label("//:syscall_files"),
        is_userspace = select({
            Label("@zephyr_kconfig//:CONFIG_USERSPACE=true"): True,
            "//conditions:default": False,
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_cc_library(
        name = "kobject_prebuilt_hash_" + name,
        srcs = [":prebuilt_gperf_files_" + name],
        copts = [
            # Need precise control.
            "-fno-function-sections",
            "-fno-data-sections",
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    gen_kobject_placeholders(
        name = "kobject_placeholders_" + name,
        kobj_prebuilt_hash_lib = ":kobject_prebuilt_hash_" + name,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    generate_app_smem_aligned_linker(
        name = "app_smem_aligned_ld_" + name,
        kernel = target_pre0,
        is_userspace = select({
            Label("@zephyr_kconfig//:CONFIG_USERSPACE=true"): True,
            "//conditions:default": False,
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    # Create genrules and dependencies for all isr table combinations. We need the sw isr and irq vector
    # options to be controlled by the normal kconfig selection, so we set up library dependencies controlled
    # by selects that correctly define the dependency graph. Each set of src and linker files are placed in
    # their own folder so that there is no collision if a zephyr_cc_binary is used with multiple platforms
    # that have different configurations.

    # Base gen_isr_tables command used for all configurations. It is formatted with the
    # name, directory, and options.
    gen_isr_tables_tool = Label("//scripts/build:gen_isr_tables")
    cmd_base = """
          ./$(execpath {tools}) \\
              --kernel $(SRCS) \\
              --intlist-section .intList \\
              --intlist-section intList \\
              --output-source $(location {name}.{dir_suffix}/isr_table.c) \\
              {options} \\
    """

    def _get_gen_isr_tables_cmd(dir_suffix, options):
        cmd_le = cmd_base.format(tools = gen_isr_tables_tool, name = name, dir_suffix = dir_suffix, options = options)
        cmd_be = cmd_base.format(tools = gen_isr_tables_tool, name = name, dir_suffix = dir_suffix, options = options + " --big-endian")
        return select({
            Label("@zephyr_kconfig//:CONFIG_BIG_ENDIAN=true"): cmd_be,
            "//conditions:default": cmd_le,
        })

    # Define output_locations
    no_sw_isr_no_vector_outs = [
        "{}._no_sw_isr_no_vector/isr_table.c".format(name),
    ]
    no_sw_isr_vector_outs = [
        "{}._no_sw_isr_vector/isr_table.c".format(name),
    ]
    sw_isr_no_vector_outs = [
        "{}._sw_isr_no_vector/isr_table.c".format(name),
    ]
    sw_isr_vector_outs = [
        "{}._sw_isr_vector/isr_table.c".format(name),
    ]

    # Define the genrules to call Zephyr the gen_isr_tables script.
    native.genrule(
        name = name + "_isr_tables_no_sw_isr_no_vector",
        srcs = [target_pre0],
        outs = no_sw_isr_no_vector_outs,
        cmd = _get_gen_isr_tables_cmd("_no_sw_isr_no_vector", ""),
        tools = [gen_isr_tables_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )
    native.genrule(
        name = name + "_isr_tables_no_sw_isr_vector",
        srcs = [target_pre0],
        outs = no_sw_isr_vector_outs,
        cmd = _get_gen_isr_tables_cmd("_no_sw_isr_vector", "--vector-table"),
        tools = [gen_isr_tables_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )
    native.genrule(
        name = name + "_isr_tables_sw_isr_no_vector",
        srcs = [target_pre0],
        outs = sw_isr_no_vector_outs,
        cmd = _get_gen_isr_tables_cmd("_sw_isr_no_vector", "--sw-isr-table"),
        tools = [gen_isr_tables_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )
    native.genrule(
        name = name + "_isr_tables_sw_isr_vector",
        srcs = [target_pre0],
        outs = sw_isr_vector_outs,
        cmd = _get_gen_isr_tables_cmd("_sw_isr_vector", "--sw-isr-table --vector-table"),
        tools = [gen_isr_tables_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    # Create the libraries to use the correct genrule outputs based on config values.
    zephyr_cc_library(
        name = name + "._isr_tables_sw_isr",
        srcs = select({
            "//conditions:default": [":{}._sw_isr_no_vector/isr_table.c".format(name)],
            Label("@zephyr_kconfig//:CONFIG_GEN_IRQ_VECTOR_TABLE=true"): [":{}._sw_isr_vector/isr_table.c".format(name)],
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )
    zephyr_cc_library(
        name = name + "._isr_tables_no_sw_isr",
        srcs = select({
            "//conditions:default": [":{}._no_sw_isr_no_vector/isr_table.c".format(name)],
            Label("@zephyr_kconfig//:CONFIG_GEN_IRQ_VECTOR_TABLE=true"): [":{}._no_sw_isr_vector/isr_table.c".format(name)],
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    zephyr_cc_library(
        name = name + "._isr_tables",
        deps = select({
            "//conditions:default": [":{}._isr_tables_no_sw_isr".format(name)],
            Label("@zephyr_kconfig//:CONFIG_GEN_SW_ISR_TABLE=true"): [":{}._isr_tables_sw_isr".format(name)],
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    gen_device_deps_tool = Label("//scripts/build:gen_device_deps")
    device_deps_out = "{}._device_deps/device_deps.c".format(name)
    native.genrule(
        name = name + "_gen_device_deps",
        srcs = [
            target_pre0,
            Label("//:edt_pickle"),
        ],
        outs = [device_deps_out],
        cmd = """
            ./$(execpath {tool}) \\
                --kernel $(location {pre0}) \\
                --edt-pickle $(location {edt_pickle}) \\
                --zephyr-base . \\
                --start-symbol _device_list_start \\
                --output-source $@
        """.format(
            tool = gen_device_deps_tool,
            pre0 = target_pre0,
            edt_pickle = Label("//:edt_pickle"),
        ),
        tools = [gen_device_deps_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_cc_library(
        name = name + "._device_deps",
        srcs = [":" + device_deps_out],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    _zephyr_cc_binary_with_alwayslink_deps(
        name = name + "._pre1.elf",
        deps = [
            ":" + name + "_linker_pre1",
            # kobject_prebuilt_hash is not linked to pre1.
            # kobject_prebuilt_hash is only used to generate 3 headers used
            # to inform pre1's linker script of alignment and sizes of
            # data, rodata and stack size.
            # ":kobject_prebuilt_hash",  # userspace.c has weak definitions. With the real one, nm should show "d wordlist"
        ] + deps + select({
            "//conditions:default": [],
            Label("@zephyr_kconfig//:CONFIG_GEN_ISR_TABLES=true"): [":{}._isr_tables".format(name)],
        }) + select({
            "//conditions:default": [],
            Label("@zephyr_kconfig//:CONFIG_DEVICE_DEPS=true"): [":{}._device_deps".format(name)],
        }) + select({
            Label("@zephyr_kconfig//:CONFIG_SYMTAB=true"): [Label("//subsys/debug/symtab:symtab_stub")],
            "//conditions:default": [],
        }),
        linkopts = linkopts + [
            "-Wl,--print-memory-usage",
        ],
        features = features,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        _skip_zephyr_compatible = True,
        **kwargs
    )

    gen_symtab_tool = Label("//scripts/build:gen_symtab")
    native.genrule(
        name = name + "_gen_symtab",
        srcs = select({
            Label("@zephyr_kconfig//:CONFIG_USERSPACE=true"): [":" + name + "._pre1.elf"],
            Label("@zephyr_kconfig//:CONFIG_DEVICE_DEPS=true"): [":" + name + "._pre1.elf"],
            "//conditions:default": [target_pre0],
        }),
        outs = ["{}._symtab/symtab.c".format(name)],
        cmd = "./$(execpath {tool}) -k $(SRCS) -o $(location {name}._symtab/symtab.c)".format(
            tool = gen_symtab_tool,
            name = name,
        ),
        tools = [gen_symtab_tool],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_cc_library(
        name = name + "._symtab",
        srcs = select({
            Label("@zephyr_kconfig//:CONFIG_SYMTAB=true"): [":{}._symtab/symtab.c".format(name)],
            "//conditions:default": [],
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    # This requires --strip=never on the bazel build command line.
    userspace_gperf_hash_files(
        name = "final_gperf_files_" + name,
        kernel = ":" + name + "._pre1.elf",
        struct_tags_json = Label("//:syscall_files"),
        prebuilt = False,
        is_userspace = select({
            Label("@zephyr_kconfig//:CONFIG_USERSPACE=true"): True,
            "//conditions:default": False,
        }),
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    zephyr_cc_library(
        name = "kobject_hash_" + name,
        srcs = [":final_gperf_files_" + name],
        copts = [
            # Need precise control.
            "-fno-function-sections",
            "-fno-data-sections",
        ],
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        _skip_zephyr_compatible = True,
    )

    rename_kobject_sections(
        name = "kobject_hash_renamed_" + name,
        dep = ":kobject_hash_" + name,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    _zephyr_cc_binary_with_alwayslink_deps(
        name = name,
        deps = [] + select({
            "@zephyr_kconfig//:CONFIG_USERSPACE=true": [":" + name + "_linker_final_with_userspace"],
            "@zephyr_kconfig//:CONFIG_DEVICE_DEPS=true": [":" + name + "_linker_final"],
            "//conditions:default": [":" + name + "_linker_final"],
        }) + select({
            # In upstream CMake (CMakeLists.txt:1522), kobject_hash is only generated
            # when CONFIG_USERSPACE is enabled. CONFIG_DEVICE_DEPS enables the multi-stage
            # linking pass for device handle generation (gen_device_deps.py), not kobject hashing.
            "@zephyr_kconfig//:CONFIG_USERSPACE=true": [":kobject_hash_renamed_" + name],
            "//conditions:default": [],
        }) + deps + select({
            "@zephyr_kconfig//:CONFIG_GEN_ISR_TABLES=true": [":{}._isr_tables".format(name)],
            "//conditions:default": [],
        }) + select({
            "@zephyr_kconfig//:CONFIG_DEVICE_DEPS=true": [":{}._device_deps".format(name)],
            "//conditions:default": [],
        }) + select({
            Label("@zephyr_kconfig//:CONFIG_SYMTAB=true"): [":{}._symtab".format(name)],
            "//conditions:default": [],
        }),
        srcs = [],
        linkopts = linkopts + [
            "-Wl,--print-memory-usage",
        ],
        features = features,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        _skip_zephyr_compatible = True,
        **kwargs
    )

def _zephyr_app_impl(ctx):
    # The transition has been applied to this target.
    # We depend on the actual binary, which will now be built in the transitioned configuration.
    if not ctx.attr.binary:
        fail("_zephyr_app_rule requires binary on a Zephyr platform")
    binary_files = ctx.attr.binary[DefaultInfo].files.to_list()
    if not binary_files:
        fail("Binary target %s produced no files" % ctx.attr.binary.label)

    in_file = binary_files[0]
    out_file = ctx.actions.declare_file(ctx.label.name)

    if ctx.file.runners_yaml:
        runners_yaml_path = resolve_runfiles_path(ctx, ctx.file.runners_yaml)
        binary_path = resolve_runfiles_path(ctx, in_file)

        flash_bin = ctx.executable.flash_utils_bin
        flash_bin_path = resolve_runfiles_path(ctx, flash_bin)

        ctx.actions.expand_template(
            template = ctx.file.bootstrapper_template,
            output = out_file,
            substitutions = {
                "{app_name}": ctx.label.name,
                "{runners_yaml}": runners_yaml_path,
                "{binary}": binary_path,
                "{flash_bin}": flash_bin_path,
            },
            is_executable = True,
        )
    else:
        ctx.actions.run_shell(
            inputs = [in_file],
            outputs = [out_file],
            command = "cp %s %s" % (in_file.path, out_file.path),
        )

    # Gather runfiles
    runfiles_list = [
        ctx.attr.binary[DefaultInfo].default_runfiles,
    ]
    if ctx.attr.flash_utils_bin:
        runfiles_list.append(ctx.attr.flash_utils_bin[DefaultInfo].default_runfiles)
    if ctx.attr.runners_yaml:
        runfiles_list.append(ctx.attr.runners_yaml[DefaultInfo].default_runfiles)

    extra_files = [out_file] + binary_files
    if ctx.file.runners_yaml:
        extra_files.append(ctx.file.runners_yaml)
    if ctx.file.config_file:
        extra_files.append(ctx.file.config_file)

    combined_runfiles = ctx.runfiles(files = extra_files).merge_all(runfiles_list)

    return [
        DefaultInfo(
            files = depset([out_file] + binary_files),
            executable = out_file,
            runfiles = combined_runfiles,
        ),
        ctx.attr.binary[OutputGroupInfo],
    ]

_zephyr_app_rule = rule(
    implementation = _zephyr_app_impl,
    attrs = {
        "app_label": attr.string(mandatory = True),
        "binary": attr.label(),
        "runners_yaml": attr.label(allow_single_file = True),
        "config_file": attr.label(allow_single_file = True),
        "bootstrapper_template": attr.label(
            allow_single_file = True,
        ),
        "flash_utils_bin": attr.label(
            executable = True,
            cfg = "exec",
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    executable = True,
    cfg = zephyr_transition,
)

def _zephyr_app_elf_impl(ctx):
    if not ctx.file.binary:
        fail("_zephyr_app_elf requires binary on a Zephyr platform")
    in_file = ctx.file.binary
    out_file = ctx.actions.declare_file(ctx.label.name)

    ctx.actions.symlink(
        output = out_file,
        target_file = in_file,
        is_executable = True,
    )

    return [
        DefaultInfo(
            files = depset([out_file]),
            executable = out_file,
        ),
    ]

_zephyr_app_elf = rule(
    implementation = _zephyr_app_elf_impl,
    attrs = {
        "app_label": attr.string(mandatory = True),
        "binary": attr.label(
            cfg = "target",
            allow_single_file = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    executable = True,
    cfg = zephyr_transition,
)

def _zephyr_app_bin_impl(ctx):
    if not ctx.file.bin:
        fail("_zephyr_app_bin requires bin on a Zephyr platform")
    in_file = ctx.file.bin
    out_file = ctx.actions.declare_file(ctx.label.name)

    ctx.actions.symlink(
        output = out_file,
        target_file = in_file,
    )

    return [
        DefaultInfo(
            files = depset([out_file]),
        ),
    ]

_zephyr_app_bin = rule(
    implementation = _zephyr_app_bin_impl,
    attrs = {
        "app_label": attr.string(mandatory = True),
        "bin": attr.label(
            cfg = "target",
            allow_single_file = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
    cfg = zephyr_transition,
)

def zephyr_app(*, name, app_label = None, **kwargs):
    """
    A macro that creates a Zephyr application with platform transition.

    Args:
        name: The name of the final application target.
        app_label: The label of the application (e.g. //src/main). Defaults to the current package.
        **kwargs: Arguments to pass to _zephyr_cc_binary.
    """
    if not app_label:
        pkg = native.package_name()
        app_label = ("//" + pkg) if pkg else str(native.package_relative_label(name))
    else:
        app_label = str(app_label)

    target_compatible_with = _with_zephyr_compatible(
        kwargs.pop("target_compatible_with", None),
    )

    tags = kwargs.pop("tags", None)
    visibility = kwargs.pop("visibility", None)
    internal_tags = _manual_tags(tags)
    testonly = kwargs.get("testonly", False)

    binary_name = name + "_bin.elf"
    _zephyr_cc_binary(
        name = binary_name,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        visibility = ["//visibility:private"],
        _skip_zephyr_compatible = True,
        **kwargs
    )

    bin_target = name + "_bin_gen"
    elf_to_bin(
        name = bin_target,
        src = ":" + binary_name,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    _zephyr_app_bin(
        name = name + ".bin",
        app_label = app_label,
        bin = _if_zephyr_platform(":" + bin_target),
        tags = tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        visibility = visibility,
    )

    hex_target = name + "_hex_gen"
    elf_to_hex(
        name = hex_target,
        src = ":" + binary_name,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    runners_yaml_name = name + "_runners_yaml"
    zephyr_runners_yaml(
        name = runners_yaml_name,
        runner_config = _if_zephyr_platform(Label("//:board_runner_config")),
        elf = _if_zephyr_platform(":" + binary_name),
        hex = _if_zephyr_platform(":" + hex_target),
        app_label = app_label,
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

    _zephyr_app_rule(
        name = name,
        app_label = app_label,
        binary = _if_zephyr_platform(":" + binary_name),
        runners_yaml = _if_zephyr_platform(":" + runners_yaml_name),
        config_file = _if_zephyr_platform(":" + name + "_copy_config"),
        bootstrapper_template = _if_zephyr_platform(
            Label("//bazel:bootstrapper.py.tpl"),
        ),
        flash_utils_bin = _if_zephyr_platform(
            Label("//bazel/tools/runners:zephyr_flash_utils_bin"),
        ),
        tags = tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        visibility = visibility,
    )

    _zephyr_app_elf(
        name = name + ".elf",
        app_label = app_label,
        binary = _if_zephyr_platform(":" + binary_name),
        tags = tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
        visibility = visibility,
    )

    copy_file(
        name = name + "_copy_config",
        src = Label("//:kconfig_config_file"),
        out = "zephyr/" + name + ".config",
        tags = internal_tags,
        target_compatible_with = target_compatible_with,
        testonly = testonly,
    )

def zephyr_cc_binary(**kwargs):
    """Deprecated: use zephyr_app instead."""
    zephyr_app(**kwargs)
