# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Repository rule for the global Zephyr Kconfig schema."""

load("//bazel:naming.bzl", "resolve_module_roots")
load("//bazel/private:kconfig_args.bzl", "get_kconfig_args")
load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")

def _zephyr_kconfig_schema_impl(rctx):
    state_file = rctx.path(rctx.attr.state_file)
    state = json.decode(rctx.read(state_file))

    zephyr_root_path = str(rctx.path(Label(state["zephyr_root"])).dirname)

    resolved_board_dirs = []
    for b_label in state["board_index"].values():
        path_str = str(rctx.path(Label(b_label)).dirname)
        if path_str not in resolved_board_dirs:
            resolved_board_dirs.append(path_str)

    resolved_oot_dts_roots = []
    for r_label_str in state.get("oot_dts_roots", []):
        r_path = rctx.path(Label(r_label_str))
        if not r_path.exists:
            r_path = r_path.dirname
        resolved_oot_dts_roots.append(str(r_path))

    resolved_modules = resolve_module_roots(rctx, state)

    kconfig_gen_symbols_py = rctx.path(rctx.attr._kconfig_gen_symbols_py)

    python = get_python(rctx, extra_import_paths = [
        zephyr_root_path + "/scripts/kconfig",
        str(kconfig_gen_symbols_py.dirname),
    ])
    rctx.watch(kconfig_gen_symbols_py)

    kconfig_utils_py = rctx.path(Label("//bazel/tools/kconfig:kconfig_utils.py"))
    rctx.watch(kconfig_utils_py)
    rctx.watch(rctx.path(Label("//bazel/tools/kconfig:kconfig_utils.py")))

    for board_dir in resolved_board_dirs:
        rctx.watch_tree(rctx.path(board_dir))

    for kconfig in rctx.attr.kconfigs:
        rctx.watch(rctx.path(kconfig))

    args = get_kconfig_args(
        script = kconfig_gen_symbols_py,
        zephyr_root = zephyr_root_path,
        modules = resolved_modules,
        output = "BUILD.bazel",
        board_dirs = resolved_board_dirs,
        oot_dts_roots = resolved_oot_dts_roots,
    )

    result = python.execute(args)
    if result.return_code != 0:
        fail("Kconfig schema generation failed: %s" % result.stderr)
    elif result.stderr:
        print(result.stderr)

    local_modules = []
    for m_info in state["modules"].values():
        m_label = m_info["target"]
        local_modules.append(m_label)

    bzl_content = "LOCAL_MODULES = %r\n" % local_modules
    rctx.file("local_modules.bzl", bzl_content)


zephyr_kconfig_schema = repository_rule(
    implementation = _zephyr_kconfig_schema_impl,
    attrs = {
        "state_file": attr.label(mandatory = True),
        "kconfigs": attr.string_list(),
        "_kconfig_gen_symbols_py": attr.label(default = "//bazel/tools/kconfig:kconfig_gen_symbols.py"),
        "_pip_deps": attr.label_list(
            default = [
                "@zephyr_pip_deps//pyyaml",
            ],
        ),
    } | COMMON_PY_REPO_RULE_ATTRS,
)
