# SPDX-FileCopyrightText: Copyright 2024 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain", "use_cpp_toolchain")
load("@rules_cc//cc:action_names.bzl", "CPP_LINK_EXECUTABLE_ACTION_NAME", "C_COMPILE_ACTION_NAME")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _get_inputs(ctx):
    all_input_files = [ctx.file.overlay]
    for label in ctx.attr.references:
        if type(label) == "Target" and label.files.to_list():
            all_input_files.extend(label.files.to_list())
        else:
            fail("Unsupported target kind in references:", label)
    if ctx.attr.extra_overlays:
        all_input_files.extend(ctx.attr.extra_overlays.files.to_list())
    return all_input_files

def _package_exec_path(ctx):
    workspace_name = ctx.label.workspace_name
    if workspace_name == "":
        return "."
    return "external/" + workspace_name + "/" + ctx.label.package

def _dts_library_impl(ctx):
    output_dts = ctx.actions.declare_file(ctx.label.name + ".dts")

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )

    # We use the preprocessor from the C compiler
    cpp_executable = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = C_COMPILE_ACTION_NAME,
    )

    include_paths = []
    package_path = ctx.label.package
    if ctx.label.workspace_name:
        package_path = "external/" + ctx.label.workspace_name + "/" + package_path

    for include_target in ctx.attr.includes:
        if CcInfo in include_target:
            compilation_context = include_target[CcInfo].compilation_context
            for inc in compilation_context.includes.to_list():
                include_paths.append("-I" + inc)
            for inc in compilation_context.quote_includes.to_list():
                include_paths.append("-I" + inc)
            for inc in compilation_context.system_includes.to_list():
                include_paths.append("-I" + inc)
        else:
            seen_dirs = {}
            for f in include_target.files.to_list():
                if f.dirname not in seen_dirs:
                    seen_dirs[f.dirname] = True
                    include_paths.append("-I" + f.dirname)

    for dep in ctx.attr.deps:
        if CcInfo in dep:
            compilation_context = dep[CcInfo].compilation_context
            for inc in compilation_context.includes.to_list():
                include_paths.append("-I" + inc)
            for inc in compilation_context.quote_includes.to_list():
                include_paths.append("-I" + inc)
            for inc in compilation_context.system_includes.to_list():
                include_paths.append("-I" + inc)

    # Add package-relative include path
    include_paths.append("-I" + package_path)

    inputs = [ctx.file.overlay] + ctx.files.references

    args = ctx.actions.args()
    args.add("-E")  # Preprocess only
    args.add("-nostdinc")
    args.add("-undef")
    args.add("-D__DTS__")
    args.add("-x", "assembler-with-cpp")
    args.add_all(include_paths)
    args.add("-o", output_dts.path)
    args.add(ctx.file.overlay.path)

    ctx.actions.run(
        inputs = depset(inputs, transitive = [cc_toolchain.all_files]),
        outputs = [output_dts],
        executable = cpp_executable,
        arguments = [args],
        mnemonic = "DtsPreprocess",
        progress_message = "Preprocessing devicetree %s" % ctx.label,
        env = cc_common.get_environment_variables(
            feature_configuration = feature_configuration,
            action_name = C_COMPILE_ACTION_NAME,
            variables = cc_common.create_compile_variables(
                feature_configuration = feature_configuration,
                cc_toolchain = cc_toolchain,
            ),
        ),
    )

    return [
        DefaultInfo(files = depset([output_dts])),
    ]

dts_library = rule(
    implementation = _dts_library_impl,
    attrs = {
        "deps": attr.label_list(allow_files = False),
        "includes": attr.label_list(),
        "overlay": attr.label(mandatory = True, allow_single_file = True),
        "references": attr.label_list(allow_files = True),
        "extra_overlays": attr.label(default = Label("//:extra_dts_overlays")),
        "_cc_toolchain": attr.label(
            default = Label("@rules_cc//cc:current_cc_toolchain"),
        ),
        "_zephyr": attr.label(
            default = Label("//:BUILD.bazel"),
            allow_single_file = True,
        ),
    },
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)

