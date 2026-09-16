# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Repository rule for app-board specific Zephyr configuration. (forced update)"""

load("//bazel:naming.bzl", "normalize_app_label", "resolve_module_roots")
load("//bazel/private:kconfig_args.bzl", "get_kconfig_args")
load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")

def _gen_zephyr_config_impl(rctx):
    rctx.watch(rctx.attr.state_file)
    rctx.watch(rctx.path(rctx.attr._kconfig_schema))
    state_file = rctx.path(rctx.attr.state_file)
    state = json.decode(rctx.read(state_file))

    zephyr_root_path = str(rctx.path(Label(state["zephyr_root"])).dirname)

    # Robust normalization: strip repo and redundant target name
    norm_app = normalize_app_label(rctx.attr.app_label)

    app_dir_label = state["apps"].get(norm_app)
    if not app_dir_label:
        fail("App %s (normalized: %s) not found in discovery index. Discovered: %s" % (rctx.attr.app_label, norm_app, state["apps"].keys()))
    app_dir_path = str(rctx.path(Label(app_dir_label)).dirname)

    board_dir_label = state["board_index"].get(rctx.attr.board_id)
    if not board_dir_label:
        fail("Board %s not found in discovery index" % rctx.attr.board_id)
    board_dir_path = str(rctx.path(Label(board_dir_label)).dirname)

    resolved_oot_dts_roots = [str(rctx.path(Label(l)).dirname) for l in state.get("oot_dts_roots", [])]

    resolved_modules = resolve_module_roots(rctx, state)

    kconfig_gen_values_py = rctx.path(rctx.attr._kconfig_gen_values_py)

    kconfig_utils_py = rctx.path(Label("//bazel/tools/kconfig:kconfig_utils.py"))
    rctx.watch(kconfig_utils_py)

    python = get_python(rctx, extra_import_paths = [
        zephyr_root_path + "/scripts/kconfig",
        str(kconfig_gen_values_py.dirname),
    ])
    rctx.watch(kconfig_gen_values_py)
    rctx.watch(rctx.path(Label("//bazel/tools/kconfig:kconfig_utils.py")))

    # Watch application configuration files
    if app_dir_path:
        # Recursively watch the app directory to catch created configuration files.
        rctx.watch_tree(rctx.path(app_dir_path))

    if board_dir_path:
        rctx.watch_tree(rctx.path(board_dir_path))

    resolved_conf_fragments = []
    for fragment in rctx.attr.conf_fragments:
        if not fragment.startswith("/"):
            fragment_path = rctx.path(str(rctx.workspace_root) + "/" + fragment)
        else:
            fragment_path = rctx.path(fragment)
        rctx.watch(fragment_path)
        resolved_conf_fragments.append(str(fragment_path))

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
    )

    result = python.execute(args)
    if result.return_code != 0:
        fail("Zephyr config generation failed: %s" % result.stderr)

    repo_dir = str(rctx.path("."))
    repo_dir_real = str(rctx.path(".").realpath)
    kconfig_list_file = rctx.path("kconfig_list.txt")
    if kconfig_list_file.exists:
        for line in rctx.read(kconfig_list_file).splitlines():
            line = line.strip()
            if not line:
                continue
            if line == repo_dir or line.startswith(repo_dir + "/"):
                continue
            if line == repo_dir_real or line.startswith(repo_dir_real + "/"):
                continue
            kpath = rctx.path(line)
            if kpath.exists:
                rctx.watch(kpath)

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
        "board_id": attr.string(mandatory = True),
        "parent_platform": attr.label(mandatory = True),
        "state_file": attr.label(mandatory = True),
        "conf_fragments": attr.string_list(),
        "extra_kconfig": attr.string(),
        "_kconfig_gen_values_py": attr.label(default = "//bazel/tools/kconfig:kconfig_gen_values.py"),
        "_kconfig_schema": attr.label(default = "@zephyr_kconfig//:BUILD.bazel"),
        "_pip_deps": attr.label_list(
            default = [
                "@zephyr_pip_deps//pcpp",
                "@zephyr_pip_deps//pyyaml",
            ],
        ),
    } | COMMON_PY_REPO_RULE_ATTRS,
)
