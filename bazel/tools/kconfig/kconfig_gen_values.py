# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import argparse
import subprocess
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
    os.environ["srctree"] = zephyr_base
    os.environ["ZEPHYR_BASE"] = zephyr_base
    os.environ["KCONFIG_BINARY_DIR"] = output_dir

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
    if not toolchain_variant:
        board_dir_lower = board_dir.lower()
        if "native" in args.board or "boards/native" in board_dir_lower or "posix" in board_dir_lower:
            toolchain_variant = "host"
        else:
            toolchain_variant = "zephyr"

    os.environ["ZEPHYR_TOOLCHAIN_VARIANT"] = toolchain_variant
    os.environ["TOOLCHAIN_KCONFIG_DIR"] = os.path.join(zephyr_base, "cmake", "toolchain", toolchain_variant)
    os.environ["BOARD_DIR"] = os.path.abspath(board_dir)
    os.environ["KCONFIG_BOARD_DIR"] = os.path.abspath(board_dir)
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
                    m_abs = os.path.abspath(m)
                    f.write(f"ZEPHYR_{module_name}_MODULE_DIR={m_abs}\n")
                    os.environ[f"ZEPHYR_{module_name}_MODULE_DIR"] = m_abs
    os.environ["KCONFIG_ENV_FILE"] = kconfig_env_file

def generate_kconfig_aggregations(zephyr_base, args, output_dir, board_dir):
    # Generate aggregation Kconfig files
    soc_dirs = []

    # Try to find SoC name from board.yml
    soc_names = []
    for board_file in ["board.yml", "board.yaml"]:
        board_yml_path = os.path.join(board_dir, board_file)
        if os.path.exists(board_yml_path):
            with open(board_yml_path, 'r') as f:
                content = f.read()
                # Simple heuristic to find soc name in board.yml
                # It looks like:
                # socs:
                #   - name: same70q21b
                matches = re.findall(r"-\s*name:\s*(\S+)", content)
                if matches:
                    soc_names.extend(matches)
            break

    soc_roots = [Path(zephyr_base)] + ([Path(m) for m in args.modules] if args.modules else [])
    for sroot in soc_roots:
        if not sroot.exists():
            continue
        for root, dirs, files in kconfig_utils.filtered_walk(sroot):
            if "soc.yml" in files:
                soc_dirs.append(root)

    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.defconfig"), soc_dirs, "SoC defconfigs")
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig"), soc_dirs, "SoC Kconfigs")
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.soc"), soc_dirs, "SoC Kconfigs")
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "soc", "Kconfig.sysbuild"), soc_dirs, "SoC sysbuild Kconfigs")

    shield_defconfig = os.path.join(output_dir, "Kconfig.shield.defconfig")
    os.makedirs(os.path.dirname(shield_defconfig), exist_ok=True)
    with open(shield_defconfig, "w") as f:
        f.write("# Empty shield defconfig\n")

    arch_dirs = []
    arch_root = os.path.join(zephyr_base, "arch")
    for d in os.listdir(arch_root):
        if os.path.isdir(os.path.join(arch_root, d)):
            arch_dirs.append(os.path.join(arch_root, d))
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "arch", "Kconfig"), arch_dirs, "Arch Kconfigs")

    board_dirs = [board_dir]
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig.defconfig"), board_dirs, "Board defconfigs")
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig"), board_dirs, "Board Kconfigs")
    kconfig_utils.generate_aggregation_file(os.path.join(output_dir, "boards", "Kconfig.sysbuild"), board_dirs, "Board sysbuild Kconfigs")

    board_name = os.environ["BOARD"]
    board_kconfig_agg = os.path.join(output_dir, "boards", f"Kconfig.{board_name}")
    os.makedirs(os.path.dirname(board_kconfig_agg), exist_ok=True)
    with open(board_kconfig_agg, "w") as f:
        board_kconfig = os.path.join(board_dir, "Kconfig")
        if not os.path.exists(board_kconfig):
             board_kconfig = os.path.join(board_dir, f"Kconfig.{board_name}")
        if os.path.exists(board_kconfig):
            f.write(f'osource "{os.path.abspath(board_kconfig)}"\n')

    kconfig_modules = os.path.join(output_dir, "Kconfig.modules")
    kconfig_utils.generate_kconfig_modules(zephyr_base, args.modules, kconfig_modules)

