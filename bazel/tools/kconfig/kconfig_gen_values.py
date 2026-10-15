# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import argparse
import pickle
import shutil
import subprocess
import tempfile
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
    parser.add_argument("--board", required=True)
    parser.add_argument("--board-dir", required=True)
    parser.add_argument("--parent-platform", required=True)
    parser.add_argument("--modules", nargs="+", default=[])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--oot-dts-roots", nargs="+", default=[])
    parser.add_argument("--app-name", default="zephyr_app")
    parser.add_argument("--toolchain-variant", default=None)
    parser.add_argument("--conf-fragments", nargs="+", default=[])
    parser.add_argument("--dtc-overlays", nargs="+", default=[])
    return parser.parse_args()

def setup_environment(args, zephyr_base, output_dir, board_dir):
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
                    module_name = os.path.basename(m.rstrip('/')).split('+')[-1].replace('-', '_').upper()
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

def preprocess_dts(args, zephyr_base, output_dir, board_dir, *, tracker):
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
        def _relativize_line(match):
            prefix, line_path, suffix = match.group(1), match.group(2), match.group(3)
            if os.path.isabs(line_path) or line_path.startswith(".."):
                abs_line = line_path if os.path.isabs(line_path) else os.path.abspath(os.path.join(abs_out, line_path))
                if (abs_line + os.sep).startswith(abs_out + os.sep):
                    rel_line = os.path.relpath(abs_line, abs_out)
                else:
                    rel_line = kconfig_utils.clean_output_path(abs_line, output_dir)
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

def _normalize_edt_pickle(edt_pickle_path, zephyr_base, output_dir):
    if not os.path.exists(edt_pickle_path):
        return
    dt_src = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "python-devicetree", "src"))
    if dt_src not in sys.path:
        sys.path.insert(0, dt_src)
    with open(edt_pickle_path, "rb") as f:
        edt = pickle.load(f)
    if getattr(edt, "dts_path", None):
        edt.dts_path = os.path.basename(edt.dts_path)
    if hasattr(edt, "_dt") and getattr(edt._dt, "filename", None):
        edt._dt.filename = os.path.basename(edt._dt.filename)
    edt.bindings_dirs = [kconfig_utils.clean_output_path(d, output_dir) for d in edt.bindings_dirs]
    edt._binding_paths = [kconfig_utils.clean_output_path(p, output_dir) for p in edt._binding_paths]
    for k, v in list(edt._binding_fname2path.items()):
        edt._binding_fname2path[k] = kconfig_utils.clean_output_path(v, output_dir)
    seen = set()
    def _clean_binding(b):
        while b is not None and id(b) not in seen:
            seen.add(id(b))
            if b.path:
                b.path = kconfig_utils.clean_output_path(b.path, output_dir)
            b = getattr(b, "child_binding", None)
    for b in edt._compat2binding.values():
        _clean_binding(b)
    for node in edt.nodes:
        _clean_binding(getattr(node, "_binding", None))
    with open(edt_pickle_path, "wb") as f:
        pickle.dump(edt, f, protocol=4)

def generate_edt_pickle(zephyr_base, output_dir, dts_roots, merged_dts_path, *, tracker):
    """Runs gen_edt.py (or gen_defines.py) to write edt.pickle."""
    output_edt_pickle_path = os.path.join(output_dir, "edt.pickle")
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    bindings_dirs = []
    seen_resolved = set()
    for dts_root in dts_roots:
        for b in ("zephyr/dts/bindings", "dts/bindings"):
            bdir = dts_root / b
            if bdir.exists():
                resolved = bdir.resolve()
                tracker.add_tree(resolved, kconfig_utils.BINDING_SUFFIXES)
                if resolved not in seen_resolved:
                    seen_resolved.add(resolved)
                    bindings_dirs.append(os.path.relpath(bdir, output_dir))
                break
            else:
                tracker.add(str(bdir))

    gen_edt_py = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "gen_edt.py"))
    gen_defines_py = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py"))

    tracker.add(gen_edt_py, *kconfig_utils.dts_python_sources(zephyr_base))

    env = _dts_subprocess_env(zephyr_base)

    rel_edt_pickle = os.path.relpath(output_edt_pickle_path, output_dir)
    rel_merged_dts = os.path.relpath(merged_dts_path, output_dir)
    rel_dts_debug = os.path.relpath(f"{merged_dts_path}.debug", output_dir)

    if os.path.exists(gen_edt_py):
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
        for bdir in bindings_dirs:
            vp = os.path.join(bdir, "vendor-prefixes.txt")
            vp_abs = os.path.join(output_dir, vp)
            tracker.add(vp_abs)
            if os.path.exists(vp_abs):
                gen_edt_args.extend(["--vendor-prefixes", vp])
        gen_edt_args.extend([
            "--dts-out",
            rel_dts_debug,
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ])
        subprocess.run(gen_edt_args, env=env, cwd=output_dir, check=True)
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
        subprocess.run(cmd, env=env, cwd=output_dir, check=True)

    _normalize_edt_pickle(output_edt_pickle_path, zephyr_base, output_dir)
    os.environ["EDT_PICKLE"] = output_edt_pickle_path

