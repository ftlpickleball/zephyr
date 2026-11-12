# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import argparse
import contextlib
import inspect
import pickle
import shutil
import subprocess
import tempfile
import types
import json
import re
from pathlib import Path

import kconfig_utils
import discovery_utils

SUPPORTED_ARCHITECTURES = ["arc", "arm", "arm64", "mips", "posix", "riscv", "sparc", "xtensa", "x86", "rx"]

# Add Zephyr's kconfiglib to sys.path
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zephyr-base", required=True)
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--sysbuild-app-dir", default=None)
    parser.add_argument("--board", required=True)
    parser.add_argument("--board-dir", required=True)
    parser.add_argument("--parent-platform", required=True)
    parser.add_argument("--modules", nargs="+", default=[])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--oot-dts-roots", nargs="+", default=[])
    parser.add_argument("--kconfig-symbols-file", default=None)
    parser.add_argument("--kconfig-dts-file", default=None)
    parser.add_argument("--app-name", default="zephyr_app")
    parser.add_argument("--toolchain-variant", default=None)
    parser.add_argument("--conf-fragments", nargs="+", default=[])
    parser.add_argument("--forced-conf-fragments", nargs="+", default=[])
    parser.add_argument("--dtc-overlays", nargs="+", default=[])
    return parser.parse_args()

def setup_environment(args, zephyr_base, output_dir, board_dir, *, tracker=None):
    kconfig_utils.sanitize_host_env()
    os.environ["srctree"] = zephyr_base
    os.environ["ZEPHYR_BASE"] = zephyr_base
    os.environ["KCONFIG_BINARY_DIR"] = output_dir
    if getattr(args, "app_dir", None):
        os.environ["APPLICATION_SOURCE_DIR"] = os.path.abspath(str(args.app_dir))

    # Replicate Zephyr SDK compiler capabilities for Kconfig
    os.environ["TOOLCHAIN_HAS_PICOLIBC"] = "y"
    os.environ["TOOLCHAIN_HAS_NEWLIB"] = "y"

    board_name, board_qualifiers, board_revision = discovery_utils.parse_board_id(args.board)
    if not board_revision:
        board_revision = discovery_utils.get_default_board_revision(
            board_dir, board_name, tracker=tracker
        )
    os.environ["BOARD"] = board_name
    os.environ["BOARD_QUALIFIERS"] = board_qualifiers
    os.environ["BOARD_REVISION"] = board_revision
    os.environ["ARCH"] = "*"
    os.environ["HWM_SCHEME"] = "v2"
    os.environ["KCONFIG_FUNCTIONS"] = "kconfigfunctions"
    # Determine toolchain variant similar to Zephyr's FindHostTools.cmake
    toolchain_variant = args.toolchain_variant
    if toolchain_variant in (None, "", "gcc", "llvm"):
        board_dir_lower = board_dir.lower()
        if "native" in args.board or "boards/native" in board_dir_lower or "posix" in board_dir_lower:
            toolchain_variant = "host"
        else:
            toolchain_variant = "zephyr"

    os.environ["ZEPHYR_TOOLCHAIN_VARIANT"] = toolchain_variant
    os.environ["TOOLCHAIN_KCONFIG_DIR"] = os.path.join(zephyr_base, "cmake", "toolchain", toolchain_variant)
    os.environ["BOARD_DIR"] = os.path.abspath(board_dir)
    os.environ["KCONFIG_BOARD_DIR"] = os.path.join(output_dir, "boards")
    os.environ["ARCH_DIR"] = "arch"
    os.environ["SOC_DIR"] = "soc"
    os.environ["SOC_NAME"] = "none" # Will be overridden by defconfig

    kconfig_env_file = os.path.join(output_dir, "kconfig_module_dirs.env")
    os.makedirs(output_dir, exist_ok=True)
    with open(kconfig_env_file, "w") as f:
        if args.modules:
            for m in args.modules:
                if os.path.isdir(m):
                    module_name = kconfig_utils.module_name_from_dir(m).replace('-', '_').upper()
                    f.write(f"ZEPHYR_{module_name}_MODULE_DIR={os.path.abspath(m)}\n")
                    os.environ[f"ZEPHYR_{module_name}_MODULE_DIR"] = os.path.abspath(m)
    os.environ["KCONFIG_ENV_FILE"] = kconfig_env_file

def generate_kconfig_aggregations(zephyr_base, args, output_dir, board_dir, *, tracker):
    """Generates the soc/, arch/ and boards/ aggregation Kconfigs and Kconfig.modules."""
    # Generate aggregation Kconfig files
    soc_dirs = []
    soc_roots = [Path(zephyr_base)] + ([Path(m) for m in args.modules] if args.modules else [])
    for sroot in soc_roots:
        soc_path = sroot / "soc"
        if not soc_path.is_dir():
            tracker.add(str(soc_path))
            continue
        for root, dirs, files in kconfig_utils.filtered_walk(str(soc_path), tracker=tracker):
            if "soc.yml" in files:
                soc_dirs.append(root)
                tracker.add(os.path.join(root, "soc.yml"))

    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.defconfig"), soc_dirs, "SoC defconfigs", tracker=tracker)
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig"), soc_dirs, "SoC Kconfigs", tracker=tracker)
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.soc"), soc_dirs, "SoC Kconfigs", tracker=tracker)
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.sysbuild"), soc_dirs, "SoC sysbuild Kconfigs", tracker=tracker)

    shield_defconfig = os.path.join(output_dir, "Kconfig.shield.defconfig")
    os.makedirs(os.path.dirname(shield_defconfig), exist_ok=True)
    with open(shield_defconfig, "w") as f:
        f.write("# Empty shield defconfig\n")

    arch_dirs = []
    arch_root = os.path.join(zephyr_base, "arch")
    tracker.add_dir(arch_root)
    for d in sorted(os.listdir(arch_root)):
        if os.path.isdir(os.path.join(arch_root, d)):
            arch_dirs.append(os.path.join(arch_root, d))
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "arch", "Kconfig"), arch_dirs, "Arch Kconfigs", tracker=tracker)

    board_dirs = [board_dir]
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig.defconfig"), board_dirs, "Board defconfigs", tracker=tracker)
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig"), board_dirs, "Board Kconfigs", tracker=tracker)
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig.sysbuild"), board_dirs, "Board sysbuild Kconfigs", tracker=tracker)

    board_name = os.environ["BOARD"]
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", f"Kconfig.{board_name}"), board_dirs, "Board v2 Kconfigs", tracker=tracker)

    kconfig_modules = os.path.join(output_dir, "Kconfig.modules")
    kconfig_utils.generate_kconfig_modules(zephyr_base, args.modules, kconfig_modules, tracker=tracker)

    kconfig_sysbuild_modules = os.path.join(output_dir, "Kconfig.sysbuild.modules")
    kconfig_utils.generate_kconfig_sysbuild_modules(zephyr_base, args.modules, kconfig_sysbuild_modules, tracker=tracker)

def discover_overlays(app_dir, board_name, board_qualifiers, board_revision="", board_dir="", app_name="", *, tracker):
    overlays = []

    # 1. Board-level revision overlays in board_dir
    board_rev_overlays = discovery_utils.get_board_revision_overlays(
        board_dir, board_name, board_qualifiers, board_revision
    )
    tracker.add(*discovery_utils.get_board_revision_overlay_candidates(
        board_dir, board_name, board_qualifiers, board_revision
    ))
    for cand in board_rev_overlays:
        if cand not in overlays:
            overlays.append(cand)

    # 2. Board-level app-named overlay in board_dir (e.g., <board_dir>/mcuboot.overlay)
    board_app_overlay_found = False
    if board_dir and app_name:
        board_app_overlay = os.path.join(board_dir, f"{app_name}.overlay")
        tracker.add(board_app_overlay)
        if os.path.exists(board_app_overlay):
            board_app_overlay_found = True
            if board_app_overlay not in overlays:
                overlays.append(board_app_overlay)

    # 3. App-level board overlays in app_dir/boards/ (precedence: base -> qualified -> revision -> qualified revision)
    app_boards_dir = os.path.join(app_dir, "boards")
    app_board_overlays_found = False
    for cand_file in discovery_utils.get_app_board_override_candidates(
        board_name, board_qualifiers, board_revision, "overlay"
    ):
        cand_path = os.path.join(app_boards_dir, cand_file)
        tracker.add(cand_path)
        if os.path.exists(cand_path):
            app_board_overlays_found = True
            if cand_path not in overlays:
                overlays.append(cand_path)

    # 4. Default app overlay (fallback only when no board-specific overlay exists)
    if not board_app_overlay_found and not app_board_overlays_found:
        app_overlay = os.path.join(app_dir, "app.overlay")
        tracker.add(app_overlay)
        if os.path.exists(app_overlay) and app_overlay not in overlays:
            overlays.append(app_overlay)

    return overlays