def discover_overlays(app_dir, board_name, board_qualifiers, board_revision="", board_dir=""):
    overlays = []

    # 1. Board-level revision overlays in board_dir
    board_rev_overlays = discovery_utils.get_board_revision_overlays(
        board_dir, board_name, board_qualifiers, board_revision
    )
    for cand in board_rev_overlays:
        if cand not in overlays:
            overlays.append(cand)

    # 2. App-level board overlays in app_dir/boards/ (precedence: base -> qualified -> revision -> qualified revision)
    app_boards_dir = os.path.join(app_dir, "boards")
    if os.path.exists(app_boards_dir):
        app_candidates = discovery_utils.get_app_board_override_candidates(
            board_name, board_qualifiers, board_revision, "overlay"
        )
        for cand_file in app_candidates:
            cand_path = os.path.join(app_boards_dir, cand_file)
            if os.path.exists(cand_path) and cand_path not in overlays:
                overlays.append(cand_path)

    # 3. Default app overlay
    app_overlay = os.path.join(app_dir, "app.overlay")
    if os.path.exists(app_overlay) and app_overlay not in overlays:
        overlays.append(app_overlay)

    return overlays

def preprocess_dts(args, zephyr_base, output_dir, board_dir):
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
        if os.path.exists(board_yml_path):
            with open(board_yml_path, 'r') as f:
                content = f.read()
                matches = re.findall(r"-\s*name:\s*(\S+)", content)
                for soc in matches:
                    candidates.append(os.path.join(board_dir, f"{board_name}_{soc}.dts"))
            break

    dts_file = None
    for candidate in candidates:
        if os.path.exists(candidate):
            dts_file = candidate
            break

    if not dts_file:
        raise RuntimeError(f"Could not find DTS file for board {args.board} in {board_dir}. Tried: {candidates}")

    overlays = discover_overlays(args.app_dir, board_name, board_qualifiers, board_revision, board_dir)
    for extra_overlay in args.dtc_overlays:
        if os.path.exists(extra_overlay) and extra_overlay not in overlays:
            overlays.append(extra_overlay)

    dts_input_path = os.path.join(output_dir, "dts_input.c")
    os.makedirs(output_dir, exist_ok=True)
    with open(dts_input_path, "w") as f:
        f.write("/* Generated by zephyr-bazel - do not edit! */\n")
        f.write(f'#include "{os.path.abspath(dts_file)}"\n')
        for overlay in overlays:
            f.write(f'#include "{os.path.abspath(overlay)}"\n')

    merged_dts_path = os.path.join(output_dir, "zephyr.dts")

    # Preprocess DTS using pcpp
    import pcpp
    pcmd_path = os.path.join(os.path.dirname(pcpp.__file__), "pcmd.py")
    pcpp_args = [
        sys.executable,
        pcmd_path,
        dts_input_path,
    ]

    raw_roots = [Path(r) for r in args.oot_dts_roots] + [Path(m) for m in args.modules] + [Path(zephyr_base)]
    dts_roots = []
    for r in raw_roots:
        if r not in dts_roots:
            dts_roots.append(r)
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
                pcpp_args.append("-I" + str(path.resolve()))
    pcpp_args.extend(["-o", merged_dts_path])

    subprocess.run(pcpp_args, check=True)
    return merged_dts_path, dts_roots

