# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import subprocess
from pathlib import Path

_EXCLUDED_DIR_NAMES = {".git"}


def sanitize_name_for_target(name):
    """Consistently sanitize for Bazel target names."""
    return name.replace("-", "_").replace(".", "_").replace("(", "_").replace(")", "_").replace("$", "_").replace('"', "").replace("'", "")

def generate_aggregation_file(output_file, dirs, comment, include_wildcard = False):
    """Generates a Kconfig file that sources other Kconfig files in the given directories."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(f'# Load {comment} descriptions.\n\n')
        for entry in sorted(dirs):
            base_file = os.path.basename(output_file)
            candidate = os.path.join(entry, base_file)
            if os.path.exists(candidate):
                f.write(f'osource "{os.path.abspath(candidate)}"\n')
            if include_wildcard and os.path.isdir(entry):
                for fname in sorted(os.listdir(entry)):
                    if fname.startswith(base_file + ".") and fname not in [base_file + ".defconfig", base_file + ".sysbuild", base_file + ".shield"]:
                        f.write(f'osource "{os.path.abspath(os.path.join(entry, fname))}"\n')

def generate_kconfig_modules(zephyr_base, extra_modules, output_file):
    """Generates Kconfig.modules including everything in zephyr/modules/ and extra_modules."""
    modules_dir = os.path.join(zephyr_base, "modules")
    with open(output_file, "w") as f:
        if os.path.isdir(modules_dir):
            for entry in sorted(os.listdir(modules_dir)):
                d = os.path.join(modules_dir, entry)
                if not os.path.isdir(d):
                    continue
                module_name = entry.replace('-', '_').upper()
                for k in ["zephyr/Kconfig", "Kconfig"]:
                    kpath = os.path.join(d, k)
                    if os.path.exists(kpath):
                        f.write(f'osource "{os.path.abspath(kpath)}"\n')
                        break
                f.write(f"""config ZEPHYR_{module_name}_MODULE
    bool
    default y
""")

        for m in sorted(extra_modules):
            if not os.path.isdir(m):
                continue
            module_name = os.path.basename(m.rstrip('/')).split('+')[-1].replace('-', '_').upper()
            for k in ["zephyr/Kconfig", "Kconfig", "Kconfig.zephyr"]:
                kpath = os.path.join(m, k)
                if os.path.exists(kpath):
                    f.write(f'osource "{os.path.abspath(kpath)}"\n')
                    break
            if 'PIGWEED' not in module_name:
                # Pigweed already defines config ZEPHYR_PIGWEED_MODULE.
                f.write(f"""config ZEPHYR_{module_name}_MODULE
    bool
    default y
""")

def generate_kconfig_dts(zephyr_base, output_file, dts_roots):
    """Generates Kconfig.dts from DT bindings."""
    bindings_dirs = []
    for dts_root in dts_roots:
        for b in ["zephyr/dts/bindings", "dts/bindings"]:
            bdir = Path(dts_root) / b
            if bdir.exists():
                bindings_dirs.append(str(bdir.resolve()))
                break # Only use the first one found

    cmd = [
        sys.executable,
        os.path.join(zephyr_base, "scripts", "dts", "gen_driver_kconfig_dts.py"),
        "--kconfig-out", output_file,
        "--bindings-dirs"
    ] + bindings_dirs

    env = os.environ.copy()
    # Ensure kconfiglib is available for the script
    env["PYTHONPATH"] = os.path.join(zephyr_base, "scripts", "kconfig") + ":" + env.get("PYTHONPATH", "")

    subprocess.run(cmd, env=env, check=True)


def filtered_walk(top, followlinks=False):
    """A wrapper around os.walk that filters out standard VCS directories."""
    for root, dirs, files in os.walk(top, topdown=True, followlinks=followlinks):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIR_NAMES]
        yield root, dirs, files