def _make_include_recorder(cmd_preprocessor):
    """Returns a subclass of pcpp's CmdPreprocessor that records, in
    'probed_includes', every path it tries to open for an #include, whether
    or not it exists: creating a missing one would shadow the file used."""

    class IncludeRecorder(cmd_preprocessor):
        def __init__(self, argv):
            # CmdPreprocessor.__init__() runs the whole preprocessing.
            self.probed_includes = []
            super().__init__(argv)

        def on_file_open(self, is_system_include, includepath):
            self.probed_includes.append(includepath)
            return super().on_file_open(is_system_include, includepath)

    return IncludeRecorder

def preprocess_dts(args, zephyr_base, output_dir, board_dir, *, tracker, rel_base_dir=None):
    # Determine input DTS file
    board_name = os.environ["BOARD"]
    board_qualifiers = os.environ.get("BOARD_QUALIFIERS", "")
    board_revision = os.environ.get("BOARD_REVISION", "")

    board_base = args.board.split("@")[0]
    candidates = [
        os.path.join(board_dir, f"{board_base.replace('/', '_')}.dts"),
        os.path.join(board_dir, f"{args.board.replace('/', '_')}.dts"),
        os.path.join(board_dir, f"{board_name}.dts"),
    ]

    # In HWM v2, try to find a DTS file matching any SoC in board.yml
    for board_file in ["board.yml", "board.yaml"]:
        board_yml_path = os.path.join(board_dir, board_file)
        tracker.add(board_yml_path)
        if os.path.exists(board_yml_path):
            with open(board_yml_path, 'r') as f:
                content = f.read()
                matches = re.findall(r"-\s*name:\s*(\S+)", content)
                for soc in matches:
                    candidates.append(os.path.join(board_dir, f"{board_name}_{soc}.dts"))
            break

    dts_file = None
    for candidate in candidates:
        tracker.add(candidate)
        if os.path.exists(candidate):
            dts_file = candidate
            break

    if not dts_file:
        raise RuntimeError(f"Could not find DTS file for board {args.board} in {board_dir}. Tried: {candidates}")

    overlays = discover_overlays(args.app_dir, board_name, board_qualifiers, board_revision, board_dir, getattr(args, "app_name", ""), tracker=tracker)
    for extra_overlay in getattr(args, "dtc_overlays", []):
        tracker.add(extra_overlay)
        if os.path.exists(extra_overlay) and extra_overlay not in overlays:
            overlays.append(extra_overlay)

    dts_input_path = os.path.join(output_dir, "dts_input.c")
    os.makedirs(output_dir, exist_ok=True)
    with open(dts_input_path, "w") as f:
        f.write("/* Generated by zephyr-bazel - do not edit! */\n")
        f.write(f'#include "{os.path.relpath(dts_file, output_dir)}"\n')
        for overlay in overlays:
            f.write(f'#include "{os.path.relpath(overlay, output_dir)}"\n')

    merged_dts_path = os.path.join(output_dir, "zephyr.dts")

    # Preprocess DTS using pcpp
    from pcpp.pcmd import CmdPreprocessor

    raw_roots = (
        [Path(args.app_dir), Path(board_dir)]
        + [Path(r) for r in args.oot_dts_roots]
        + [Path(m) for m in args.modules]
        + [Path(zephyr_base)]
    )
    dts_roots = []
    for r in raw_roots:
        if r not in dts_roots:
            dts_roots.append(r)

    pcpp_cmd_args = [
        "pcpp",
        "-D__DTS__=1",
        os.path.abspath(dts_input_path),
        "-o",
        merged_dts_path,
    ]
    for dts_root in dts_roots:
        directories = [
            "include",
            "include/zephyr",
            "dts",
            "dts/common",
        ] + ["dts/" + a for a in SUPPORTED_ARCHITECTURES] + ["dts/vendor"]
        for directory in directories:
            path = dts_root / directory
            if path.exists():
                pcpp_cmd_args.append("-I" + os.path.abspath(path))
            else:
                # Creating it would add an include path, with headers that
                # could shadow the ones found now.
                tracker.add(str(path))

    preprocessor = CmdPreprocessor
    if isinstance(CmdPreprocessor, type):
        preprocessor = _make_include_recorder(CmdPreprocessor)
    cpp = preprocessor(pcpp_cmd_args)
    for item in getattr(cpp, "include_times", []):
        if item.included_abspath and os.path.exists(item.included_abspath):
            tracker.add(item.included_abspath)
    tracker.add(*getattr(cpp, "probed_includes", []))

    if os.path.exists(merged_dts_path):
        abs_out = os.path.abspath(output_dir)
        clean_base_dir = rel_base_dir or output_dir
        def _relativize_line(match):
            prefix, line_path, suffix = match.group(1), match.group(2), match.group(3)
            if os.path.isabs(line_path) or line_path.startswith(".."):
                abs_line = line_path if os.path.isabs(line_path) else os.path.abspath(os.path.join(abs_out, line_path))
                if (abs_line + os.sep).startswith(abs_out + os.sep):
                    rel_line = os.path.relpath(abs_line, abs_out)
                else:
                    rel_line = kconfig_utils.clean_output_path(abs_line, clean_base_dir)
                return f"{prefix}{rel_line}{suffix}"
            return match.group(0)

        with open(merged_dts_path, "r", encoding="utf-8") as f:
            dts_content = f.read()
        new_dts_content = re.sub(r'(?m)^(\s*#\s*(?:line\s+)?\d+\s+")([^"]+)(")', _relativize_line, dts_content)
        if new_dts_content != dts_content:
            with open(merged_dts_path, "w", encoding="utf-8") as f:
                f.write(new_dts_content)

    return merged_dts_path, dts_roots

def _dts_subprocess_env(zephyr_base):
    abs_base = os.path.abspath(zephyr_base)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [
            os.path.join(abs_base, "scripts", "dts"),
            os.path.join(abs_base, "scripts", "dts", "python-devicetree", "src"),
            env.get("PYTHONPATH", ""),
        ] if p
    )
    return env


def _is_mock(obj) -> bool:
    return hasattr(obj, "_mock_name") or hasattr(obj, "assert_called")