def _dts_cc_library_impl(ctx):
    output_dts = ctx.actions.declare_file("zephyr.dts")
    output_edt_pickle = ctx.actions.declare_file("edt.pickle")
    output_header_name = "zephyr/devicetree_generated.h"
    output_header = ctx.actions.declare_file(output_header_name)
    dts_file = ctx.attr.dts_lib[DefaultInfo].files.to_list()[0]
    bindings_files = []
    bindings_dirs = []

    for bindings_file_provider in ctx.attr.bindings:
        provider = bindings_file_provider[DefaultInfo].files.to_list()
        bindings_files.extend(provider)
        bindings_dirs += [f.dirname for f in provider]

    gen_defines_target = ctx.attr._gen_defines[DefaultInfo]
    gen_edt_target = ctx.attr._gen_edt[DefaultInfo]
    inputs = gen_defines_target.files.to_list() + gen_edt_target.files.to_list() + [dts_file] + bindings_files

    ctx.actions.run(
        inputs = inputs,
        outputs = [output_edt_pickle, output_dts],
        executable = gen_edt_target.files_to_run.executable,
        arguments = [
            "--edt-pickle-out",
            output_edt_pickle.path,
            "--dts",
            dts_file.path,
            "--bindings-dirs",
        ] + depset(bindings_dirs).to_list() + [
            # "--bindings-dirs",
            # "external/zephyr/dts/bindings",
            "--dts-out",
            output_dts.path,
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ],
        mnemonic = "DtsGenEdtPickle",
        progress_message = "Generating EDT pickle",
    )

    args = [
        "--header-out",
        output_header.path,
        "--edt-pickle",
        output_edt_pickle.path,
    ]
    ctx.actions.run(
        inputs = inputs + [output_edt_pickle],
        outputs = [output_header],
        executable = gen_defines_target.files_to_run.executable,
        arguments = args,
        mnemonic = "DtsGenDefines",
        progress_message = "Running DTS definition generator",
    )
    return [
        DefaultInfo(
            files = depset([output_header, output_dts]),
        ),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([
                    output_header.dirname,
                    output_header.dirname + "/..",
                ]),
                quote_includes = depset([
                    output_header.dirname,
                    output_header.dirname + "/..",
                ]),
                system_includes = depset([
                    output_header.dirname,
                    output_header.dirname + "/..",
                ]),
                headers = depset([output_header]),
            ),
        ),
    ]

dts_cc_library = rule(
    implementation = _dts_cc_library_impl,
    attrs = {
        "dts_lib": attr.label(allow_files = False),
        "bindings": attr.label_list(allow_files = True),
        "_gen_defines": attr.label(
            default = "//scripts/dts:gen_defines",
            executable = True,
            cfg = "exec",
        ),
        "_gen_edt": attr.label(
            default = "//scripts/dts:gen_edt",
            executable = True,
            cfg = "exec",
        ),
    },
    provides = [CcInfo],
)

StructTagsInfo = provider(
    doc = "Holds the struct_tags.json parsed from syscalls",
    fields = ["json_file"],
)

