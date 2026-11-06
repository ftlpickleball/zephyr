# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Repository rule for the global Zephyr Kconfig schema."""

load("//bazel/private:deps.bzl", "label_path", "new_tracker", "read_path_list", "realpath_of", "repo_root", "watch_deps", "watch_pins", "watch_workspace_manifest")
load("//bazel/private:kconfig_args.bzl", "get_kconfig_args", "resolve_module_roots")
load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")

def _zephyr_kconfig_schema_impl(rctx):
    # Inputs in other repositories are recorded first: they are the only ones that make
    # re-verification expensive (see deps.bzl).
    context = json.decode(rctx.attr.context)
    tracker = new_tracker(rctx, zephyr_manifest = "kconfig_done")
    zephyr_root = repo_root(tracker, Label("//:BUILD.bazel"))
    zephyr_root_path = str(zephyr_root)

    kconfig_gen_symbols_py = label_path(tracker, rctx.attr._kconfig_gen_symbols_py)
    kconfig_utils_py = label_path(tracker, Label("//bazel/tools/kconfig:kconfig_utils.py"))

    python = get_python(rctx, extra_import_paths = [
        zephyr_root_path + "/scripts/kconfig",
        zephyr_root_path + "/bazel/tools/deps",
        str(kconfig_gen_symbols_py.dirname),
    ])

    resolved_board_dirs = []
    for b_label in rctx.attr.board_dirs:
        path_str = str(label_path(tracker, b_label).dirname)
        if path_str not in resolved_board_dirs:
            resolved_board_dirs.append(path_str)

    resolved_oot_dts_roots = []
    for r_label_str in context["oot_dts_roots"]:
        r_path = label_path(tracker, r_label_str)
        if not r_path.exists:
            r_path = r_path.dirname
        resolved_oot_dts_roots.append(str(r_path))

    resolved_modules = resolve_module_roots(tracker, context["modules"])

    resolved_build_files = []
    for b_label in rctx.attr.app_build_files:
        b_path = label_path(tracker, b_label)
        if not b_path.exists:
            b_path = b_path.dirname
        path_str = str(b_path)
        if path_str not in resolved_build_files:
            resolved_build_files.append(path_str)

    # watch_deps() records no DIRENTS, so in a downstream workspace new Kconfig, binding, board
    # metadata and BUILD/.bzl files in workspace modules and board roots are noticed through this
    # digest of their names (zephyr_setup may re-run without changing this rule's attributes).
    watch_workspace_manifest(tracker)

    args = get_kconfig_args(
        script = kconfig_gen_symbols_py,
        zephyr_root = zephyr_root_path,
        modules = resolved_modules,
        output = "BUILD.bazel",
        board_dirs = resolved_board_dirs,
        oot_dts_roots = resolved_oot_dts_roots,
        build_files = resolved_build_files,
    )

    result = python.execute(args)
    if result.return_code != 0:
        fail("Kconfig schema generation failed: %s" % result.stderr)
    elif result.stderr:
        print(result.stderr)

    # The generator lists every file it read (Kconfig files, board metadata, and the BUILD/.bzl
    # files it scans for configuration values) and every directory it walked, as realpaths. Only
    # mutable locations get watched; fetched content is covered by the pin files and probes.
    deps = (read_path_list(rctx, rctx.path("deps.txt")) or []) + [
        realpath_of(p)
        for p in [kconfig_gen_symbols_py, kconfig_utils_py]
    ]
    dep_dirs = read_path_list(rctx, rctx.path("dep_dirs.txt")) or []

    watch_pins(tracker, context["pin_files"])
    watch_deps(tracker, files = deps, dirs = dep_dirs)

    rctx.delete("deps.txt")
    rctx.delete("dep_dirs.txt")

    return rctx.repo_metadata(reproducible = True)

zephyr_kconfig_schema = repository_rule(
    implementation = _zephyr_kconfig_schema_impl,
    attrs = {
        "app_build_files": attr.string_list(
            doc = "Canonical labels of the BUILD files of out-of-tree application packages, from discovery.",
        ),
        "board_dirs": attr.string_list(
            doc = "Canonical labels of the BUILD files of all board packages, from discovery.",
        ),
        "context": attr.string(
            mandatory = True,
            doc = "JSON with the module roots, OOT DTS roots and pin files (the zc repos' context.json).",
        ),
        "_kconfig_gen_symbols_py": attr.label(default = "//bazel/tools/kconfig:kconfig_gen_symbols.py"),
        "_pip_deps": attr.label_list(
            default = [
                "@zephyr_pip_deps//pyyaml",
            ],
        ),
    } | COMMON_PY_REPO_RULE_ATTRS,
)