@contextlib.contextmanager
def _chdir(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _ensure_dts_sys_path(zephyr_base):
    abs_base = os.path.abspath(zephyr_base)
    for d in (
        os.path.join(abs_base, "scripts", "dts", "python-devicetree", "src"),
        os.path.join(abs_base, "scripts", "dts"),
    ):
        if d not in sys.path:
            sys.path.insert(0, d)


def _normalize_edt_obj(edt, output_dir):
    """Normalizes paths inside an in-memory EDT object for reproducible outputs."""
    if getattr(edt, "dts_path", None):
        edt.dts_path = os.path.basename(edt.dts_path)
    if hasattr(edt, "_dt") and getattr(edt._dt, "filename", None):
        edt._dt.filename = os.path.basename(edt._dt.filename)
    if hasattr(edt, "_dt") and getattr(edt._dt, "_base_dir", None):
        edt._dt._base_dir = "."

    abs_out = os.path.abspath(output_dir)
    repo_root_cache = {}
    dir_prefix_cache = {}
    path_cache = {}

    def _is_repo_root_cached(parent: Path) -> bool:
        res = repo_root_cache.get(parent)
        if res is None:
            res = kconfig_utils._is_repo_root(parent)
            repo_root_cache[parent] = res
        return res

    def _clean_dir_prefix(dir_path: str) -> str:
        res = dir_prefix_cache.get(dir_path)
        if res is not None:
            return res
        probe = os.path.join(dir_path, "__probe__")
        rel = os.path.relpath(probe, abs_out)
        if not rel.startswith(".." + os.sep + ".."):
            res = os.path.dirname(rel)
        else:
            res = ""
            for parent in Path(probe).parents:
                if os.path.commonpath([abs_out, str(parent)]) == str(parent):
                    break
                if _is_repo_root_cached(parent):
                    res = os.path.relpath(dir_path, parent)
                    if res == ".":
                        res = ""
                    break
        dir_prefix_cache[dir_path] = res
        return res

    def _clean(path_str: str) -> str:
        res = path_cache.get(path_str)
        if res is not None:
            return res
        abs_path = (
            os.path.abspath(os.path.join(abs_out, path_str))
            if not os.path.isabs(path_str)
            else os.path.abspath(path_str)
        )
        res = path_cache.get(abs_path)
        if res is not None:
            path_cache[path_str] = res
            return res
        dir_path, base = os.path.split(abs_path)
        if not base:
            res = kconfig_utils.clean_output_path(abs_path, abs_out)
        else:
            prefix = _clean_dir_prefix(dir_path)
            res = os.path.join(prefix, base) if prefix else base
        path_cache[path_str] = res
        path_cache[abs_path] = res
        return res

    edt.bindings_dirs = [
        kconfig_utils.clean_output_path(d, abs_out) for d in edt.bindings_dirs
    ]
    edt._binding_paths = [_clean(p) for p in edt._binding_paths]
    for k, v in list(edt._binding_fname2path.items()):
        edt._binding_fname2path[k] = _clean(v)
    seen = set()

    def _clean_binding(b):
        while b is not None and id(b) not in seen:
            seen.add(id(b))
            if b.path:
                b.path = _clean(b.path)
            if getattr(b, "_included_binding_paths", None):
                b._included_binding_paths = {
                    _clean(p) for p in b._included_binding_paths
                }
            b = getattr(b, "child_binding", None)

    for b in edt._compat2binding.values():
        _clean_binding(b)
    for node in edt.nodes:
        _clean_binding(getattr(node, "_binding", None))


def _record_edt_bindings(edt, base_dir, tracker):
    """Records the binding YAML files actually matched by `edt`."""
    seen = set()

    def _visit(b):
        while b is not None and id(b) not in seen:
            seen.add(id(b))
            b_path = getattr(b, "path", None)
            if b_path:
                tracker.add(
                    b_path if os.path.isabs(b_path) else os.path.join(base_dir, b_path)
                )
            for inc in getattr(b, "_included_binding_paths", None) or ():
                tracker.add(inc if os.path.isabs(inc) else os.path.join(base_dir, inc))
            b = getattr(b, "child_binding", None)

    for b in getattr(edt, "_compat2binding", {}).values():
        _visit(b)
    for node in getattr(edt, "nodes", ()):
        _visit(getattr(node, "_binding", None))


def _normalize_edt_pickle(edt_pickle_path, zephyr_base, output_dir):
    if not os.path.exists(edt_pickle_path):
        return
    _ensure_dts_sys_path(zephyr_base)
    with open(edt_pickle_path, "rb") as f:
        edt = pickle.load(f)
    _normalize_edt_obj(edt, output_dir)
    with open(edt_pickle_path, "wb") as f:
        pickle.dump(edt, f, protocol=4)


def generate_edt_pickle(zephyr_base, output_dir, dts_roots, merged_dts_path, *, tracker):
    """Runs edtlib (or gen_edt.py / gen_defines.py) to write edt.pickle."""
    output_edt_pickle_path = os.path.join(output_dir, "edt.pickle")
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    zephyr_real_prefix = os.path.realpath(zephyr_base) + os.sep
    bindings_dirs = []
    resolved_bindings_dirs = []
    seen_resolved = set()
    for dts_root in dts_roots:
        for b in ("zephyr/dts/bindings", "dts/bindings"):
            bdir = dts_root / b
            if bdir.exists():
                resolved = bdir.resolve()
                if resolved not in seen_resolved:
                    seen_resolved.add(resolved)
                    resolved_bindings_dirs.append(resolved)
                    bindings_dirs.append(os.path.relpath(bdir, output_dir))
                if not (str(resolved) + os.sep).startswith(zephyr_real_prefix):
                    tracker.add_tree(resolved, kconfig_utils.BINDING_SUFFIXES)
                break
            else:
                tracker.add(str(bdir))

    gen_edt_py = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "gen_edt.py"))
    gen_defines_py = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py"))

    tracker.add(gen_edt_py, *kconfig_utils.dts_python_sources(zephyr_base))

    rel_edt_pickle = os.path.relpath(output_edt_pickle_path, output_dir)
    rel_merged_dts = os.path.relpath(merged_dts_path, output_dir)
    rel_dts_debug = os.path.relpath(f"{merged_dts_path}.debug", output_dir)

    if os.path.exists(gen_edt_py):
        vendor_prefix_args = []
        vendor_prefix_files = []
        for bdir in bindings_dirs:
            vp = os.path.join(bdir, "vendor-prefixes.txt")
            vp_abs = os.path.join(output_dir, vp)
            tracker.add(vp_abs)
            if os.path.exists(vp_abs):
                vendor_prefix_args.extend(["--vendor-prefixes", vp])
                vendor_prefix_files.append(vp)

        if not _is_mock(subprocess.run) and os.path.isfile(merged_dts_path):
            _ensure_dts_sys_path(zephyr_base)
            import edtlib_logger
            from devicetree import edtlib

            edtlib_logger.setup_edtlib_logging()
            with _chdir(output_dir):
                vendor_prefixes = {}
                for vp in vendor_prefix_files:
                    vendor_prefixes.update(edtlib.load_vendor_prefixes_txt(vp))
                try:
                    edt = edtlib.EDT(
                        rel_merged_dts,
                        bindings_dirs,
                        workspace_dir=".",
                        warn_reg_unit_address_mismatch=True,
                        default_prop_types=True,
                        infer_binding_for_paths=["/zephyr,user", "/cpus"],
                        werror=False,
                        vendor_prefixes=vendor_prefixes,
                        warn_bus_mismatch=False,
                    )
                except edtlib.EDTError as e:
                    sys.exit(f"devicetree error: {e}")
                with open(rel_dts_debug, "w", encoding="utf-8") as f:
                    print(edt.dts_source, file=f)
            _record_edt_bindings(edt, output_dir, tracker)
            _normalize_edt_obj(edt, output_dir)
            with open(output_edt_pickle_path, "wb") as f:
                pickle.dump(edt, f, protocol=4)
            os.environ["EDT_PICKLE"] = output_edt_pickle_path
            return edt

        # gen_edt.py runs in a subprocess and cannot report which bindings it matched, so every
        # binding file in the bindings directories is an input.
        for resolved in resolved_bindings_dirs:
            tracker.add_tree(resolved, kconfig_utils.BINDING_SUFFIXES)

        gen_edt_args = [
            sys.executable,
            "-B",
            "-s",
            gen_edt_py,
            "--workspace-dir",
            ".",
            "--edt-pickle-out",
            rel_edt_pickle,
            "--dts",
            rel_merged_dts,
            "--bindings-dirs",
        ]
        gen_edt_args.extend(bindings_dirs)
        gen_edt_args.extend(vendor_prefix_args)
        gen_edt_args.extend([
            "--dts-out",
            rel_dts_debug,
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ])
        subprocess.run(
            gen_edt_args,
            env=_dts_subprocess_env(zephyr_base),
            cwd=output_dir,
            check=True,
        )
    else:
        tracker.add(gen_defines_py)
        cmd = [
            sys.executable,
            "-B",
            "-s",
            gen_defines_py,
            "--dts",
            rel_merged_dts,
            "--bindings-dirs",
        ]
        cmd.extend(bindings_dirs)
        cmd.extend([
            "--header-out",
            os.path.relpath(output_header, output_dir),
            "--dts-out",
            rel_dts_debug,
            "--edt-pickle-out",
            rel_edt_pickle,
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ])
        subprocess.run(
            cmd,
            env=_dts_subprocess_env(zephyr_base),
            cwd=output_dir,
            check=True,
        )

    _normalize_edt_pickle(output_edt_pickle_path, zephyr_base, output_dir)
    os.environ["EDT_PICKLE"] = output_edt_pickle_path
    return None


