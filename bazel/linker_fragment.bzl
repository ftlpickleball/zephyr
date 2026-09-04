# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

LinkerFragmentInfo = provider(
    fields = {
        "fragments": "A depset of structs containing fragment details (file, location, sort_key).",
    },
)

def _zephyr_linker_fragment_impl(ctx):
    """
    Transitively collects all fragments from its dependencies and merges them with its own.
    """
    if ctx.files.srcs and not ctx.attr.location:
        fail("location to insert linker fragment is not specified")

    direct_fragments = [
        struct(
            file = src,
            location = ctx.attr.location,
            sort_key = ctx.attr.sort_key,
        )
        for src in ctx.files.srcs
    ]

    dep_fragments = []
    compilation_contexts = []
    linking_contexts = []

    for dep in ctx.attr.deps:
        if LinkerFragmentInfo in dep:
            dep_fragments.append(dep[LinkerFragmentInfo].fragments)
        if CcInfo in dep:
            cc_info = dep[CcInfo]
            compilation_contexts.append(cc_info.compilation_context)
            if cc_info.linking_context:
                linking_contexts.append(cc_info.linking_context)

    return [
        LinkerFragmentInfo(
            fragments = depset(direct = direct_fragments, transitive = dep_fragments),
        ),
        CcInfo(
            compilation_context = cc_common.merge_compilation_contexts(
                compilation_contexts = compilation_contexts,
            ),
            linking_context = cc_common.merge_linking_contexts(
                linking_contexts = linking_contexts,
            ),
        ),
        # Also provide DefaultInfo so this rule can be used in other contexts if needed.
        DefaultInfo(files = depset(ctx.files.srcs)),
    ]

zephyr_linker_fragment = rule(
    implementation = _zephyr_linker_fragment_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_files = [".ld"],
            doc = "The .ld fragment files for this specific target.",
        ),
        "location": attr.string(
            default = "",
            doc = "The location for this target's fragments (e.g., RODATA).",
        ),
        "sort_key": attr.string(
            default = "default",
            doc = "The sort key for this target's fragments.",
        ),
        # This is the key change: it depends on other fragment targets.
        "deps": attr.label_list(
            doc = "The linker fragment targets that this target depends on.",
        ),
    },
)

# This is the list of all possible snippet files the rule can generate.
SNIPPET_FILENAMES = [
    "snippets-sections.ld",
    "snippets-rom-sections.ld",
    "snippets-ram-sections.ld",
    "snippets-data-sections.ld",
    "snippets-text-sections.ld",
    "snippets-rom-start.ld",
    "snippets-noinit.ld",
    "snippets-rwdata.ld",
    "snippets-rodata.ld",
    "snippets-ramfunc-section.ld",
    "snippets-nocache-section.ld",
    "snippets-itcm-section.ld",
    "snippets-dtcm-section.ld",
    "snippets-pinned-ram-sections.ld",
    "snippets-pinned-data-sections.ld",
    "snippets-pinned-rodata.ld",
    "snippets-text-sections.ld",
]

def _generate_linker_snippets_impl(ctx):
    """Implementation of the rule that generates the snippet-*.ld files."""
    manifest_filename = ctx.label.name + "_manifest.txt"
    manifest_file = ctx.actions.declare_file(manifest_filename)

    # Declare each potential snippet file as an output file.
    output_files = []
    for filename in SNIPPET_FILENAMES:
        output_files.append(ctx.actions.declare_file(filename))

    # Collect the depsets of fragments from all targets.
    all_fragment_depsets = []
    for target in ctx.attr.targets:
        if LinkerFragmentInfo in target:
            all_fragment_depsets.append(target[LinkerFragmentInfo].fragments)

    merged_fragments = depset(transitive = all_fragment_depsets)

    manifest_content = []
    for fragment in merged_fragments.to_list():
        manifest_content.append(
            "{} {} {}".format(fragment.location, fragment.sort_key, fragment.file.path),
        )

    ctx.actions.write(
        output = manifest_file,
        content = "\n".join(manifest_content),
    )

    output_path = manifest_file.path[:-len(manifest_filename)]
    zephyr_root = ctx.file.zephyr_root.dirname
    ctx.actions.run(
        outputs = output_files,
        # Is this transitive needed????
        inputs = depset([manifest_file], transitive = [depset(ctx.files._generator_script)]),
        executable = ctx.executable._generator_script,
        # Pass the output directory to the script. The script will construct the full paths.
        arguments = ["--manifest", manifest_file.path, "--zephyr-root", zephyr_root, "--output-dir", output_path],
        mnemonic = "GenerateLinkerSnippets",
    )

    # Return the list of files and the parent directory.
    # Collect all fragment files to be exported as headers so they are available in the sandbox.
    fragment_files = [f.file for f in merged_fragments.to_list()]

    return [
        DefaultInfo(files = depset(output_files)),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path]),
                headers = depset(output_files + fragment_files),
            ),
        ),
    ]