def generate_edt_pickle(zephyr_base, output_dir, dts_roots, merged_dts_path):
    output_edt_pickle_path = os.path.join(output_dir, "edt.pickle")
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    bindings_dirs = []
    for dts_root in dts_roots:
        bdir = dts_root / "zephyr" / "dts" / "bindings"
        if bdir.exists():
            if str(bdir.resolve()) not in bindings_dirs:
                bindings_dirs.append(str(bdir.resolve()))
        else:
            bdir = dts_root / "dts" / "bindings"
            if bdir.exists():
                if str(bdir.resolve()) not in bindings_dirs:
                    bindings_dirs.append(str(bdir.resolve()))

    gen_edt_py = os.path.join(zephyr_base, "scripts", "dts", "gen_edt.py")
    gen_defines_py = os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([
        os.path.join(zephyr_base, "scripts", "dts"),
        os.path.join(zephyr_base, "scripts", "dts", "python-devicetree", "src"),
        env.get("PYTHONPATH", ""),
    ])

    if os.path.exists(gen_edt_py):
        gen_edt_args = [
            sys.executable,
            gen_edt_py,
            "--edt-pickle-out",
            output_edt_pickle_path,
            "--dts",
            merged_dts_path,
            "--bindings-dirs",
        ]
        gen_edt_args.extend(bindings_dirs)
        for bdir in bindings_dirs:
            vp = os.path.join(bdir, "vendor-prefixes.txt")
            if os.path.exists(vp):
                gen_edt_args.extend(["--vendor-prefixes", vp])
        gen_edt_args.extend([
            "--dts-out",
            os.path.join(output_dir, "zephyr.dts.debug"),
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ])
        subprocess.run(gen_edt_args, env=env, check=True)
    else:
        cmd = [
            sys.executable,
            gen_defines_py,
            "--dts",
            merged_dts_path,
            "--bindings-dirs",
        ]
        cmd.extend(bindings_dirs)
        cmd.extend([
            "--header-out",
            output_header,
            "--dts-out",
            os.path.join(output_dir, "zephyr.dts.debug"),
            "--edt-pickle-out",
            output_edt_pickle_path,
            "--dtc-flags",
            "Wno-simple_bus_reg",
        ])
        subprocess.run(cmd, env=env, check=True)

    os.environ["EDT_PICKLE"] = output_edt_pickle_path

