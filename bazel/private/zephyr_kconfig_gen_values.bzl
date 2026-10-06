# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Repository rule for app-board specific Zephyr configuration. (forced update)"""

load("//bazel:naming.bzl", "normalize_app_label")
load("//bazel/private:deps.bzl", "label_path", "new_tracker", "read_path_list", "realpath_of", "repo_root", "watch_deps", "watch_pins")
load("//bazel/private:kconfig_args.bzl", "get_kconfig_args", "resolve_module_roots")
load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")

def _gen_zephyr_config_impl(rctx):
    # Inputs in other repositories are recorded first: they are the only ones that make
    # re-verification expensive (see deps.bzl). The context holds what all configurations share
    # (module roots, OOT DTS roots, pin files); per-configuration data comes from attributes, so
    # discovering a new app or board does not invalidate existing configurations.
    context = json.decode(rctx.read(rctx.attr._context))
    tracker = new_tracker(rctx)
    zephyr_root = repo_root(tracker, Label("//:BUILD.bazel"))
    zephyr_root_path = str(zephyr_root)

    kconfig_gen_values_py = label_path(tracker, rctx.attr._kconfig_gen_values_py)
    kconfig_utils_py = label_path(tracker, Label("//bazel/tools/kconfig:kconfig_utils.py"))

    python = get_python(rctx, extra_import_paths = [
        zephyr_root_path + "/scripts/kconfig",
        zephyr_root_path + "/bazel/tools/deps",
        str(kconfig_gen_values_py.dirname),
    ])

    if not rctx.attr.app_dir:
        # Robust normalization: strip repo and redundant target name
        norm_app = normalize_app_label(rctx.attr.app_label)
        fail("App %s (normalized: %s) not found in discovery index." % (rctx.attr.app_label, norm_app))
    app_dir_path = str(label_path(tracker, rctx.attr.app_dir).dirname)

    if not rctx.attr.board_dir:
        fail("Board %s not found in discovery index" % rctx.attr.board_id)
    board_dir_path = str(label_path(tracker, rctx.attr.board_dir).dirname)

    resolved_oot_dts_roots = [str(label_path(tracker, l).dirname) for l in context["oot_dts_roots"]]

    resolved_modules = resolve_module_roots(tracker, context["modules"])

    resolved_conf_fragments = []
    for fragment in rctx.attr.conf_fragments:
        if not fragment.startswith("/"):
            fragment_path = rctx.path(str(rctx.workspace_root) + "/" + fragment)
        else:
            fragment_path = rctx.path(fragment)
        resolved_conf_fragments.append(str(fragment_path))

    resolved_dtc_overlays = []
    for overlay in rctx.attr.dtc_overlays:
        if not overlay.startswith("/"):
            overlay_path = rctx.path(str(rctx.workspace_root) + "/" + overlay)
        else:
            overlay_path = rctx.path(overlay)
        resolved_dtc_overlays.append(str(overlay_path))

    if rctx.attr.extra_kconfig:
        rctx.file("sysbuild_generated.conf", rctx.attr.extra_kconfig)
        resolved_conf_fragments.append(str(rctx.path("sysbuild_generated.conf")))

    args = get_kconfig_args(
        script = kconfig_gen_values_py,
        zephyr_root = zephyr_root_path,
        modules = resolved_modules,
        app_dir = app_dir_path,
        board = rctx.attr.board_id,
        board_dir = board_dir_path,
        parent_platform = rctx.attr.parent_platform,
        output_dir = ".",
        app_name = rctx.attr.app_label.name,
        oot_dts_roots = resolved_oot_dts_roots,
        conf_fragments = resolved_conf_fragments,
        dtc_overlays = resolved_dtc_overlays,
    )

    result = python.execute(args)
    if result.return_code != 0:
        fail("Zephyr config generation failed: %s" % result.stderr)

    # The generator lists every file it read (plus probed candidates that don't exist) and every
    # directory whose listing matters, as realpaths. Only mutable locations get watched.
    deps = read_path_list(rctx, rctx.path("deps.txt"))
    dep_dirs = read_path_list(rctx, rctx.path("dep_dirs.txt")) or []
    if deps == None:
        # Generators without deps.txt only report some inputs, possibly not as realpaths.
        legacy = read_path_list(rctx, rctx.path("watched_inputs.txt"))
        if legacy == None:
            legacy = read_path_list(rctx, rctx.path("kconfig_list.txt")) or []
        deps = [realpath_of(rctx.path(line.strip())) for line in legacy]
    deps = deps + [realpath_of(p) for p in [kconfig_gen_values_py, kconfig_utils_py]]
    deps = deps + [realpath_of(rctx.path(f)) for f in resolved_conf_fragments + resolved_dtc_overlays]

    watch_pins(tracker, context["pin_files"])
    watch_deps(tracker, files = deps, dirs = dep_dirs)

    # We need to replace @zc_target with the actual repo name in BUILD.bazel
    # since the script doesn't know it.
    build_bazel = rctx.read("BUILD.bazel")
    build_bazel = build_bazel.replace("@zc_target", "@@" + rctx.name)
    build_bazel = build_bazel.replace("zc_target_platform", rctx.name + "_platform")
    rctx.file("BUILD.bazel", build_bazel)

gen_zephyr_config = repository_rule(
    implementation = _gen_zephyr_config_impl,
    attrs = {
        "app_label": attr.label(mandatory = True),
        "app_dir": attr.string(
            doc = "Canonical label of the BUILD file of the application's package, from discovery. " +
                  "Empty if the application was not discovered.",
        ),
        "board_id": attr.string(mandatory = True),
        "board_dir": attr.string(
            doc = "Canonical label of the BUILD file of the board's package, from discovery. " +
                  "Empty if the board was not discovered.",
        ),
        "parent_platform": attr.label(mandatory = True),
        "conf_fragments": attr.string_list(),
        "dtc_overlays": attr.string_list(),
        "extra_kconfig": attr.string(),
        "_context": attr.label(default = "@zephyr_state//:context.json"),
        "_kconfig_gen_values_py": attr.label(default = "//bazel/tools/kconfig:kconfig_gen_values.py"),
        "_pip_deps": attr.label_list(
            default = [
                "@zephyr_pip_deps//pcpp",
                "@zephyr_pip_deps//pyyaml",
            ],
        ),
    } | COMMON_PY_REPO_RULE_ATTRS,
)
