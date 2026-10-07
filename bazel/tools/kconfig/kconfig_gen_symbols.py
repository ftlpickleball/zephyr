# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import argparse
import tempfile
import re
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import collections

import kconfig_utils
import discovery_utils

try:
    import yaml

    try:
        from yaml import CSafeLoader as SafeLoader
    except ImportError:
        from yaml import SafeLoader
except ImportError:
    yaml = None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zephyr-base", required=True)
    parser.add_argument("--modules", nargs="+", default=[])
    parser.add_argument("--board-dirs", nargs="+", default=[])
    parser.add_argument("--oot-dts-roots", nargs="+", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--jobs", "-j", type=int, default=None, help="Number of parallel processes to use for parsing")
    return parser.parse_args()


def find_soc_source_directories(zephyr_base, modules=None, *, tracker):
    soc_roots = [Path(zephyr_base)] + ([Path(m) for m in modules] if modules else [])
    result = []
    for root in soc_roots:
        soc_path = root / "soc"
        if soc_path.is_dir():
            for dirpath, dirs, filenames in kconfig_utils.filtered_walk(soc_path, tracker=tracker):
                if "soc.yml" in filenames:
                    result.append(dirpath)
        else:
            tracker.add(str(soc_path))
    return result


def find_board_source_directories(board_roots, tracker):
    result = []
    for root in board_roots:
        root_path = Path(root)
        if not root_path.exists():
            tracker.add(root)
            continue
        for dirpath, dirs, filenames in kconfig_utils.filtered_walk(root, tracker=tracker):
            if (
                "board.yml" in filenames
                or "Kconfig.board" in filenames
                or "board.Kconfig" in filenames
            ):
                result.append(dirpath)
    return sorted(set(result))


def get_soc_to_clusters(soc_dirs, tracker):
    """Parses soc.yml files to map SoC names to their clusters."""
    soc_to_clusters = {}
    if yaml is None:
        return soc_to_clusters

    for sdir in soc_dirs:
        soc_yml_path = os.path.join(sdir, "soc.yml")
        tracker.add(soc_yml_path)
        if os.path.exists(soc_yml_path):
            try:
                with open(soc_yml_path, "r") as f:
                    content = yaml.load(f, Loader=SafeLoader)

                    def find_socs(node):
                        if isinstance(node, dict):
                            if "socs" in node:
                                for soc in node["socs"]:
                                    sn = soc.get("name")
                                    if sn:
                                        if sn not in soc_to_clusters:
                                            soc_to_clusters[sn] = []
                                        if "cpuclusters" in soc:
                                            for cluster in soc["cpuclusters"]:
                                                cn = cluster.get("name")
                                                if cn and cn not in soc_to_clusters[sn]:
                                                    soc_to_clusters[sn].append(cn)
                            for v in node.values():
                                find_socs(v)
                        elif isinstance(node, list):
                            for item in node:
                                find_socs(item)

                    find_socs(content)
            except Exception as e:
                raise Exception("DEBUG: Failed to parse %s: %s" % (soc_yml_path, e))
    return soc_to_clusters


def discover_board_variants(board_dirs, soc_to_clusters, symbols, tracker):
    """Discovers board and SoC variants from board.yml files using YAML parsing."""
    if yaml is None:
        return

    for bdir in board_dirs:
        for bfile in ["board.yml", "board.yaml"]:
            bpath = os.path.join(bdir, bfile)
            tracker.add(bpath)
            if os.path.exists(bpath):
                try:
                    with open(bpath, "r") as f:
                        content = yaml.load(f, Loader=SafeLoader)

                    if not content:
                        continue

                    # Handle both 'board' (singular) and 'boards' (plural) formats
                    boards = []
                    if isinstance(content.get("board"), dict):
                        boards.append(content["board"])
                    if isinstance(content.get("boards"), list):
                        boards.extend(content["boards"])

                    for board in boards:
                        b_name = board.get("name", "").upper()
                        if not b_name:
                            continue

                        socs = board.get("socs", [])
                        if not isinstance(socs, list):
                            continue

                        for soc in socs:
                            sn_raw = soc.get("name")
                            if not sn_raw:
                                continue

                            sn_upper = sn_raw.upper()
                            base_name = (
                                "CONFIG_BOARD_"
                                + kconfig_utils.sanitize_name_for_target(b_name)
                                + "_"
                                + kconfig_utils.sanitize_name_for_target(sn_upper)
                            )
                            if base_name not in symbols:
                                symbols[base_name] = "bool"

                            # Add board/soc variants from board.yml
                            variants = soc.get("variants", [])
                            if isinstance(variants, list):
                                for var in variants:
                                    vn_raw = var.get("name")
                                    if vn_raw:
                                        vn_upper = vn_raw.upper()
                                        var_name = (
                                            base_name
                                            + "_"
                                            + kconfig_utils.sanitize_name_for_target(
                                                vn_upper
                                            )
                                        )
                                        if var_name not in symbols:
                                            symbols[var_name] = "bool"

                            if "CONFIG_BOARD_REVISION" not in symbols:
                                symbols["CONFIG_BOARD_REVISION"] = "string"

                            for rn_raw in discovery_utils.extract_board_revisions(board):
                                rn_upper = kconfig_utils.sanitize_name_for_target(rn_raw.upper())
                                board_rev_name = (
                                    "CONFIG_BOARD_"
                                    + kconfig_utils.sanitize_name_for_target(b_name)
                                    + "_"
                                    + rn_upper
                                )
                                if board_rev_name not in symbols:
                                    symbols[board_rev_name] = "bool"

                                soc_rev_name = base_name + "_" + rn_upper
                                if soc_rev_name not in symbols:
                                    symbols[soc_rev_name] = "bool"

                                if sn_raw in soc_to_clusters:
                                    for cn in soc_to_clusters[sn_raw]:
                                        full_name = (
                                            base_name
                                            + "_"
                                            + kconfig_utils.sanitize_name_for_target(cn.upper())
                                            + "_"
                                            + rn_upper
                                        )
                                        if full_name not in symbols:
                                            symbols[full_name] = "bool"

                            # Add cluster variants
                            if sn_raw in soc_to_clusters:
                                for cn in soc_to_clusters[sn_raw]:
                                    full_name = (
                                        base_name
                                        + "_"
                                        + kconfig_utils.sanitize_name_for_target(
                                            cn.upper()
                                        )
                                    )
                                    if full_name not in symbols:
                                        symbols[full_name] = "bool"
                except Exception as e:
                    raise Exception("DEBUG: Failed to parse %s: %s" % (bpath, e))


def setup_kconfig_environment(zephyr_base, tmp_dir, modules=None):
    """Sets up environment variables required for Kconfig parsing."""
    kconfig_utils.sanitize_host_env()
    os.environ["ZEPHYR_BASE"] = zephyr_base
    os.environ["srctree"] = zephyr_base
    os.environ["KCONFIG_BINARY_DIR"] = tmp_dir
    os.environ["CMAKE_BINARY_DIR"] = tmp_dir
    os.environ["APPLICATION_SOURCE_DIR"] = tmp_dir
    os.environ["ARCH_DIR"] = "arch"
    os.environ["SOC_DIR"] = "soc"
    os.environ["BOARD_DIR"] = "boards"
    os.environ["KCONFIG_BOARD_DIR"] = tmp_dir
    os.environ["HWM_SCHEME"] = "v2"
    os.environ["KCONFIG_FUNCTIONS"] = "kconfigfunctions"
    os.environ["TOOLCHAIN_HAS_PICOLIBC"] = "y"
    os.environ["TOOLCHAIN_HAS_NEWLIB"] = "y"
    os.environ["ZEPHYR_TOOLCHAIN_VARIANT"] = "zephyr"

    kconfig_env_file = os.path.join(tmp_dir, "kconfig_module_dirs.env")
    os.makedirs(tmp_dir, exist_ok=True)
    with open(kconfig_env_file, "w") as f:
        if modules:
            for m in modules:
                if os.path.isdir(m):
                    module_name = (
                        os.path.basename(m.rstrip("/"))
                        .split("+")[-1]
                        .replace("-", "_")
                        .upper()
                    )
                    m_abs = os.path.abspath(m)
                    f.write(f"ZEPHYR_{module_name}_MODULE_DIR={m_abs}\n")
                    os.environ[f"ZEPHYR_{module_name}_MODULE_DIR"] = m_abs
    os.environ["KCONFIG_ENV_FILE"] = kconfig_env_file


def generate_kconfig_scaffolding(
    tmp_dir, zephyr_base, soc_dirs, board_dirs, modules, oot_dts_roots=[], tracker=None
):
    """Generates the necessary Kconfig tree scaffolding for super-schema parsing.

    If 'tracker' (a kconfig_utils.InputRecorder) is given, the inputs of the
    generated files are recorded.
    """
    os.makedirs(tmp_dir, exist_ok=True)

    # Generate aggregation files
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "soc", "Kconfig.defconfig"), soc_dirs, "SoC defconfigs", tracker=tracker
    )
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "soc", "Kconfig"), soc_dirs, "SoC Kconfigs", tracker=tracker
    )
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "soc", "Kconfig.soc"), soc_dirs, "SoC Kconfigs", tracker=tracker
    )
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "soc", "Kconfig.sysbuild"),
        soc_dirs,
        "SoC sysbuild Kconfigs",
        tracker=tracker,
    )

    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "boards", "Kconfig.defconfig"),
        board_dirs,
        "Board defconfigs",
        tracker=tracker,
    )
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "boards", "Kconfig"), board_dirs, "Board Kconfigs", True, tracker=tracker
    )
    kconfig_utils.generate_aggregation_file(
        os.path.join(tmp_dir, "boards", "Kconfig.sysbuild"),
        board_dirs,
        "Board sysbuild Kconfigs",
        tracker=tracker,
    )

    # Mock arch Kconfig (Kconfig.zephyr sources it but we'll loop over archs)
    os.makedirs(os.path.join(tmp_dir, "arch"), exist_ok=True)
    with open(os.path.join(tmp_dir, "arch", "Kconfig"), "w") as f:
        f.write("# Placeholder\n")

    kconfig_modules = os.path.join(tmp_dir, "Kconfig.modules")
    kconfig_utils.generate_kconfig_modules(zephyr_base, modules, kconfig_modules, tracker=tracker)

    dts_roots = (
        [Path(zephyr_base)]
        + [Path(m) for m in modules]
        + [Path(r) for r in oot_dts_roots]
    )
    kconfig_utils.generate_kconfig_dts(
        zephyr_base, os.path.join(tmp_dir, "Kconfig.dts"), dts_roots, tracker=tracker
    )

    # Mock currently unsupported parts of the Kconfig tree
    for f_name in [
        "Kconfig.defconfig",
        "Kconfig.board",
        "Kconfig.sysbuild.modules",
        "Kconfig.shield",
        "Kconfig.shield.defconfig",
    ]:
        with open(os.path.join(tmp_dir, f_name), "w") as f:
            f.write("# Dummy\n")