def _syscall_library_files_impl(ctx):
    syscalls_json = ctx.actions.declare_file("syscalls.json")
    struct_tags_json = ctx.actions.declare_file("struct_tags.json")
    syscall_file_list = ctx.actions.declare_file("syscalls_file_list.txt")

    # Collect the client headers from all targets.
    transitive_client_headers = []
    for filegroup in ctx.attr.client_files:
        transitive_client_headers.append(filegroup[DefaultInfo].files)

    all_client_headers_depset = depset(transitive = transitive_client_headers)
    all_client_headers = all_client_headers_depset.to_list()

    ctx.actions.write(
        output = syscall_file_list,
        content = ";".join([f.path for f in all_client_headers]),
    )

    scan_dirs = depset([f.dirname for f in all_client_headers])
    include_list = []
    for d in scan_dirs.to_list():
        include_list += ["--include", d]

    scan_list = []
    root_path = _package_exec_path(ctx)
    scan_list += ["--scan", root_path + "include"]
    scan_list += ["--scan", root_path + "drivers"]
    scan_list += ["--scan", root_path + "subsys/net"]

    # Bazel sandboxing requires scanned files to be in the action inputs, so we
    # add the scan_files attribute. Otherwise sandboxing would hide the scan
    # directories from the action.
    ctx.actions.run(
        inputs = all_client_headers + [syscall_file_list] + ctx.files.scan_files,
        outputs = [syscalls_json, struct_tags_json],
        executable = ctx.attr._parse_syscalls[DefaultInfo].files_to_run.executable,
        arguments = scan_list + include_list + [
            "--json-file",
            syscalls_json.path,
            "--tag-struct-file",
            struct_tags_json.path,
            "--file-list",
            syscall_file_list.path,
        ],
        mnemonic = "ParseSyscalls",
        progress_message = "Parsing syscalls",
    )

    out_dir = ctx.actions.declare_directory("include/generated/zephyr")

    ctx.actions.run(
        inputs = [syscalls_json],
        outputs = [out_dir],
        executable = ctx.attr._gen_syscalls[DefaultInfo].files_to_run.executable,
        arguments = [
            "--json-file",
            syscalls_json.path,
            "--base-output",
            out_dir.path + "/syscalls",
            "--syscall-dispatch",
            out_dir.path + "/syscall_dispatch.c",
            "--syscall-list",
            out_dir.path + "/syscall_list.h",
            # Technically this should only apply when CONFIG_USERSPACE is set,
            # but it doesn't seem to hurt non-userspace builds.
            "--gen-mrsh-files",
        ],
        mnemonic = "GenSyscalls",
        progress_message = "Generating syscalls",
    )

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )

    compilation_context, compilation_outputs = cc_common.compile(
        name = ctx.label.name,
        actions = ctx.actions,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        # Make the dynamic files available to the sandbox.
        srcs = [out_dir],
        private_hdrs = [out_dir],
        # Tell the compiler where to look.
        user_compile_flags = ["-I" + out_dir.path],
    )

    linking_context, linking_outputs = cc_common.create_linking_context_from_compilation_outputs(
        actions = ctx.actions,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        compilation_outputs = compilation_outputs,
        name = ctx.label.name,
    )
    return [
        DefaultInfo(files = depset([out_dir])),
        # The generated .h and .c files are used to compile the syscall
        # header library with a dispatch table and weak definitions.
        CcInfo(
            compilation_context = compilation_context,
            linking_context = linking_context,
        ),
        StructTagsInfo(json_file = struct_tags_json),
    ]

# Collects filegroups that use syscalls, and generates .h and .c files
# necessary for the syscall header library. The output should be consumed by
# a cc_library.
syscall_library_files = rule(
    implementation = _syscall_library_files_impl,
    attrs = {
        "client_files": attr.label_list(
            doc = "A list of filegroups to collect syscall usage from.",
            allow_files = True,
        ),
        "scan_files": attr.label_list(allow_files = True),
        "_parse_syscalls": attr.label(
            default = "//scripts/build:parse_syscalls",
            executable = True,
            cfg = "exec",
        ),
        "_gen_syscalls": attr.label(
            default = "//scripts/build:gen_syscalls",
            executable = True,
            cfg = "exec",
        ),
        "_cc_toolchain": attr.label(
            default = Label("@rules_cc//cc:current_cc_toolchain"),
        ),
    },
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)