generate_linker_snippets = rule(
    implementation = _generate_linker_snippets_impl,
    attrs = {
        "targets": attr.label_list(
            doc = "A list of top-level zephyr_linker_fragment targets to collect from.",
        ),
        "zephyr_root": attr.label(
            default = Label("//:BUILD.bazel"),
            allow_single_file = True,
            doc = "Label pointing to Zephyr's root directory.",
        ),
        "_generator_script": attr.label(
            default = Label("//bazel/tools/linker:linker_snippet_generator"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def _generate_app_smem_unaligned_linker_impl(ctx):
    """Generates linker snippets for userspace app partitions (declared by
    K_APPMEM_PARTITION_DEFINE()) from a list of object files (cc_libraries).
    This only collects the declared app mem partitions to the linker snippet,
    and does not handle alignments. This is to be used in the pre0 linker pass.
    """
    filename = "app_smem_unaligned.ld"
    app_smem_unaligned_ld = ctx.actions.declare_file(filename)

    files_to_process = []

    # Retrieve the cc_library target
    for cc_lib in ctx.attr.cc_libs:
        cc_info = cc_lib[CcInfo]

        for linker_input in cc_info.linking_context.linker_inputs.to_list():
            for lib in linker_input.libraries:
                if lib.objects:
                    files_to_process += lib.objects

    # When generating the unaligned app mem linker snippets, the script tool
    # needs to look at relevant object files. There are two options:
    #
    # 1. The script can take a build directory and will scan that directory for
    # object files with the ".obj" suffix. Because Bazel generates object files
    # with the ".o" suffix, this does not work. Providing the build directory
    # is also fragile.
    # 2. The script can take a compile_commands.json that contains paths to the
    # object files. This is the chosen approach.
    # We pass in cc_libraries and find the object files and assemble an
    # artificial compile_commands.json fo the script to consume, even though
    # we are not cmake.
    workspace_root = "."
    entries = []
    for file in files_to_process:
        entries.append("""{{
    "directory": "{}",
    "command" : "-o {}"
}}""".format(workspace_root, file.path))

    fake_compile_commands_json = ctx.actions.declare_file("fake_compile_commands.json")
    content = "[\n" + ",\n".join(entries) + "\n]"

    ctx.actions.write(
        output = fake_compile_commands_json,
        content = content,
    )

    ctx.actions.run(
        outputs = [app_smem_unaligned_ld],
        inputs = [fake_compile_commands_json] + files_to_process,
        executable = ctx.executable._script,
        # This collectes the partitions in given object files matching
        # r'data_smem_([A-Za-z0-9_]*)_(data|bss)*'.
        #
        # This will fail with "KeyError: 'size'" if no file declares
        # "z_libc_partition" (which would happen if CONFIG_USERSPACE=n,
        # and note CONFIG_USERSPACE requires TOOLCHAIN TLS support).
        #
        # If you hit this error and need to debug, the accumulated partitions
        # dictionary in the script should look something like this:
        # [
        # ('z_libc_partition', {'size': 156, 'libraries': ['libc.a']}),
        # ('z_malloc_partition', {'size': 6144}),
        # ('ztest_mem_partition', {'size': 23}),
        # ]
        arguments = [
            "-f",
            fake_compile_commands_json.path,
            "-o",
            app_smem_unaligned_ld.path,
            "-l",
            "libc.a",
            "z_libc_partition",
        ],
        mnemonic = "GenerateAppSmemLd",
    )
    output_path = app_smem_unaligned_ld.path[:-len(filename)]
    return [
        DefaultInfo(files = depset([app_smem_unaligned_ld])),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path]),
                headers = depset([app_smem_unaligned_ld]),
            ),
        ),
    ]

generate_app_smem_unaligned_linker = rule(
    implementation = _generate_app_smem_unaligned_linker_impl,
    attrs = {
        "cc_libs": attr.label_list(mandatory = True, providers = [CcInfo]),
        "_script": attr.label(
            default = Label("//scripts/build:gen_app_partitions"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def _generate_app_smem_aligned_linker_impl(ctx):
    """Generates correctly aligned linker snippets for userspace app
    partitions (declared by K_APPMEM_PARTITION_DEFINE()) from a prebuilt
    ELF file (the result of the pre0 linker pass).
    The generated linker snippets are used in the pre1 and final linker passes.
    """
    filename = "app_smem_aligned.ld"
    app_smem_aligned_ld = ctx.actions.declare_file(filename)

    if not ctx.attr.is_userspace:
        ctx.actions.write(
            output = app_smem_aligned_ld,
            content = "/* Empty app_smem_aligned.ld when CONFIG_USERSPACE is disabled */\n",
        )
    else:
        kernel_elf = ctx.executable.kernel
        ctx.actions.run(
            outputs = [app_smem_aligned_ld],
            inputs = [kernel_elf],
            executable = ctx.executable._script,
            arguments = [
                "-e",
                kernel_elf.path,
                "-o",
                app_smem_aligned_ld.path,
                "-l",
                "libc.a",
                "z_libc_partition",
            ],
            mnemonic = "GenerateAppSmemLd",
        )

    output_path = app_smem_aligned_ld.path[:-len(filename)]
    return [
        DefaultInfo(files = depset([app_smem_aligned_ld])),
        CcInfo(
            compilation_context = cc_common.create_compilation_context(
                includes = depset([output_path]),
                headers = depset([app_smem_aligned_ld]),
            ),
        ),
    ]

generate_app_smem_aligned_linker = rule(
    implementation = _generate_app_smem_aligned_linker_impl,
    attrs = {
        "is_userspace": attr.bool(default = False),
        "kernel": attr.label(
            executable = True,
            cfg = "target",
            mandatory = True,
            doc = "The cc_binary target containing the ELF file.",
        ),
        "_script": attr.label(
            default = Label("//scripts/build:gen_app_partitions"),
            executable = True,
            cfg = "exec",
        ),
    },
)