def parse_arch_symbols(
    arch, zephyr_base, global_tmp_dir, modules, soc_dirs, board_dirs, oot_dts_roots
):
    """Parses Kconfig for a single architecture in a separate process.

    Returns (arch, symbols, warnings, parsed Kconfig files, inputs), where
    'inputs' is a kconfig_utils.InputRecorder snapshot of everything this parse
    depended on.
    """
    kconfig_dir = os.path.join(zephyr_base, "scripts", "kconfig")
    if kconfig_dir not in sys.path:
        sys.path.insert(0, kconfig_dir)
    import kconfiglib

    arch_tmp_dir = os.path.join(global_tmp_dir, "archs", arch)
    deps = kconfig_utils.InputRecorder()

    # Scaffolding must be arch-specific to avoid conflicts during parallel execution
    setup_kconfig_environment(zephyr_base, arch_tmp_dir, modules)
    generate_kconfig_scaffolding(
        arch_tmp_dir, zephyr_base, soc_dirs, board_dirs, modules, oot_dts_roots, tracker=deps
    )

    symbols = {}
    warnings_list = []
    parsed_files = set()

    try:
        os.environ["ARCH"] = arch
        os.environ["ARCH_DIR"] = "arch"
        os.environ["SOC_DIR"] = "soc"
        os.environ["BOARD"] = "generic"
        os.environ["BOARD_QUALIFIERS"] = ""
        os.environ["SOC_NAME"] = "none"
        os.environ["BOARD_DIR"] = arch_tmp_dir
        os.environ["KCONFIG_BOARD_DIR"] = arch_tmp_dir

        # Update arch/Kconfig mock to source the real arch Kconfig
        with open(os.path.join(arch_tmp_dir, "arch", "Kconfig"), "w") as f:
            arch_kconfig = os.path.join(zephyr_base, "arch", arch, "Kconfig")
            deps.add(arch_kconfig)
            if os.path.exists(arch_kconfig):
                f.write('source "%s"\n' % arch_kconfig)

        toolchain_arch = (
            "host" if arch == "posix" else "gnuarmemb" if arch == "arm" else "zephyr"
        )
        toolchain_kconfig_dir = os.path.join(
            zephyr_base, "cmake", "toolchain", toolchain_arch
        )
        if not os.path.exists(toolchain_kconfig_dir):
            # Creating it would switch TOOLCHAIN_KCONFIG_DIR.
            deps.add(toolchain_kconfig_dir)
            toolchain_kconfig_dir = os.path.join(
                zephyr_base, "cmake", "toolchain", "zephyr"
            )
        os.environ["TOOLCHAIN_KCONFIG_DIR"] = toolchain_kconfig_dir

        kconf_path = os.path.join(zephyr_base, "Kconfig")
        deps.add(kconf_path)
        with kconfig_utils.record_kconfig_sources(kconfiglib, deps):
            kconf = kconfiglib.Kconfig(kconf_path, warn_to_stderr=False)
        if kconf.warnings:
            for warning in kconf.warnings:
                warnings_list.append(warning)

        for path in set(kconf.kconfig_filenames):
            joined = os.path.join(kconf.srctree, path)
            parsed_files.add(os.path.abspath(joined))
            parsed_files.add(os.path.realpath(joined))

        for name, sym in kconf.syms.items():
            if sym.type == kconfiglib.UNKNOWN:
                continue
            full_name = "CONFIG_" + kconfig_utils.sanitize_name_for_target(name)
            stype = "bool"
            if sym.type in [kconfiglib.INT, kconfiglib.HEX]:
                stype = "int"
            elif sym.type == kconfiglib.STRING:
                stype = "string"

            symbols[full_name] = stype
    except Exception as e:
        print("DEBUG: Exception parsing arch %s: %s" % (arch, e), file=sys.stderr)
        pass

    # kconfiglib, kconfigfunctions and this script's modules, as loaded here.
    deps.add_python_modules(
        os.path.join(zephyr_base, "scripts"), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return arch, symbols, warnings_list, parsed_files, deps.snapshot()


def parse_kconfig_authoritative(
    zephyr_base,
    tmp_dir,
    archs,
    modules,
    soc_dirs,
    board_dirs,
    oot_dts_roots,
    symbols,
    warnings_list,
    kconfig_files,
    jobs=None,
    tracker=None,
):
    """Uses kconfiglib to perform an authoritative parse for each architecture in parallel.

    If 'tracker' (a kconfig_utils.InputRecorder) is given, the inputs of every
    per-arch parse are merged into it.
    """
    if jobs == 1:
        results = [
            parse_arch_symbols(
                arch,
                zephyr_base,
                tmp_dir,
                modules,
                soc_dirs,
                board_dirs,
                oot_dts_roots,
            )
            for arch in archs
        ]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = [
                executor.submit(
                    parse_arch_symbols,
                    arch,
                    zephyr_base,
                    tmp_dir,
                    modules,
                    soc_dirs,
                    board_dirs,
                    oot_dts_roots,
                )
                for arch in archs
            ]
            results = [future.result() for future in futures]

    for arch, arch_symbols, arch_warnings, arch_kconfig_files, arch_inputs in results:
        warnings_list.extend(arch_warnings)
        kconfig_files.update(arch_kconfig_files)
        tracker.update(arch_inputs)
        for name, stype in arch_symbols.items():
            if name not in symbols or (stype != "bool" and symbols[name] == "bool"):
                symbols[name] = stype


def scan_files_for_dynamic_symbols(zephyr_base, board_dirs, modules, symbols, symbol_settings, kconfig_files, tracker):
    """Scans files for symbols that might not be visible in the static Kconfig tree.

    Every directory walked, missing search dir and file read is recorded in 'tracker'.
    """
    untyped_symbols = set()
    search_dirs = [zephyr_base] + list(board_dirs) + list(modules)
    for d in search_dirs:
        if not os.path.isdir(d):
            tracker.add(d)
            continue
        for root, dirs, files in kconfig_utils.filtered_walk(d, tracker=tracker):
            for fname in files:
                if fname == "Kconfig" or fname.startswith("Kconfig."):
                    fpath = os.path.join(root, fname)
                    kconfig_files.add(os.path.abspath(fpath))
                    kconfig_files.add(os.path.realpath(fpath))
                    tracker.add(fpath)
                    try:
                        with open(fpath, "r", errors="ignore") as f:
                            content = f.read()
                            # config/choice
                            for match in re.finditer(
                                r"^\s*(?:menu)?(?:config|choice)\s+([a-zA-Z0-9_.-]+)",
                                content,
                                re.MULTILINE,
                            ):
                                name = match.group(1)
                                if name == "MODULES":
                                    continue
                                full_name = (
                                    "CONFIG_"
                                    + kconfig_utils.sanitize_name_for_target(name)
                                )

                                # Look ahead for type
                                start = match.end()
                                next_match = re.search(
                                    r"^\s*(?:menu)?(?:config|choice)\s+",
                                    content[start:],
                                    re.MULTILINE,
                                    )
                                end = (
                                    start + next_match.start()
                                    if next_match
                                    else len(content)
                                )
                                block = content[start:end]

                                stype = None
                                if re.search(r"^\s*int\b", block, re.MULTILINE):
                                    stype = "int"
                                elif re.search(r"^\s*hex\b", block, re.MULTILINE):
                                    stype = "int"
                                elif re.search(r"^\s*string\b", block, re.MULTILINE):
                                    stype = "string"
                                elif re.search(r"^\s*bool\b", block, re.MULTILINE):
                                    stype = "bool"

                                if stype:
                                    if (
                                        full_name not in symbols
                                        or full_name in untyped_symbols
                                    ):
                                        symbols[full_name] = stype
                                        untyped_symbols.discard(full_name)
                                    elif symbols[full_name] != stype:
                                        symbols[full_name] = "string"
                                else:
                                    if full_name not in symbols:
                                        symbols[full_name] = "string"
                                        untyped_symbols.add(full_name)

                            # Logging Template expansion
                            if "subsys/logging/Kconfig.template.log_config" in content:
                                mod_match = re.search(
                                    r"module\s*=\s*([a-zA-Z0-9_]+)", content
                                )
                                if mod_match:
                                    mod_name = mod_match.group(1)
                                    for suffix in [
                                        "_LOG_LEVEL_OFF",
                                        "_LOG_LEVEL_ERR",
                                        "_LOG_LEVEL_WRN",
                                        "_LOG_LEVEL_INF",
                                        "_LOG_LEVEL_DBG",
                                        "_LOG_LEVEL_DEFAULT",
                                        "_LOG_LEVEL",
                                    ]:
                                        full_name = "CONFIG_" + mod_name + suffix
                                        if (
                                            full_name not in symbols
                                            or full_name in untyped_symbols
                                        ):
                                            symbols[full_name] = (
                                                "bool"
                                                if suffix != "_LOG_LEVEL"
                                                else "int"
                                            )
                                            untyped_symbols.discard(full_name)
                    except:
                        pass
                elif fname in ["BUILD.bazel", "BUILD"] or fname.endswith(".bzl") or fname.endswith(".BUILD"):
                    tracker.add(os.path.join(root, fname))
                    try:
                        with open(os.path.join(root, fname), "r", errors="ignore") as f:
                            content = f.read()
                            for match in re.finditer(
                                r"@zephyr_kconfig//:(CONFIG_[A-Za-z0-9_]+)(?:=([^\"\s,\]\)]+))?",
                                content,
                            ):
                                sym_name = match.group(1)
                                sym_val = match.group(2)
                                if sym_name not in symbols:
                                    if sym_val and (
                                        sym_val.isdigit() or sym_val.startswith("0x")
                                    ):
                                        symbols[sym_name] = "int"
                                    elif sym_val and sym_val not in ["true", "false"]:
                                        symbols[sym_name] = "string"
                                    else:
                                        symbols[sym_name] = "bool"
                                elif sym_val and (
                                    sym_val.isdigit() or sym_val.startswith("0x")
                                ):
                                    symbols[sym_name] = "int"

                                if sym_val:
                                    symbol_settings[sym_name].add(sym_val)
                    except:
                        pass


def write_bazel_build_file(output_file, symbols, symbol_settings):
    """Writes the discovered symbols into a BUILD.bazel file as Bazel flags."""
    with open(output_file, "w") as f:
        f.write(
            'load("@bazel_skylib//rules:common_settings.bzl", "bool_flag", "int_flag", "string_flag")\n'
        )
        f.write('load("@rules_cc//cc:defs.bzl", "cc_library")\n')
        f.write('load("@zephyr//bazel:cc.bzl", "zephyr_cc_library")\n\n')
        f.write('package(default_visibility = ["//visibility:public"])\n\n')
        f.write('exports_files(["local_modules.bzl"])\n\n')
        f.write("zephyr_cc_library(\n")
        f.write('    name = "kconfig_warnings",\n')
        f.write('    srcs = ["kconfig_warnings.c"],\n')
        f.write(")\n\n")

        for name in sorted(symbols.keys()):
            stype = symbols[name]
            if stype == "bool":
                f.write(
                    'bool_flag(name = "%s", build_setting_default = False)\n' % name
                )
                symbol_settings[name].add("true")
                symbol_settings[name].add("false")
            elif stype == "int":
                f.write('int_flag(name = "%s", build_setting_default = 0)\n' % name)
                symbol_settings[name].add("0")
            else:
                f.write('string_flag(name = "%s", build_setting_default = "")\n' % name)

            for val in sorted(symbol_settings[name]):
                f.write(
                    'config_setting(name = "%s=%s", flag_values = {":%s": "%s"})\n'
                    % (name, val, name, val)
                )


def main():
    args = parse_args()

    zephyr_base = os.path.abspath(args.zephyr_base)
    tmp_dir = os.path.abspath("kconfig_bin")
    symbols = {}
    symbol_settings = collections.defaultdict(set)
    kconfig_files = set()
    # Every input of this run, written to deps.txt and dep_dirs.txt.
    deps = kconfig_utils.InputRecorder()

    # 1. Discover all hardware
    soc_dirs = find_soc_source_directories(zephyr_base, tracker=deps, modules=args.modules)
    board_roots = [os.path.join(zephyr_base, "boards")] + args.board_dirs
    board_dirs = find_board_source_directories(board_roots, tracker=deps)

    soc_to_clusters = get_soc_to_clusters(soc_dirs, tracker=deps)
    discover_board_variants(board_dirs, soc_to_clusters, symbols, tracker=deps)

    arch_root = os.path.join(zephyr_base, "arch")
    deps.add_dir(arch_root)
    archs = [
        d for d in sorted(os.listdir(arch_root)) if os.path.isdir(os.path.join(arch_root, d))
    ]

    # 2. Setup environment
    setup_kconfig_environment(zephyr_base, tmp_dir, args.modules)

    # 3. Authoritative Parse using kconfiglib (parallelized)
    all_warnings = []
    parse_kconfig_authoritative(
        zephyr_base,
        tmp_dir,
        archs,
        args.modules,
        soc_dirs,
        board_dirs,
        args.oot_dts_roots,
        symbols,
        all_warnings,
        kconfig_files,
        jobs=args.jobs,
        tracker=deps,
    )

    # Generate kconfig_warnings.c
    output_dir = os.path.dirname(os.path.abspath(args.output))
    with open(os.path.join(output_dir, "kconfig_warnings.c"), "w") as f:
        f.write("/* AUTO-GENERATED by kconfig_gen_symbols.py, do not edit! */\n\n")
        if all_warnings:
            for warning in all_warnings:
                msg = warning.replace('"', '\\"').replace("\n", " ")
                f.write(f'#warning "Kconfig warning: {msg}"\n')
        else:
            f.write("/* No Kconfig warnings */\n")

    # 4. Fallback: Scan files for dynamic symbols
    scan_files_for_dynamic_symbols(
        zephyr_base, args.board_dirs, args.modules, symbols, symbol_settings, kconfig_files, tracker=deps
    )

    excluded_prefixes = (
        os.path.abspath(output_dir) + "/",
        os.path.realpath(output_dir) + "/",
        os.path.abspath(tmp_dir) + "/",
        os.path.realpath(tmp_dir) + "/",
    )
    excluded_exact = {
        os.path.abspath(output_dir),
        os.path.realpath(output_dir),
        os.path.abspath(tmp_dir),
        os.path.realpath(tmp_dir),
    }
    with open(os.path.join(output_dir, "kconfig_list.txt"), "w") as f:
        for path in sorted(kconfig_files):
            if path in excluded_exact or path.startswith(excluded_prefixes):
                continue
            f.write(path + "\n")

    # 5. Generate BUILD.bazel
    write_bazel_build_file(args.output, symbols, symbol_settings)

    # Python code that ran in this process; the per-arch parses reported theirs.
    deps.add_python_modules(os.path.join(zephyr_base, "scripts"), os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    deps.add(*kconfig_files)
    deps.write(output_dir=output_dir, exclude_dirs=[tmp_dir])


if __name__ == "__main__":
    main()