def _device_api_linker_files_impl(ctx):
    output_filename = "device-api-sections.ld"
    device_api_sections_ld = ctx.actions.declare_file(output_filename)

    # We don't need the generated cmake file, but zephyr's script requires one
    # file as an argument.
    device_api_sections_cmake = ctx.actions.declare_file("unused-device-api-sections.cmake")
    struct_tags_json = ctx.attr.dep[StructTagsInfo].json_file
    output_path = device_api_sections_ld.path[:-len(output_filename)]

    ctx.actions.run(
        inputs = [struct_tags_json],
        outputs = [device_api_sections_ld, device_api_sections_cmake],
        executable = ctx.attr._gen_iter_sections[DefaultInfo].files_to_run.executable,
        arguments = [
            "--alignment",
            "4",  # This should be CONFIG_LINKER_ITERABLE_SUBALIGN to be precise.
            "--input",
            struct_tags_json.path,
            "--tag",
            "__subsystem",
            "--ld-output",
            device_api_sections_ld.path,
            "--cmake-output",
            device_api_sections_cmake.path,
        ],
        mnemonic = "GenDeviceApiSectionsLd",
        progress_message = "Generating device-api-sections.ld",
    )
    return [
        DefaultInfo(files = depset([device_api_sections_ld])),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path]),
                headers = depset([device_api_sections_ld]),
            ),
        ),
    ]

# Generates device-api-sections.ld from a JSON file of used device drivers.
device_api_linker_files = rule(
    implementation = _device_api_linker_files_impl,
    attrs = {
        "dep": attr.label(providers = [StructTagsInfo], mandatory = True),
        "_gen_iter_sections": attr.label(
            default = "//scripts/build:gen_iter_sections",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _driver_validation_file_impl(ctx):
    output_filename = "zephyr/driver-validation.h"
    driver_validation_h = ctx.actions.declare_file(output_filename)
    struct_tags_json = ctx.attr.dep[StructTagsInfo].json_file
    output_path = driver_validation_h.path[:-len(output_filename)]

    ctx.actions.run(
        inputs = [struct_tags_json],
        outputs = [driver_validation_h],
        executable = ctx.attr._gen_kobject_list[DefaultInfo].files_to_run.executable,
        arguments = [
            "--include-subsystem-list",
            struct_tags_json.path,
            "--validation-output",
            driver_validation_h.path,
        ],
        mnemonic = "GenDriverValidationHdr",
        progress_message = "Generating driver-validation.h",
    )
    return [
        DefaultInfo(files = depset([driver_validation_h])),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path, output_path + "zephyr"]),
                quote_includes = depset([output_path, output_path + "zephyr"]),
                system_includes = depset([output_path, output_path + "zephyr"]),
                headers = depset([driver_validation_h]),
            ),
        ),
    ]