def generate_dts_headers(zephyr_base, output_dir, edt_pickle_path, *, tracker):
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    if os.path.exists(output_header):
        return
    gen_defines_py = os.path.abspath(os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py"))
    tracker.add(gen_defines_py, *kconfig_utils.dts_python_sources(zephyr_base))
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    cmd = [
        sys.executable,
        "-B",
        "-s",
        gen_defines_py,
        "--edt-pickle", os.path.relpath(edt_pickle_path, output_dir),
        "--header-out", os.path.relpath(output_header, output_dir),
    ]

    subprocess.run(cmd, env=_dts_subprocess_env(zephyr_base), cwd=output_dir, check=True)

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
        f.write('load("@zephyr//bazel:cc.bzl", "zephyr_cc_library")\n')
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

        flags_lines = []
        for sym in kconf.unique_defined_syms:
             if not sym.nodes:
                 continue

             sname = kconfig_utils.sanitize_name_for_target(sym.name)
             full_name = "CONFIG_" + sname

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
        setup_environment(args, zephyr_base, tmp_dir, board_dir)

        generate_kconfig_aggregations(zephyr_base, args, tmp_dir, board_dir, tracker=tracker)

        for frag in args.conf_fragments:
            tracker.add(frag)

        merged_dts_path, dts_roots = preprocess_dts(args, zephyr_base, tmp_dir, board_dir, tracker=tracker)
        generate_edt_pickle(zephyr_base, output_dir, dts_roots, merged_dts_path, tracker=tracker)
        generate_dts_headers(zephyr_base, output_dir, os.path.join(output_dir, "edt.pickle"), tracker=tracker)
        kconfig_utils.generate_kconfig_dts(zephyr_base, os.path.join(tmp_dir, "Kconfig.dts"), dts_roots, tracker=tracker)

        conf_files = get_conf_files(args, board_dir, tracker=tracker)
        conf_files.extend(args.conf_fragments)

        os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)

        env = os.environ.copy()

        kconfig_root = os.path.join(zephyr_base, "Kconfig")
        app_kconfig = os.path.join(args.app_dir, "Kconfig")
        if os.path.exists(app_kconfig):
            kconfig_root = app_kconfig

        # Call the definitive Zephyr's kconfig.py
        kconfig_py = os.path.join(zephyr_base, "scripts", "kconfig", "kconfig.py")
        tracker.add(kconfig_py)
        tmp_config_path = os.path.join(tmp_dir, ".config")
        kconfig_list_path = os.path.join(tmp_dir, "kconfig_list.txt")
        cmd = [
            sys.executable,
            "-B",
            "-s",
            kconfig_py,
            "--handwritten-input-configs",
            kconfig_root,
            tmp_config_path,
            os.path.join(output_dir, "zephyr", "autoconf.h"),
            kconfig_list_path,
        ] + conf_files

        res = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if res.stderr:
            print(res.stderr, file=sys.stderr)

        if res.returncode != 0:
            sys.exit(f"Kconfig generation failed with exit code {res.returncode}")

        if os.path.exists(tmp_config_path):
            shutil.copyfile(tmp_config_path, os.path.join(output_dir, ".config"))

        # Add the app name to the autoconf.h natively
        with open(os.path.join(output_dir, "zephyr", "autoconf.h"), "a") as f:
            f.write(f'#define APP_NAME "{args.app_name}"\n')

        # Load final cleanly resolved config
        import kconfiglib
        # This parse sees the same environment as kconfig.py's, so its 'source'
        # globs and optional sources are the ones kconfig_list.txt doesn't show.
        with kconfig_utils.record_kconfig_sources(kconfiglib, tracker):
            kconf = kconfiglib.Kconfig(kconfig_root)
        kconf.load_config(os.path.join(output_dir, ".config"))

        generate_config_c(kconf, output_dir, args)
        generate_bazel_build(args, kconf, output_dir, kconfiglib)

        # Record out-of-tree Kconfigs
        tracker.add_kconfig_sources(kconfig_list_path)

        # Python code that ran: this script, its helpers, kconfiglib and
        # kconfigfunctions, and the devicetree modules loaded from edt.pickle.
        tracker.add_python_modules(
            os.path.join(zephyr_base, "scripts"),
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        tracker.write(output_dir=output_dir, exclude_dirs=[tmp_dir])

if __name__ == "__main__":
    main()