def generate_dts_headers(
    zephyr_base, output_dir, edt_pickle_path, *, tracker, edt=None
):
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    if os.path.exists(output_header):
        return
    gen_defines_py = os.path.abspath(
        os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py")
    )
    tracker.add(gen_defines_py, *kconfig_utils.dts_python_sources(zephyr_base))
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    rel_edt_pickle = os.path.relpath(edt_pickle_path, output_dir)
    rel_header = os.path.relpath(output_header, output_dir)

    if (
        not _is_mock(subprocess.run)
        and os.path.isfile(gen_defines_py)
        and (edt is not None or os.path.isfile(edt_pickle_path))
    ):
        _ensure_dts_sys_path(zephyr_base)
        import gen_defines

        prev_argv = sys.argv
        prev_pickle = gen_defines.pickle
        edt_pickle_arg = (
            rel_edt_pickle
            if os.path.isfile(edt_pickle_path)
            else os.devnull
        )
        try:
            sys.argv = [
                gen_defines_py,
                "--edt-pickle",
                edt_pickle_arg,
                "--header-out",
                rel_header,
            ]
            if edt is not None:
                gen_defines.pickle = types.SimpleNamespace(load=lambda _f: edt)
            with _chdir(output_dir):
                gen_defines.main()
        finally:
            gen_defines.pickle = prev_pickle
            sys.argv = prev_argv
        return

    cmd = [
        sys.executable,
        "-B",
        "-s",
        gen_defines_py,
        "--edt-pickle",
        rel_edt_pickle,
        "--header-out",
        rel_header,
    ]

    subprocess.run(
        cmd, env=_dts_subprocess_env(zephyr_base), cwd=output_dir, check=True
    )

def get_conf_files(args, board_dir, *, tracker):
    board_name = os.environ["BOARD"]
    board_qualifiers = os.environ.get("BOARD_QUALIFIERS", "").lstrip("/")
    board_revision = os.environ.get("BOARD_REVISION", "")

    conf_files = []

    # 1 & 2. Base and qualified board defconfigs (HWM v2) using shared candidate logic
    for cand in discovery_utils.get_app_board_override_candidates(board_name, board_qualifiers, "", "defconfig", sep="_"):
        cand_path = os.path.join(board_dir, cand)
        tracker.add(cand_path)
        if os.path.exists(cand_path) and cand_path not in conf_files:
            conf_files.append(cand_path)

    # 3. Revision defconfig in board directory
    rev_defconfigs = discovery_utils.get_board_revision_defconfigs(
        board_dir, board_name, board_qualifiers, board_revision
    )
    tracker.add(*discovery_utils.get_board_revision_defconfig_candidates(
        board_dir, board_name, board_qualifiers, board_revision
    ))
    for rev_defconfig in rev_defconfigs:
        if rev_defconfig not in conf_files:
            conf_files.append(rev_defconfig)

    # 4. Base application prj.conf and Kconfig
    prj_conf = os.path.join(args.app_dir, "prj.conf")
    tracker.add(prj_conf, os.path.join(args.app_dir, "Kconfig"))
    if os.path.exists(prj_conf):
        conf_files.append(prj_conf)

    # 4b. Board-level app-named conf in board_dir (e.g., <board_dir>/mcuboot.conf)
    if board_dir and getattr(args, "app_name", ""):
        board_app_conf = os.path.join(board_dir, f"{args.app_name}.conf")
        tracker.add(board_app_conf)
        if os.path.exists(board_app_conf) and board_app_conf not in conf_files:
            conf_files.append(board_app_conf)

    # 5. Application board conf candidates (precedence: base -> qualified -> revision -> qualified revision)
    app_boards_dir = os.path.join(args.app_dir, "boards")
    for conf_file in discovery_utils.get_app_board_override_candidates(
        board_name, board_qualifiers, board_revision, "conf"
    ):
        conf_path = os.path.join(app_boards_dir, conf_file)
        tracker.add(conf_path)
        if os.path.exists(conf_path) and conf_path not in conf_files:
            conf_files.append(conf_path)

    return conf_files