def generate_dts_headers(zephyr_base, output_dir, edt_pickle_path):
    output_header = os.path.join(output_dir, "zephyr", "devicetree_generated.h")
    if os.path.exists(output_header):
        return
    gen_defines_py = os.path.join(zephyr_base, "scripts", "dts", "gen_defines.py")
    os.makedirs(os.path.dirname(output_header), exist_ok=True)

    cmd = [
        sys.executable,
        gen_defines_py,
        "--edt-pickle", edt_pickle_path,
        "--header-out", output_header,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([
        os.path.join(zephyr_base, "scripts", "dts"),
        os.path.join(zephyr_base, "scripts", "dts", "python-devicetree", "src"),
        env.get("PYTHONPATH", ""),
    ])

    subprocess.run(cmd, env=env, check=True)

def get_conf_files(args, board_dir):
    board_name = os.environ["BOARD"]
    board_qualifiers = os.environ.get("BOARD_QUALIFIERS", "").lstrip("/")
    board_revision = os.environ.get("BOARD_REVISION", "")

    conf_files = []

    # 1 & 2. Base and qualified board defconfigs (HWM v2) using shared candidate logic
    for cand in discovery_utils.get_app_board_override_candidates(board_name, board_qualifiers, "", "defconfig", sep="_"):
        cand_path = os.path.join(board_dir, cand)
        if os.path.exists(cand_path) and cand_path not in conf_files:
            conf_files.append(cand_path)

    # 3. Revision defconfig in board directory
    rev_defconfigs = discovery_utils.get_board_revision_defconfigs(
        board_dir, board_name, board_qualifiers, board_revision
    )
    for rev_defconfig in rev_defconfigs:
        if rev_defconfig not in conf_files:
            conf_files.append(rev_defconfig)

    # 4. Base application prj.conf
    prj_conf = os.path.join(args.app_dir, "prj.conf")
    if os.path.exists(prj_conf):
        conf_files.append(prj_conf)

    # 5. Application board conf candidates (precedence: base -> qualified -> revision -> qualified revision)
    app_boards_dir = os.path.join(args.app_dir, "boards")
    if os.path.exists(app_boards_dir):
        app_candidates = discovery_utils.get_app_board_override_candidates(
            board_name, board_qualifiers, board_revision, "conf"
        )
        for conf_file in app_candidates:
            conf_path = os.path.join(app_boards_dir, conf_file)
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

        # GCC Platform
        f.write('platform(\n')
        f.write('    name = "zc_target_platform_gcc",\n')
        f.write('    parents = ["%s"],\n' % args.parent_platform)
        f.write('    constraint_values = [\n')
        f.write('        "@zephyr//constraints:zephyr_autoconf_force_included",\n')
        f.write('        "@bazel_tools//tools/cpp:gcc",\n')
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
        f.write('    name = "platform_gcc",\n')
        f.write('    actual = ":zc_target_platform_gcc",\n')
        f.write(')\n\n')

        # LLVM Platform
        f.write('platform(\n')
        f.write('    name = "zc_target_platform_llvm",\n')
        f.write('    parents = ["%s"],\n' % args.parent_platform)
        f.write('    constraint_values = [\n')
        f.write('        "@zephyr//constraints:zephyr_autoconf_force_included",\n')
        f.write('        "@bazel_tools//tools/cpp:clang",\n')
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
        f.write('    name = "platform_llvm",\n')
        f.write('    actual = ":zc_target_platform_llvm",\n')
        f.write(')\n\n')


def write_deps_files(output_dir, args, board_dir, conf_files):
    out_real = os.path.realpath(output_dir)
    deps = set()
    dep_dirs = set()

    # 1. Kconfig files visited by kconfig.py
    kconfig_list_path = os.path.join(output_dir, "kconfig_list.txt")
    if os.path.exists(kconfig_list_path):
        with open(kconfig_list_path, "r") as f:
            for line in f:
                path = line.strip()
                if path:
                    real = os.path.realpath(path)
                    if real != out_real and not real.startswith(out_real + os.sep):
                        deps.add(real)

    # 2. Conf files and fragments
    for conf in conf_files:
        deps.add(os.path.realpath(conf))

    # 3. Application probed candidates (even if non-existent) and boards dir
    app_dir = getattr(args, "app_dir", None)
    if app_dir:
        deps.add(os.path.realpath(os.path.join(app_dir, "prj.conf")))
        deps.add(os.path.realpath(os.path.join(app_dir, "Kconfig")))
        deps.add(os.path.realpath(os.path.join(app_dir, "app.overlay")))
        dep_dirs.add(os.path.realpath(app_dir))
        dep_dirs.add(os.path.realpath(os.path.join(app_dir, "boards")))

    # 4. Devicetree files and overlays from dts_input.c
    dts_input_c = os.path.join(output_dir, "dts_input.c")
    if os.path.exists(dts_input_c):
        with open(dts_input_c, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith('#include "') and line.endswith('"'):
                    inc_path = line[len('#include "'):-1]
                    deps.add(os.path.realpath(inc_path))
    elif app_dir and board_dir:
        board_name = os.environ.get("BOARD", "")
        board_qualifiers = os.environ.get("BOARD_QUALIFIERS", "")
        board_revision = os.environ.get("BOARD_REVISION", "")
        for ov in discover_overlays(app_dir, board_name, board_qualifiers, board_revision, board_dir):
            deps.add(os.path.realpath(ov))

    # 5. Extra DTC overlays from args
    if hasattr(args, "dtc_overlays") and args.dtc_overlays:
        for overlay in args.dtc_overlays:
            deps.add(os.path.realpath(overlay))

    # 6. Board directory and board metadata
    if board_dir:
        dep_dirs.add(os.path.realpath(board_dir))
        for meta in ["board.yml", "board.yaml", "Kconfig"]:
            meta_path = os.path.join(board_dir, meta)
            if os.path.exists(meta_path):
                deps.add(os.path.realpath(meta_path))
        board_name = os.environ.get("BOARD", "")
        if board_name:
            board_kconfig = os.path.join(board_dir, f"Kconfig.{board_name}")
            if os.path.exists(board_kconfig):
                deps.add(os.path.realpath(board_kconfig))
        board_rev_dir = os.path.join(board_dir, "revisions")
        if os.path.exists(board_rev_dir):
            dep_dirs.add(os.path.realpath(board_rev_dir))

    # Write deps.txt
    with open(os.path.join(output_dir, "deps.txt"), "w") as f:
        for dep in sorted(deps):
            f.write(dep + "\n")

    # Write dep_dirs.txt
    with open(os.path.join(output_dir, "dep_dirs.txt"), "w") as f:
        for d in sorted(dep_dirs):
            f.write(d + "\n")





def main():
    args = parse_args()

    zephyr_base = os.path.abspath(args.zephyr_base)
    output_dir = os.path.abspath(args.output_dir)
    board_dir = os.path.abspath(args.board_dir)

    board_name = args.board.split("/")[0]
    if not os.path.exists(os.path.join(board_dir, "board.yml")) and not os.path.exists(os.path.join(board_dir, f"{board_name}.dts")):
        found = False
        for root in [board_dir] + args.oot_dts_roots:
            for dirpath, dirs, filenames in kconfig_utils.filtered_walk(root):
                if os.path.basename(dirpath) == board_name or f"{board_name}.dts" in filenames or any(f.startswith(f"{board_name}_") and f.endswith(".dts") for f in filenames):
                    board_dir = os.path.abspath(dirpath)
                    found = True
                    break
            if found: break

    setup_environment(args, zephyr_base, output_dir, board_dir)

    generate_kconfig_aggregations(zephyr_base, args, output_dir, board_dir)

    merged_dts_path, dts_roots = preprocess_dts(args, zephyr_base, output_dir, board_dir)
    generate_edt_pickle(zephyr_base, output_dir, dts_roots, merged_dts_path)
    generate_dts_headers(zephyr_base, output_dir, os.path.join(output_dir, "edt.pickle"))
    kconfig_utils.generate_kconfig_dts(zephyr_base, os.path.join(output_dir, "Kconfig.dts"), dts_roots)

    # Re-verify environment for kconfiglib
    os.environ["ARCH"] = "*"
    os.environ["ZEPHYR_BASE"] = zephyr_base

    conf_files = get_conf_files(args, board_dir)
    conf_files.extend(args.conf_fragments)

    os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)

    # Setup base environment variables for kconfig execution
    env = os.environ.copy()
    env["BOARD_DIR"] = os.path.abspath(board_dir)
    env["KCONFIG_BOARD_DIR"] = os.path.abspath(board_dir)
    env["ARCH_DIR"] = "arch"
    env["SOC_DIR"] = "soc"

    kconfig_root = os.path.join(zephyr_base, "Kconfig")
    app_kconfig = os.path.join(args.app_dir, "Kconfig")
    if os.path.exists(app_kconfig):
        kconfig_root = app_kconfig

    # Call the definitive Zephyr's kconfig.py
    kconfig_py = os.path.join(zephyr_base, "scripts", "kconfig", "kconfig.py")
    cmd = [
        sys.executable,
        kconfig_py,
        "--handwritten-input-configs",
        kconfig_root,
        os.path.join(output_dir, ".config"),
        os.path.join(output_dir, "zephyr", "autoconf.h"),
        os.path.join(output_dir, "kconfig_list.txt"),
    ] + conf_files

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    if res.stderr:
        print(res.stderr, file=sys.stderr)

    if res.returncode != 0:
        sys.exit(f"Kconfig generation failed with exit code {res.returncode}")

    # Add the app name to the autoconf.h natively
    with open(os.path.join(output_dir, "zephyr", "autoconf.h"), "a") as f:
        f.write(f'#define APP_NAME "{args.app_name}"\n')

    # Load final cleanly resolved config
    import kconfiglib
    kconf = kconfiglib.Kconfig(kconfig_root)
    kconf.load_config(os.path.join(output_dir, ".config"))

    generate_config_c(kconf, output_dir, args)
    generate_bazel_build(args, kconf, output_dir, kconfiglib)
    write_deps_files(output_dir, args, board_dir, conf_files)

if __name__ == "__main__":
    main()