# Generates driver-validation.h from a JSON file of used device drivers.
driver_validation_file = rule(
    implementation = _driver_validation_file_impl,
    attrs = {
        "dep": attr.label(providers = [StructTagsInfo], mandatory = True),
        "_gen_kobject_list": attr.label(
            default = "//scripts/build:gen_kobject_list",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _userspace_gperf_hash_files_impl(ctx):
    """Uses the gperf tool to create a perfect hash table for kernel objects,
    used to check syscall arguments against known kernel objects when syscalls
    are called from userspace. This is standard Zephyr operation.

    When attr.prebuilt is True, this generates the prebuilt hash table that
    has the right sizes but wrong addresses of kernel objects; this is so that
    the hash table itself gets placed to the right address in the ELF and the
    address of the hash table doesn't change from prebuilt to final ELF.

    When attr.prebuilt is False, this generates the real hash table that has
    the correct addresses of kernel objects.
    """
    gperf_list_filename = "zephyr/kobject_prebuilt_hash.gperf"
    if not ctx.attr.prebuilt:
        gperf_list_filename = "zephyr/kobject_hash.gperf"

    gperf_list = ctx.actions.declare_file(gperf_list_filename)
    struct_tags_json = ctx.attr.struct_tags_json[StructTagsInfo].json_file
    kernel_elf = ctx.executable.kernel

    ctx.actions.run(
        inputs = [struct_tags_json, kernel_elf],
        outputs = [gperf_list],
        executable = ctx.attr._gen_kobject_list[DefaultInfo].files_to_run.executable,
        arguments = [
            "--include-subsystem-list",
            struct_tags_json.path,
            "--kernel",
            kernel_elf.path,
            "--gperf-output",
            gperf_list.path,
        ],
        mnemonic = "GenKobjGperfHashList",
        progress_message = "Generating kobject gperf input list",
    )

    gperf_hash_output_src_pre_filename = "zephyr/kobject_prebuilt_hash_preprocessed.c"
    if not ctx.attr.prebuilt:
        gperf_hash_output_src_pre_filename = "zephyr/kobject_hash_preprocessed.c"
    gperf_hash_output_src_pre = ctx.actions.declare_file(gperf_hash_output_src_pre_filename)

    ctx.actions.run(
        inputs = [gperf_list],
        outputs = [gperf_hash_output_src_pre],
        executable = ctx.attr._gperf[DefaultInfo].files_to_run.executable,
        arguments = [
            "--output-file",
            gperf_hash_output_src_pre.path,
            "--multiple-iterations",
            "10",
            gperf_list.path,
        ],
        mnemonic = "GenKobjGperfHashSrcPre",
    )

    gperf_hash_output_src_filename = "zephyr/kobject_prebuilt_hash.c"
    if not ctx.attr.prebuilt:
        gperf_hash_output_src_filename = "zephyr/kobject_hash.c"
    gperf_hash_output_src = ctx.actions.declare_file(gperf_hash_output_src_filename)
    ctx.actions.run(
        inputs = [gperf_hash_output_src_pre],
        outputs = [gperf_hash_output_src],
        executable = ctx.attr._process_gperf[DefaultInfo].files_to_run.executable,
        arguments = [
            "-i",
            gperf_hash_output_src_pre.path,
            "-o",
            gperf_hash_output_src.path,
            "-p",
            "struct k_object",
        ],
        mnemonic = "GenKobjGperfHashSrc",
        progress_message = "Generating kobject hash source file",
    )

    return [
        DefaultInfo(files = depset([gperf_hash_output_src])),
    ]

userspace_gperf_hash_files = rule(
    implementation = _userspace_gperf_hash_files_impl,
    attrs = {
        "struct_tags_json": attr.label(providers = [StructTagsInfo], mandatory = True),
        "kernel": attr.label(
            executable = True,
            cfg = "target",
            mandatory = True,
            doc = "The cc_binary target containing the ELF file.",
        ),
        "prebuilt": attr.bool(default = True),
        "_gperf": attr.label(
            default = "@gperf//:gperf",
            executable = True,
            cfg = "exec",
        ),
        "_gen_kobject_list": attr.label(
            default = "//scripts/build:gen_kobject_list",
            executable = True,
            cfg = "exec",
        ),
        "_process_gperf": attr.label(
            default = "//scripts/build:process_gperf",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _gen_kobject_placeholders_impl(ctx):
    """Generates headers to reserve space for kernel objects in linker scripts.
    """
    cc_info = ctx.attr.kobj_prebuilt_hash_lib[CcInfo]

    obj_file = None
    for linker_input in cc_info.linking_context.linker_inputs.to_list():
        for lib in linker_input.libraries:
            for obj in lib.objects:
                if obj.path.endswith("kobject_prebuilt_hash.o"):
                    obj_file = obj
                    break

    if not obj_file:
        fail("did not find kobject_prebuilt_hash.o. This rule needs a correct kobj_prebuilt_hash_lib")

    out_dir = ctx.actions.declare_directory("include/generated/zephyr")

    # The script generates 3 files used to reserve space in the linker script:
    #    linker_kobject_prebuild_data.h
    #    linker_kobject_prebuild_priv_stacks.h
    #    linker_kobject_prebuild_rodata.h
    ctx.actions.run(
        outputs = [out_dir],
        inputs = [obj_file],
        executable = ctx.executable._gen_kobject_placeholders,
        arguments = [
            "--object",
            obj_file.path,
            "--outdir",
            out_dir.path,
            # TODO: Double-check these number literals. They may need to come
            # from Kconfig in rare cases.
            "--datapct",
            "100",
            "--rodata",
            "16",
        ],
        mnemonic = "GenerateAppSmemLd",
    )

    compilation_context = cc_common.create_compilation_context(
        # 'headers' tells Bazel to pull this directory into the sandbox
        # for any downstream C++ rules that depend on this target.
        headers = depset([out_dir]),

        # 'includes' adds an implicit "-I" flag to the compiler.
        # This allows downstream rules to #include "my_header.h" directly,
        # rather than typing the full bazel-out/.../ path.
        includes = depset([out_dir.path[:-len("zephyr")]]),
    )
    return [
        DefaultInfo(files = depset([out_dir])),
        CcInfo(compilation_context = compilation_context),
    ]

gen_kobject_placeholders = rule(
    implementation = _gen_kobject_placeholders_impl,
    attrs = {
        "kobj_prebuilt_hash_lib": attr.label(mandatory = True, providers = [CcInfo]),
        "_gen_kobject_placeholders": attr.label(
            default = "//scripts/build:gen_kobject_placeholders",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _kobj_types_enum_file_impl(ctx):
    output_filename = "zephyr/kobj-types-enum.h"
    kobj_types_enum_h = ctx.actions.declare_file(output_filename)
    struct_tags_json = ctx.attr.dep[StructTagsInfo].json_file
    output_path = kobj_types_enum_h.path[:-len(output_filename)]

    otype_to_str_h = ctx.actions.declare_file("zephyr/otype-to-str.h")
    otype_to_size_h = ctx.actions.declare_file("zephyr/otype-to-size.h")

    output_files = [kobj_types_enum_h, otype_to_str_h, otype_to_size_h]

    ctx.actions.run(
        inputs = [struct_tags_json],
        outputs = output_files,
        executable = ctx.attr._gen_kobject_list[DefaultInfo].files_to_run.executable,
        arguments = [
            "--include-subsystem-list",
            struct_tags_json.path,
            "--kobj-types-output",
            kobj_types_enum_h.path,
            "--kobj-otype-output",
            otype_to_str_h.path,
            "--kobj-size-output",
            otype_to_size_h.path,
        ],
        mnemonic = "GenKobjTypesEnum",
        progress_message = "Generating kobj-types-enum.h",
    )
    return [
        DefaultInfo(files = depset(output_files)),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path, output_path + "zephyr"]),
                quote_includes = depset([output_path, output_path + "zephyr"]),
                system_includes = depset([output_path, output_path + "zephyr"]),
                headers = depset(output_files),
            ),
        ),
    ]

# Generates kobj-types-enum.h from a JSON file of used device drivers.
kobj_types_enum_file = rule(
    implementation = _kobj_types_enum_file_impl,
    attrs = {
        "dep": attr.label(providers = [StructTagsInfo], mandatory = True),
        "_gen_kobject_list": attr.label(
            default = "//scripts/build:gen_kobject_list",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _zephyr_final_binary_impl(ctx):
    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    cxx_linker_path = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = CPP_LINK_EXECUTABLE_ACTION_NAME,
    )

    output_elf = ctx.actions.declare_file(ctx.label.name)

    ctx.actions.run(
        inputs = depset(
            direct = [ctx.executable.pre0_elf, ctx.file.lds],
            transitive = [cc_toolchain.all_files],
        ),
        outputs = [output_elf],
        arguments = [
            "-T",
            ctx.file.lds.path,
            ctx.executable.pre0_elf.path,
            "-o",
            output_elf.path,
        ],
        executable = cxx_linker_path,
        tools = cc_toolchain.all_files,
        mnemonic = "Linking",
    )
    return [
        DefaultInfo(
            files = depset([output_elf, ctx.executable.pre0_elf]),
            executable = output_elf,
        ),
    ]

zephyr_final_binary = rule(
    implementation = _zephyr_final_binary_impl,
    attrs = {
        "lds": attr.label(
            mandatory = True,
            allow_single_file = True,
        ),
        "pre0_elf": attr.label(
            mandatory = True,
            executable = True,
            cfg = "target",
        ),
        "_cc_toolchain": attr.label(
            default = Label("@rules_cc//cc:current_cc_toolchain"),
        ),
    },
    executable = True,
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)

def _zephyr_offset_header_impl(ctx):
    output_file = ctx.actions.declare_file(ctx.attr.output)

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )

    compilation_context = ctx.attr.lib[CcInfo].compilation_context

    # We compile the provided source file with the library's compilation context.

    # We must explicitly add the include paths to user_compile_flags because
    # cc_common.compile might not add them for -include.
    user_compile_flags = []
    user_compile_flags.extend(ctx.attr.copts)
    for inc in compilation_context.includes.to_list():
        user_compile_flags.append("-I" + inc)
    for inc in compilation_context.quote_includes.to_list():
        user_compile_flags.append("-I" + inc)
    for inc in compilation_context.system_includes.to_list():
        user_compile_flags.append("-I" + inc)

    all_compilation_contexts = [compilation_context]
    if ctx.files.hdrs or ctx.attr.includes:
        extra_ctx = cc_common.create_compilation_context(
            headers = depset(ctx.files.hdrs),
            includes = depset(ctx.attr.includes),
            quote_includes = depset(ctx.attr.includes),
        )
        all_compilation_contexts.append(extra_ctx)

    for inc in ctx.attr.includes:
        user_compile_flags.append("-I" + inc)

    _, compilation_outputs = cc_common.compile(
        name = ctx.label.name,
        actions = ctx.actions,
        feature_configuration = feature_configuration,
        cc_toolchain = cc_toolchain,
        srcs = [ctx.file.src],
        user_compile_flags = user_compile_flags,
        compilation_contexts = all_compilation_contexts,
    )

    # Get the command line args that the toolchain is configured with.
    # This is needed for Xtensa, which requires the core to be specified
    # as an argument on the toolchain command line.
    cc_variables = cc_common.create_compile_variables(
        cc_toolchain = cc_toolchain,
        feature_configuration = feature_configuration,
    )
    command_line_args = cc_common.get_memory_inefficient_command_line(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.cpp_link_static_library,
        variables = cc_variables,
    )
    filtered_args = []
    for arg in command_line_args:
        # rules_cc adds 'rcsD' to the cpp_link_static_library action, but that
        # is not what we want here - we are extracting, not creating. So skip
        # this argument but keep the other ones.
        if arg != "rcsD":
            filtered_args.append(arg)

    if not compilation_outputs.objects:
        if compilation_outputs.pic_objects:
            offsets_obj = compilation_outputs.pic_objects[0]
        else:
            fail("No object files produced by CompileOffsets for %s" % ctx.file.src.path)
    else:
        offsets_obj = compilation_outputs.objects[0]

    # Now run the extraction tool
    ctx.actions.run(
        inputs = [offsets_obj],
        outputs = [output_file],
        executable = ctx.executable.tool,
        arguments = ["-i", offsets_obj.path, "-o", output_file.path],
        mnemonic = "GenOffsetHeader",
    )

    output_dir = output_file.dirname
    parent_dir = output_file.dirname.rpartition("/")[0] if "/" in output_file.dirname else "."
    return [
        DefaultInfo(files = depset([output_file])),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                headers = depset([output_file]),
                includes = depset([output_dir, parent_dir]),
                quote_includes = depset([output_dir, parent_dir]),
                system_includes = depset([output_dir, parent_dir]),
            ),
        ),
    ]

zephyr_offset_header = rule(
    implementation = _zephyr_offset_header_impl,
    attrs = {
        "lib": attr.label(mandatory = True, allow_files = False, providers = [CcInfo]),
        "src": attr.label(mandatory = True, allow_single_file = True),
        "hdrs": attr.label_list(allow_files = True),
        "includes": attr.string_list(),
        "tool": attr.label(executable = True, allow_files = False, mandatory = True, cfg = "exec"),
        "output": attr.string(mandatory = True),
        "copts": attr.string_list(),
        "_cc_toolchain": attr.label(
            default = Label("@rules_cc//cc:current_cc_toolchain"),
        ),
    },
    toolchains = use_cpp_toolchain(),
    fragments = ["cpp"],
)