def translate_sysbuild_kconfig_to_domain(sb_kconf, image_type):
    """Translates resolved SB_CONFIG_* symbols to domain CONFIG_* lines.

    Mirrors Zephyr's share/sysbuild/image_configurations/*_image_default.cmake.
    """
    lines = []

    def sb_bool(name):
        sym = sb_kconf.syms.get(name)
        return sym is not None and sym.str_value == "y"

    def sb_str(name):
        sym = sb_kconf.syms.get(name)
        return sym.str_value if sym is not None else ""

    def sb_has_user_value(name):
        sym = sb_kconf.syms.get(name)
        return sym is not None and sym.user_value is not None

    def set_bool(config_name, val):
        if val:
            lines.append(f"CONFIG_{config_name}=y")
        else:
            lines.append(f"# CONFIG_{config_name} is not set")

    def set_str(config_name, val):
        lines.append(f'CONFIG_{config_name}="{val}"')

    def set_int(config_name, val):
        lines.append(f"CONFIG_{config_name}={val}")

    # 1. ALL_image_default.cmake
    if sb_bool("COMPILER_WARNINGS_AS_ERRORS"):
        set_bool("COMPILER_WARNINGS_AS_ERRORS", True)

    # 2. MAIN_image_default.cmake
    if image_type == "MAIN":
        if sb_bool("BOOTLOADER_MCUBOOT"):
            set_bool("BOOTLOADER_MCUBOOT", True)
            sig_key = sb_str("BOOT_SIGNATURE_KEY_FILE")
            if sig_key:
                set_str("MCUBOOT_SIGNATURE_KEY_FILE", sig_key.split(",")[0])
            enc_key = sb_str("BOOT_ENCRYPTION_KEY_FILE")
            if enc_key:
                set_str("MCUBOOT_ENCRYPTION_KEY_FILE", enc_key)

            if sb_str("SIGNATURE_TYPE") == "NONE" or sb_bool("BOOT_SIGNATURE_TYPE_NONE"):
                set_bool("MCUBOOT_GENERATE_UNSIGNED_IMAGE", True)
            else:
                set_bool("MCUBOOT_GENERATE_UNSIGNED_IMAGE", False)

            if sb_bool("MCUBOOT_MODE_SINGLE_APP"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_SINGLE_APP", True)
            elif sb_bool("MCUBOOT_MODE_SWAP_USING_OFFSET"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_SWAP_USING_OFFSET", True)
            elif sb_bool("MCUBOOT_MODE_SWAP_USING_MOVE") or sb_bool("MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_SWAP_USING_MOVE", True)
            elif sb_bool("MCUBOOT_MODE_SWAP_SCRATCH"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_SWAP_SCRATCH", True)
            elif sb_bool("MCUBOOT_MODE_OVERWRITE_ONLY"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_OVERWRITE_ONLY", True)
            elif sb_bool("MCUBOOT_MODE_DIRECT_XIP"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_DIRECT_XIP", True)
            elif sb_bool("MCUBOOT_MODE_DIRECT_XIP_WITH_REVERT"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_DIRECT_XIP_WITH_REVERT", True)
            elif sb_bool("MCUBOOT_MODE_RAM_LOAD"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_RAM_LOAD", True)
                if "MCUBOOT_RAMLOAD_ALLOW_XIP" in sb_kconf.syms and not sb_bool("MCUBOOT_RAMLOAD_ALLOW_XIP"):
                    set_bool("XIP", False)
                    set_int("FLASH_SIZE", 0)
            elif sb_bool("MCUBOOT_MODE_RAM_LOAD_WITH_REVERT"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_RAM_LOAD_WITH_REVERT", True)
                if "MCUBOOT_RAMLOAD_ALLOW_XIP" in sb_kconf.syms and not sb_bool("MCUBOOT_RAMLOAD_ALLOW_XIP"):
                    set_bool("XIP", False)
                    set_int("FLASH_SIZE", 0)
            elif sb_bool("MCUBOOT_MODE_SINGLE_APP_RAM_LOAD"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_SINGLE_APP_RAM_LOAD", True)
            elif sb_bool("MCUBOOT_MODE_FIRMWARE_UPDATER"):
                set_bool("MCUBOOT_BOOTLOADER_MODE_FIRMWARE_UPDATER", True)
                if sb_bool("MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE"):
                    set_bool("REBOOT", True)
                    set_bool("RETAINED_MEM", True)
                    set_bool("RETENTION", True)
                    set_bool("RETENTION_BOOT_MODE", True)

            if sb_bool("BOOT_ENCRYPTION"):
                if sb_bool("BOOT_ENCRYPTION_ALG_AES_128"):
                    set_bool("MCUBOOT_ENCRYPTION_ALG_AES_128", True)
                elif sb_bool("BOOT_ENCRYPTION_ALG_AES_256"):
                    set_bool("MCUBOOT_ENCRYPTION_ALG_AES_256", True)
        elif sb_has_user_value("BOOTLOADER_MCUBOOT") or sb_has_user_value("BOOTLOADER_NONE"):
            set_bool("BOOTLOADER_MCUBOOT", False)

    # 3. BOOTLOADER_image_default.cmake
    elif image_type == "BOOTLOADER":
        set_bool("SINGLE_APPLICATION_SLOT", sb_bool("MCUBOOT_MODE_SINGLE_APP"))
        set_bool("BOOT_SWAP_USING_OFFSET", sb_bool("MCUBOOT_MODE_SWAP_USING_OFFSET"))
        set_bool("BOOT_SWAP_USING_SCRATCH", sb_bool("MCUBOOT_MODE_SWAP_SCRATCH"))
        set_bool("BOOT_UPGRADE_ONLY", sb_bool("MCUBOOT_MODE_OVERWRITE_ONLY"))
        set_bool(
            "BOOT_SWAP_USING_MOVE",
            sb_bool("MCUBOOT_MODE_SWAP_USING_MOVE") or sb_bool("MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH"),
        )
        set_bool(
            "BOOT_DIRECT_XIP",
            sb_bool("MCUBOOT_MODE_DIRECT_XIP") or sb_bool("MCUBOOT_MODE_DIRECT_XIP_WITH_REVERT"),
        )
        set_bool(
            "BOOT_RAM_LOAD",
            sb_bool("MCUBOOT_MODE_RAM_LOAD") or sb_bool("MCUBOOT_MODE_RAM_LOAD_WITH_REVERT"),
        )
        set_bool("BOOT_FIRMWARE_LOADER", sb_bool("MCUBOOT_MODE_FIRMWARE_UPDATER"))
        set_bool("SINGLE_APPLICATION_SLOT_RAM_LOAD", sb_bool("MCUBOOT_MODE_SINGLE_APP_RAM_LOAD"))

        if sb_bool("MCUBOOT_MODE_FIRMWARE_UPDATER") and sb_bool("MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE"):
            set_bool("RETAINED_MEM", True)
            set_bool("RETENTION", True)
            set_bool("RETENTION_BOOT_MODE", True)
            set_bool("BOOT_FIRMWARE_LOADER_BOOT_MODE", True)

        set_bool("BOOT_DIRECT_XIP_REVERT", sb_bool("MCUBOOT_MODE_DIRECT_XIP_WITH_REVERT"))
        set_bool("BOOT_RAM_LOAD_REVERT", sb_bool("MCUBOOT_MODE_RAM_LOAD_WITH_REVERT"))

        sig_key = sb_str("BOOT_SIGNATURE_KEY_FILE")
        if sig_key or sb_has_user_value("BOOT_SIGNATURE_KEY_FILE"):
            if sb_bool("BOOT_SIGNATURE_TYPE_NONE"):
                set_str("BOOT_SIGNATURE_KEY_FILE", "")
            else:
                set_str("BOOT_SIGNATURE_KEY_FILE", sig_key)

        set_bool("BOOT_SIGNATURE_TYPE_NONE", sb_bool("BOOT_SIGNATURE_TYPE_NONE"))
        set_bool("BOOT_SIGNATURE_TYPE_RSA", sb_bool("BOOT_SIGNATURE_TYPE_RSA"))
        set_bool("BOOT_SIGNATURE_TYPE_ECDSA_P256", sb_bool("BOOT_SIGNATURE_TYPE_ECDSA_P256"))
        set_bool("BOOT_SIGNATURE_TYPE_ED25519", sb_bool("BOOT_SIGNATURE_TYPE_ED25519"))

        if sb_bool("BOOT_ENCRYPTION"):
            set_bool("BOOT_ENCRYPT_IMAGE", True)
            enc_key = sb_str("BOOT_ENCRYPTION_KEY_FILE")
            if enc_key or sb_has_user_value("BOOT_ENCRYPTION_KEY_FILE"):
                set_str("BOOT_ENCRYPTION_KEY_FILE", enc_key)
            if sb_bool("BOOT_ENCRYPTION_ALG_AES_128"):
                set_bool("BOOT_ENCRYPT_ALG_AES_128", True)
            elif sb_bool("BOOT_ENCRYPTION_ALG_AES_256"):
                set_bool("BOOT_ENCRYPT_ALG_AES_256", True)

    # 4. FIRMWARE_LOADER_image_default.cmake
    elif image_type == "FIRMWARE_LOADER":
        set_bool("BOOTLOADER_MCUBOOT", sb_bool("BOOTLOADER_MCUBOOT"))
        sig_key = sb_str("BOOT_SIGNATURE_KEY_FILE")
        if sig_key:
            set_str("MCUBOOT_SIGNATURE_KEY_FILE", sig_key.split(",")[0])
        enc_key = sb_str("BOOT_ENCRYPTION_KEY_FILE")
        if enc_key:
            set_str("MCUBOOT_ENCRYPTION_KEY_FILE", enc_key)
        if sb_str("SIGNATURE_TYPE") == "NONE" or sb_bool("BOOT_SIGNATURE_TYPE_NONE"):
            set_bool("MCUBOOT_GENERATE_UNSIGNED_IMAGE", True)
        else:
            set_bool("MCUBOOT_GENERATE_UNSIGNED_IMAGE", False)
        set_bool("MCUBOOT_BOOTLOADER_MODE_FIRMWARE_UPDATER", True)

    return lines


def generate_sysbuild_forced_config(zephyr_base, args, output_dir, board_dir, *, tracker):
    """Evaluates share/sysbuild/Kconfig and writes .config.sysbuild if applicable."""
    sysbuild_kconfig = os.path.join(zephyr_base, "share", "sysbuild", "Kconfig")
    tracker.add(sysbuild_kconfig)
    if not os.path.exists(sysbuild_kconfig):
        return None

    raw_app_name = getattr(args, "app_name", "")
    app_name = raw_app_name if isinstance(raw_app_name, str) else ""
    abs_app_dir = os.path.abspath(args.app_dir).replace("\\", "/")
    abs_zephyr_base = os.path.abspath(zephyr_base).replace("\\", "/").rstrip("/")
    is_in_tree_test_or_sample = abs_app_dir.startswith(
        (abs_zephyr_base + "/tests/", abs_zephyr_base + "/samples/")
    )
    if not is_in_tree_test_or_sample and (
        app_name == "mcuboot"
        or os.path.basename(abs_app_dir) == "mcuboot"
        or abs_app_dir.endswith("/mcuboot/boot/zephyr")
    ):
        image_type = "BOOTLOADER"
    elif not is_in_tree_test_or_sample and app_name == "firmware_loader":
        image_type = "FIRMWARE_LOADER"
    else:
        image_type = "MAIN"

    raw_sb_app_dir = getattr(args, "sysbuild_app_dir", None)
    sb_app_dir = (
        raw_sb_app_dir
        if isinstance(raw_sb_app_dir, str) and raw_sb_app_dir
        else args.app_dir
    )
    app_kconfig_sysbuild = os.path.join(sb_app_dir, "Kconfig.sysbuild")
    app_sysbuild_conf = os.path.join(sb_app_dir, "sysbuild.conf")
    board_kconfig_sysbuild = os.path.join(board_dir, "Kconfig.sysbuild")
    tracker.add(app_kconfig_sysbuild, app_sysbuild_conf, board_kconfig_sysbuild)

    board_name = os.environ.get("BOARD", "")
    board_qualifiers = os.environ.get("BOARD_QUALIFIERS", "").lstrip("/")
    board_revision = os.environ.get("BOARD_REVISION", "")
    sysbuild_yml_candidates = [os.path.join(sb_app_dir, "sysbuild.yml")]
    if board_name:
        for cand in discovery_utils.get_app_board_override_candidates(
            board_name, board_qualifiers, board_revision, "sysbuild.yml"
        ):
            sysbuild_yml_candidates.append(os.path.join(sb_app_dir, "boards", cand))
    for yml_cand in sysbuild_yml_candidates:
        tracker.add(yml_cand)

    has_sysbuild_yml = False
    uses_mcuboot = image_type == "BOOTLOADER"
    for yml_cand in sysbuild_yml_candidates:
        if os.path.exists(yml_cand):
            has_sysbuild_yml = True
            try:
                import yaml
                with open(yml_cand, "r", encoding="utf-8") as yf:
                    ydata = yaml.safe_load(yf)
                if isinstance(ydata, dict) and isinstance(ydata.get("helpers"), dict):
                    for h_name, h_cfg in ydata["helpers"].items():
                        h_target = h_cfg.get("target", "") if isinstance(h_cfg, dict) else ""
                        if "mcuboot" in str(h_name).lower() or "mcuboot" in str(h_target).lower():
                            uses_mcuboot = True
            except Exception:
                pass

    raw_forced_fragments = getattr(args, "forced_conf_fragments", None)
    has_forced_fragments = (
        bool(raw_forced_fragments)
        if isinstance(raw_forced_fragments, (list, tuple))
        else False
    )

    if image_type in ("BOOTLOADER", "FIRMWARE_LOADER"):
        sysbuild_active = (
            os.path.exists(board_kconfig_sysbuild)
            or has_sysbuild_yml
            or os.path.exists(app_kconfig_sysbuild)
            or os.path.exists(app_sysbuild_conf)
            or has_forced_fragments
        )
    else:
        sysbuild_active = (
            has_sysbuild_yml
            or os.path.exists(app_kconfig_sysbuild)
            or os.path.exists(app_sysbuild_conf)
            or has_forced_fragments
        )

    if not sysbuild_active:
        return None

    import kconfiglib

    sb_root = app_kconfig_sysbuild if os.path.exists(app_kconfig_sysbuild) else sysbuild_kconfig
    prev_config_prefix = os.environ.get("CONFIG_")
    prev_app_src_dir = os.environ.get("APPLICATION_SOURCE_DIR")
    os.environ["CONFIG_"] = "SB_CONFIG_"
    os.environ["APPLICATION_SOURCE_DIR"] = os.path.abspath(sb_app_dir)
    try:
        with kconfig_utils.record_kconfig_sources(kconfiglib, tracker):
            sb_kconf = kconfiglib.Kconfig(sb_root, warn_to_stderr=False)
        sb_srctree = getattr(sb_kconf, "srctree", None)
        base_srctree = (
            sb_srctree
            if isinstance(sb_srctree, str) and sb_srctree
            else zephyr_base
        )
        for kfile in getattr(sb_kconf, "kconfig_filenames", []):
            tracker.add(
                os.path.realpath(os.path.join(base_srctree, kfile))
            )
        if uses_mcuboot and "BOOTLOADER_MCUBOOT" in sb_kconf.syms:
            sb_kconf.syms["BOOTLOADER_MCUBOOT"].set_value("y")
        if os.path.exists(app_sysbuild_conf):
            sb_kconf.load_config(app_sysbuild_conf, replace=False)
    finally:
        if prev_config_prefix is None:
            os.environ.pop("CONFIG_", None)
        else:
            os.environ["CONFIG_"] = prev_config_prefix
        if prev_app_src_dir is None:
            os.environ.pop("APPLICATION_SOURCE_DIR", None)
        else:
            os.environ["APPLICATION_SOURCE_DIR"] = prev_app_src_dir

    lines = translate_sysbuild_kconfig_to_domain(sb_kconf, image_type)
    if not lines:
        return None

    forced_conf_path = os.path.join(output_dir, ".config.sysbuild")
    with open(forced_conf_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return forced_conf_path

def generate_config_c(kconf, output_dir, args):
    os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)
    with open(os.path.join(output_dir, "zephyr", "config.c"), "w") as f:
        f.write("/* AUTO-GENERATED by kconfig_gen_values.py, do not edit! */\n\n")
        f.write("#include <zephyr/toolchain.h>\n\n")
        f.write("GEN_ABS_SYM_BEGIN (_ConfigAbsSyms)\n")

        # Call scripts/build/generate_configs_dot_c.py methodology
        for sym in kconf.unique_defined_syms:
            if not sym.nodes:
                continue

            val = None
            # Import here because it's not available at the top level due to path setup.
            import kconfiglib
            if sym.type in [kconfiglib.BOOL, kconfiglib.TRISTATE]:
                if sym.str_value == "y":
                    val = "1"
            elif sym.type == kconfiglib.INT:
                if sym.str_value:
                    val = sym.str_value
            elif sym.type == kconfiglib.HEX:
                if sym.str_value:
                    val = "0x" + sym.str_value.replace("0x", "")
            elif sym.type == kconfiglib.STRING:
                if sym.str_value:
                    val = "1"

            if val is not None:
                f.write(f"GEN_ABSOLUTE_SYM_KCONFIG(CONFIG_{sym.name}, {val});\n")

        f.write("GEN_ABS_SYM_END\n")

def _is_enabled(kconf, name):
    sym = kconf.syms.get(name)
    return bool(sym and sym.str_value == "y")


def _get_int(kconf, name):
    sym = kconf.syms.get(name)
    if not sym or not sym.str_value:
        return 0
    try:
        return int(sym.str_value, 0)
    except ValueError:
        return 0


def _sum_kconfig_prefix(kconf, prefix):
    total = 0
    for sym in kconf.unique_defined_syms:
        if not sym.nodes or not sym.name.startswith(prefix):
            continue
        if sym.str_value:
            try:
                total += int(sym.str_value, 0)
            except ValueError:
                pass
    return total


def _get_zvfs_eventfd_size(kconf):
    if not (_is_enabled(kconf, "ZVFS") and _is_enabled(kconf, "ZVFS_EVENTFD")):
        return None
    eventfd_max = _get_int(kconf, "ZVFS_EVENTFD_MAX")
    if _is_enabled(kconf, "ZVFS_EVENTFD_IGNORE_MIN"):
        return eventfd_max
    eventfd_add_size_sum = _sum_kconfig_prefix(kconf, "ZVFS_EVENTFD_ADD_SIZE_")
    return max(eventfd_max, eventfd_add_size_sum)


def _get_zvfs_open_size(kconf):
    if not _is_enabled(kconf, "ZVFS"):
        return None
    open_max = _get_int(kconf, "ZVFS_OPEN_MAX")
    if _is_enabled(kconf, "ZVFS_OPEN_IGNORE_MIN"):
        return open_max
    add_size_sum = _sum_kconfig_prefix(kconf, "ZVFS_OPEN_ADD_SIZE_")
    return max(open_max, add_size_sum)


def generate_bazel_build(args, kconf, output_dir, kconfiglib):
    resolved_arch = "arm"
    for a in SUPPORTED_ARCHITECTURES:
        sym_name = "ARCH_POSIX" if a == "posix" else a.upper()
        sym = kconf.syms.get(sym_name)
        if sym and sym.str_value == "y":
            resolved_arch = a
            break

    if resolved_arch == "arm":
        # Fallback check for ARC if standard symbol is missing
        sym = kconf.syms.get("DT_HAS_SNPS_ARCEM_ENABLED")
        if sym and sym.str_value == "y":
            resolved_arch = "arc"

    arch_macro = "__arm__"
    if resolved_arch == "arm64":
        arch_macro = "__aarch64__"
    elif resolved_arch == "x86":
        arch_macro = "__i386__"
    elif resolved_arch == "riscv":
        arch_macro = "__riscv"

    soc_name = kconf.syms.get("SOC").str_value
    if not soc_name:
        # Try SOC_SERIES or other fallbacks if SOC is empty
        soc_name = kconf.syms.get("SOC_SERIES").str_value
    if not soc_name:
        soc_name = os.environ.get("BOARD", "unknown")

    target_name = kconfig_utils.sanitize_name_for_target(soc_name)
    print(f"DEBUG: soc_name={soc_name}, target_name={target_name}")

    with open(os.path.join(output_dir, "BUILD.bazel"), "w") as f:
        f.write('load("@rules_cc//cc:defs.bzl", "cc_library")\n')
        f.write('load("@zephyr//bazel:cc_library.bzl", "zephyr_cc_library")\n')
        f.write('load("@bazel_skylib//rules/directory:directory.bzl", "directory")\n')
        f.write('package(default_visibility = ["//visibility:public"])\n\n')
        f.write('exports_files(["zephyr/autoconf.h", "zephyr/devicetree_generated.h", ".config", "edt.pickle"])\n\n')

        f.write('cc_library(\n')
        f.write('    name = "devicetree_generated",\n')
        f.write('    hdrs = ["zephyr/devicetree_generated.h"],\n')
        f.write('    includes = ["zephyr", "."],\n')
        f.write(')\n\n')

        f.write('cc_library(\n')
        f.write('    name = "autoconf_library",\n')
        f.write('    hdrs = ["zephyr/autoconf.h"],\n')
        f.write('    includes = ["zephyr", "."],\n')
        f.write('    deps = [":devicetree_generated"],\n')
        f.write(')\n\n')

        f.write('directory(\n')
        f.write('    name = "autoconf_dir",\n')
        f.write('    srcs = ["zephyr/autoconf.h"],\n')
        f.write(')\n\n')

        f.write('zephyr_cc_library(\n')
        f.write('    name = "autoconf_symbols",\n')
        f.write('    srcs = ["zephyr/config.c"],\n')
        f.write('    copts = ["-D%s"],\n' % arch_macro)
        f.write('    deps = [\n')
        f.write('        ":autoconf_library",\n')
        f.write('        "@zephyr//include:zephyr",\n')
        f.write('    ],\n')
        f.write(')\n\n')

        allowed_symbols = None
        kconfig_symbols_file = getattr(args, "kconfig_symbols_file", None)
        if isinstance(kconfig_symbols_file, (str, Path)) and os.path.exists(
            kconfig_symbols_file
        ):
            with open(kconfig_symbols_file, "r", encoding="utf-8") as sym_f:
                allowed_symbols = {
                    line.strip() for line in sym_f if line.strip()
                }

        flags_lines = []
        for sym in kconf.unique_defined_syms:
             if not sym.nodes:
                 continue

             sname = kconfig_utils.sanitize_name_for_target(sym.name)
             full_name = "CONFIG_" + sname
             if allowed_symbols is not None and full_name not in allowed_symbols:
                 continue

             if sym.type in [kconfiglib.BOOL, kconfiglib.TRISTATE]:
                 if sym.str_value == "y":
                     flags_lines.append('        "--@zephyr_kconfig//:%s=true",\n' % full_name)
             elif sym.type == kconfiglib.INT:
                 if sym.str_value:
                     try:
                         val = int(sym.str_value)
                         if val != 0:
                             flags_lines.append('        "--@zephyr_kconfig//:%s=%d",\n' % (full_name, val))
                     except ValueError:
                         pass
             elif sym.type == kconfiglib.HEX:
                 if sym.str_value:
                     try:
                         val = int(sym.str_value, 16)
                         if val != 0:
                             flags_lines.append('        "--@zephyr_kconfig//:%s=%d",\n' % (full_name, val))
                     except ValueError:
                         pass
             elif sym.type == kconfiglib.STRING:
                 if sym.str_value:
                     flags_lines.append('        "--@zephyr_kconfig//:%s=%s",\n' % (full_name, sym.str_value))

        flags_str = "".join(flags_lines)

        extra_constraints_by_variant = {
            "gcc": ["@bazel_tools//tools/cpp:gcc"],
            "llvm": ["@bazel_tools//tools/cpp:clang"],
        }
        variants = (
            [args.toolchain_variant]
            if args.toolchain_variant
            else ["gcc", "llvm"]
        )
        for variant in variants:
            constraints = [
                "@zephyr//constraints:zephyr_autoconf_force_included",
            ] + extra_constraints_by_variant.get(variant, [])
            f.write('platform(\n')
            f.write('    name = "zc_target_platform_%s",\n' % variant)
            f.write('    parents = ["%s"],\n' % args.parent_platform)
            f.write('    constraint_values = [\n')
            for c in constraints:
                f.write('        "%s",\n' % c)
            f.write('    ],\n')
            f.write('    flags = [\n')
            f.write(flags_str)
            f.write('        "--@zephyr//:autoconf_file=@zc_target//:zephyr/autoconf.h",\n')
            f.write('        "--@zephyr//:autoconf_dir=@zc_target//:autoconf_dir",\n')
            f.write('        "--@zephyr//:kconfig_config_file=@zc_target//:.config",\n')
            f.write('        "--@zephyr//:autoconf_library=@zc_target//:autoconf_library",\n')
            f.write('        "--@zephyr//:autoconf_symbols_to_link=@zc_target//:autoconf_symbols",\n')
            f.write('        "--@zephyr//:dts_cc_library=@zc_target//:devicetree_generated",\n')
            f.write('        "--@zephyr//:edt_pickle=@zc_target//:edt.pickle",\n')
            f.write('    ],\n')
            f.write(')\n\n')
            f.write('alias(\n')
            f.write('    name = "platform_%s",\n' % variant)
            f.write('    actual = ":zc_target_platform_%s",\n' % variant)
            f.write(')\n\n')

def _can_reuse_kconfig_dts(args, zephyr_base, board_dir):
    kconfig_dts_file = getattr(args, "kconfig_dts_file", None)
    if not (
        isinstance(kconfig_dts_file, (str, os.PathLike))
        and os.path.isfile(kconfig_dts_file)
    ):
        return False
    shared_bindings = set()
    for root in (
        [zephyr_base]
        + list(getattr(args, "modules", None) or [])
        + list(getattr(args, "oot_dts_roots", None) or [])
    ):
        for rel in ("zephyr/dts/bindings", "dts/bindings"):
            bdir = Path(root) / rel
            if bdir.exists():
                shared_bindings.add(bdir.resolve())
                break
    for extra_root in (getattr(args, "app_dir", None), board_dir):
        if not isinstance(extra_root, (str, os.PathLike)) or not extra_root:
            continue
        for rel in ("zephyr/dts/bindings", "dts/bindings"):
            bdir = Path(extra_root) / rel
            if bdir.exists():
                if bdir.resolve() not in shared_bindings:
                    return False
                break
    return True


def run_kconfig_in_process(
    zephyr_base,
    kconfig_root,
    conf_files,
    config_out,
    autoconf_out,
    *,
    tracker,
    edt=None,
    forced_input_configs=False,
):
    """Evaluates Kconfig in-process in a single pass with validation checks."""
    kconfig_dir = os.path.abspath(os.path.join(zephyr_base, "scripts", "kconfig"))
    if kconfig_dir not in sys.path:
        sys.path.insert(0, kconfig_dir)
    kconfig_py = os.path.join(kconfig_dir, "kconfig.py")
    tracker.add(kconfig_py)

    saved_edt_pickle = os.environ.pop("EDT_PICKLE", None) if edt is not None else None
    try:
        import kconfig
        import kconfigfunctions
        import kconfiglib
    finally:
        if saved_edt_pickle is not None:
            os.environ["EDT_PICKLE"] = saved_edt_pickle

    kconfigfunctions.doc_mode = os.environ.get("KCONFIG_DOC_MODE") == "1"
    try:
        if not kconfigfunctions.doc_mode:
            if edt is not None:
                kconfigfunctions.edt = edt
                kconfigfunctions.edtlib = inspect.getmodule(edt)
            else:
                edt_pickle = os.environ.get("EDT_PICKLE")
                if edt_pickle and os.path.isfile(edt_pickle):
                    with open(edt_pickle, "rb") as f:
                        kconfigfunctions.edt = pickle.load(f)
                        kconfigfunctions.edtlib = inspect.getmodule(
                            kconfigfunctions.edt
                        )
                else:
                    kconfigfunctions.edt = None
                    kconfigfunctions.edtlib = None

        with kconfig_utils.record_kconfig_sources(kconfiglib, tracker):
            kconf = kconfiglib.Kconfig(
                kconfig_root, warn_to_stderr=False, suppress_traceback=True
            )

        kconf.warn_assign_undef = True
        kconf.warn_assign_override = False
        kconf.warn_assign_redun = False

        if conf_files:
            kconf.load_config(conf_files[0])
            for config in conf_files[1:]:
                kconf.load_config(config, replace=False)

        kconfig.check_no_promptless_assign(kconf)
        kconfig.check_assigned_sym_values(kconf)
        kconfig.check_assigned_choice_values(kconf)

        if kconf.syms.get("WARN_DEPRECATED", kconf.y).tri_value == 2:
            kconfig.check_deprecated(kconf)

        if kconf.syms.get("WARN_EXPERIMENTAL", kconf.y).tri_value == 2:
            kconfig.check_experimental(kconf)

        kconfig.check_not_secure(kconf)
        kconf.write_config(os.devnull)

        warn_only = r"warning:.*set more than once."

        if kconf.warnings:
            error_out = not forced_input_configs
            for warning in kconf.warnings:
                print("\n" + warning, file=sys.stderr)
                if not error_out and not re.search(warn_only, warning):
                    error_out = True
            if error_out:
                kconfig.err("Aborting due to Kconfig warnings")

        os.makedirs(os.path.dirname(os.path.abspath(config_out)), exist_ok=True)
        os.makedirs(
            os.path.dirname(os.path.abspath(autoconf_out)), exist_ok=True
        )
        kconf.write_config(config_out)
        kconf.write_autoconf(autoconf_out)

        for path in set(kconf.kconfig_filenames):
            tracker.add(os.path.realpath(os.path.join(kconf.srctree, path)))

        return kconf, kconfiglib
    finally:
        kconfigfunctions.edt = None
        kconfigfunctions.edtlib = None


def main():
    args = parse_args()

    zephyr_base = os.path.abspath(args.zephyr_base)
    output_dir = os.path.abspath(args.output_dir)
    board_dir = os.path.abspath(args.board_dir)

    tracker = kconfig_utils.InputRecorder()

    board_name = args.board.split("/")[0]
    tracker.add(os.path.join(board_dir, "board.yml"), os.path.join(board_dir, f"{board_name}.dts"))
    if not os.path.exists(os.path.join(board_dir, "board.yml")) and not os.path.exists(os.path.join(board_dir, f"{board_name}.dts")):
        found = False
        for root in [board_dir] + args.oot_dts_roots:
            if not os.path.isdir(root):
                tracker.add(root)
            for dirpath, dirs, filenames in kconfig_utils.filtered_walk(root, tracker=tracker):
                if os.path.basename(dirpath) == board_name or f"{board_name}.dts" in filenames or any(f.startswith(f"{board_name}_") and f.endswith(".dts") for f in filenames):
                    board_dir = os.path.abspath(dirpath)
                    found = True
                    break
            if found: break

    with tempfile.TemporaryDirectory() as tmp_dir:
        setup_environment(args, zephyr_base, tmp_dir, board_dir, tracker=tracker)

        generate_kconfig_aggregations(zephyr_base, args, tmp_dir, board_dir, tracker=tracker)

        for frag in args.conf_fragments:
            tracker.add(frag)

        merged_dts_path, dts_roots = preprocess_dts(
            args, zephyr_base, tmp_dir, board_dir, tracker=tracker, rel_base_dir=output_dir
        )
        edt = generate_edt_pickle(
            zephyr_base,
            output_dir,
            dts_roots,
            merged_dts_path,
            tracker=tracker,
        )
        generate_dts_headers(
            zephyr_base,
            output_dir,
            os.path.join(output_dir, "edt.pickle"),
            tracker=tracker,
            edt=edt,
        )
        if _can_reuse_kconfig_dts(args, zephyr_base, board_dir):
            tracker.add(
                os.path.join(
                    zephyr_base,
                    "scripts",
                    "dts",
                    "gen_driver_kconfig_dts.py",
                )
            )
            shutil.copyfile(
                args.kconfig_dts_file, os.path.join(tmp_dir, "Kconfig.dts")
            )
        else:
            kconfig_utils.generate_kconfig_dts(
                zephyr_base,
                os.path.join(tmp_dir, "Kconfig.dts"),
                dts_roots,
                tracker=tracker,
            )

        conf_files = get_conf_files(args, board_dir, tracker=tracker)
        conf_files.extend(args.conf_fragments)

        os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)

        raw_forced_fragments = getattr(args, "forced_conf_fragments", None)
        forced_fragments = (
            list(raw_forced_fragments)
            if isinstance(raw_forced_fragments, (list, tuple))
            else []
        )
        forced_conf_files = []
        for frag in forced_fragments:
            tracker.add(frag)
            if os.path.exists(frag) and frag not in forced_conf_files:
                forced_conf_files.append(frag)
        sysbuild_forced_conf = generate_sysbuild_forced_config(
            zephyr_base, args, tmp_dir, board_dir, tracker=tracker
        )
        if sysbuild_forced_conf:
            forced_conf_files.append(sysbuild_forced_conf)

        kconfig_root = os.path.join(zephyr_base, "Kconfig")
        app_kconfig = os.path.join(args.app_dir, "Kconfig")
        if os.path.exists(app_kconfig):
            kconfig_root = app_kconfig

        autoconf_out = os.path.join(output_dir, "zephyr", "autoconf.h")
        config_out = os.path.join(output_dir, ".config")
        kconfig_py = os.path.join(zephyr_base, "scripts", "kconfig", "kconfig.py")

        if not _is_mock(subprocess.run) and os.path.isfile(kconfig_py):
            kconf, kconfiglib = run_kconfig_in_process(
                zephyr_base,
                kconfig_root,
                conf_files + forced_conf_files,
                config_out,
                autoconf_out,
                tracker=tracker,
                edt=edt,
                forced_input_configs=bool(forced_conf_files),
            )
        else:
            env = os.environ.copy()
            tracker.add(kconfig_py)
            tmp_config_path = os.path.join(tmp_dir, ".config")
            kconfig_list_path = os.path.join(tmp_dir, "kconfig_list.txt")
            cmd = [
                sys.executable,
                "-B",
                "-s",
                kconfig_py,
                "--handwritten-input-configs",
            ]
            if forced_conf_files:
                cmd.append("--forced-input-configs")
            cmd.extend([
                kconfig_root,
                tmp_config_path,
                autoconf_out,
                kconfig_list_path,
            ] + conf_files + forced_conf_files)

            res = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if res.stderr:
                print(res.stderr, file=sys.stderr)

            if res.returncode != 0:
                sys.exit(f"Kconfig generation failed with exit code {res.returncode}")

            if os.path.exists(tmp_config_path):
                shutil.copyfile(tmp_config_path, config_out)

            import kconfiglib
            # This parse sees the same environment as kconfig.py's, so its 'source'
            # globs and optional sources are the ones kconfig_list.txt doesn't show.
            with kconfig_utils.record_kconfig_sources(kconfiglib, tracker):
                kconf = kconfiglib.Kconfig(kconfig_root)
            kconf.load_config(config_out)
            tracker.add_kconfig_sources(kconfig_list_path)

        # Add the app name to autoconf.h
        with open(autoconf_out, "a") as f:
            f.write(f'#define APP_NAME "{args.app_name}"\n')

        extra_autoconf_defines = [
            ("ZVFS_EVENTFD_SIZE", _get_zvfs_eventfd_size(kconf)),
            ("ZVFS_OPEN_SIZE", _get_zvfs_open_size(kconf)),
        ]
        if any(val is not None for _, val in extra_autoconf_defines):
            with open(autoconf_out, "a") as f:
                for macro_name, macro_val in extra_autoconf_defines:
                    if macro_val is not None:
                        f.write(f"#define {macro_name} {macro_val}\n")

        generate_config_c(kconf, output_dir, args)
        generate_bazel_build(args, kconf, output_dir, kconfiglib)

        # Python code that ran: this script, its helpers, kconfiglib and
        # kconfigfunctions, and the devicetree modules loaded from edt.pickle.
        tracker.add_python_modules(
            os.path.join(zephyr_base, "scripts"),
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        tracker.write(output_dir=output_dir, exclude_dirs=[tmp_dir])

if __name__ == "__main__":
    main()
