# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
import fnmatch
import glob
import os
import sys
import subprocess
from pathlib import Path

from input_recorder import DEPS_FILE, DEP_DIRS_FILE, InputRecorder  # noqa: F401

_EXCLUDED_DIR_NAMES = {".git"}

# File suffixes edtlib and gen_driver_kconfig_dts.py load from bindings dirs.
BINDING_SUFFIXES = (".yaml", ".yml")


def glob_dependencies(pattern):
    """Returns (dirs, paths) that determine the result of glob.glob(pattern).

    'dirs' are the directories listed to expand wildcard components. 'paths'
    are the paths whose existence decides the result: the pattern itself when
    it has no wildcards (e.g. an 'osource' of an optional file), the literal
    tails of wildcard matches (e.g. <dir>/<subdir>/Kconfig for "*/Kconfig",
    whether or not they exist), and missing directories below which matches
    could appear.
    """
    if not glob.has_magic(pattern):
        return set(), {pattern}
    if not os.path.isabs(pattern):
        pattern = os.path.join(os.getcwd(), pattern)
    dirs, paths = set(), set()
    parts = pattern.split(os.sep)
    bases = [os.sep]
    for i, part in enumerate(parts):
        if not part:
            continue
        if not glob.has_magic(part):
            bases = [os.path.join(b, part) for b in bases]
            continue
        last = i == len(parts) - 1
        matches = []
        for base in bases:
            if not os.path.isdir(base):
                paths.add(base)
                continue
            dirs.add(base)
            try:
                names = os.listdir(base)
            except OSError:
                continue
            if not part.startswith("."):
                # glob skips hidden entries unless the pattern asks for them.
                names = [n for n in names if not n.startswith(".")]
            for name in fnmatch.filter(names, part):
                match = os.path.join(base, name)
                if last or os.path.isdir(match):
                    matches.append(match)
        bases = matches
    paths.update(bases)
    return dirs, paths


@contextlib.contextmanager
def record_kconfig_sources(kconfiglib_module, tracker):
    """Records every 'source' pattern kconfiglib expands while parsing.

    kconfiglib resolves (o|r|or)source statements with a module-level iglob().
    Wrapping it captures, after macro expansion, the directories listed for
    wildcard patterns and the probed paths of optional sources that do not
    exist, neither of which shows up in Kconfig.kconfig_filenames.
    """
    original = getattr(kconfiglib_module, "iglob", None)
    if original is None:
        yield
        return

    def recording_iglob(pattern, *args, **kwargs):
        dirs, paths = glob_dependencies(pattern)
        tracker.add_dir(*dirs)
        tracker.add(*paths)
        return original(pattern, *args, **kwargs)

    kconfiglib_module.iglob = recording_iglob
    try:
        yield
    finally:
        kconfiglib_module.iglob = original


def dts_python_sources(zephyr_base):
    """Returns the modules imported by scripts/dts/gen_edt.py and gen_defines.py:
    edtlib_logger.py and the python-devicetree package."""
    dts_dir = os.path.join(zephyr_base, "scripts", "dts")
    package_dir = os.path.join(dts_dir, "python-devicetree", "src", "devicetree")
    return [os.path.join(dts_dir, "edtlib_logger.py")] + sorted(glob.glob(os.path.join(package_dir, "*.py")))


def sanitize_name_for_target(name):
    """Consistently sanitize for Bazel target names."""
    return name.replace("-", "_").replace(".", "_").replace("(", "_").replace(")", "_").replace("$", "_").replace('"', "").replace("'", "")

def generate_aggregation_file(output_file, dirs, comment, include_wildcard = False, tracker = None):
    """Generates a Kconfig file that sources other Kconfig files in the given directories.

    Records the probed candidates (existing or not) and, with 'include_wildcard',
    the listed directories into 'tracker'.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(f'# Load {comment} descriptions.\n\n')
        for entry in sorted(dirs):
            base_file = os.path.basename(output_file)
            candidate = os.path.join(entry, base_file)
            if tracker is not None:
                tracker.add(candidate)
            if os.path.exists(candidate):
                f.write(f'osource "{os.path.abspath(candidate)}"\n')
            if include_wildcard and os.path.isdir(entry):
                if tracker is not None:
                    tracker.add_dir(entry)
                for fname in sorted(os.listdir(entry)):
                    if fname.startswith(base_file + ".") and fname not in [base_file + ".defconfig", base_file + ".sysbuild", base_file + ".shield"]:
                        f.write(f'osource "{os.path.abspath(os.path.join(entry, fname))}"\n')

def generate_kconfig_modules(zephyr_base, extra_modules, output_file, tracker = None):
    """Generates Kconfig.modules including everything in zephyr/modules/ and extra_modules.

    Records the files read and the candidates probed into 'tracker'.
    """
    modules_dir = os.path.join(zephyr_base, "modules")
    with open(output_file, "w") as f:
        if os.path.isdir(modules_dir):
            if tracker is not None:
                tracker.add_dir(modules_dir)
            for entry in sorted(os.listdir(modules_dir)):
                d = os.path.join(modules_dir, entry)
                if not os.path.isdir(d):
                    continue
                module_name = entry.replace('-', '_').upper()
                for k in ["zephyr/Kconfig", "Kconfig"]:
                    kpath = os.path.join(d, k)
                    if tracker is not None:
                        tracker.add(kpath)
                    if os.path.exists(kpath):
                        f.write(f'osource "{os.path.abspath(kpath)}"\n')
                        break
                f.write(f"""config ZEPHYR_{module_name}_MODULE
    bool
    default y
""")
        elif tracker is not None:
            tracker.add(modules_dir)

        for m in sorted(extra_modules):
            if not os.path.isdir(m):
                if tracker is not None:
                    tracker.add(m)
                continue
            module_name = os.path.basename(m.rstrip('/')).split('+')[-1].replace('-', '_').upper()
            k_candidates = []
            module_yml = os.path.join(m, "zephyr", "module.yml")
            if tracker is not None:
                tracker.add(module_yml)
            if os.path.exists(module_yml):
                try:
                    import yaml
                    with open(module_yml, "r", encoding="utf-8") as yf:
                        ydata = yaml.safe_load(yf)
                        if isinstance(ydata, dict):
                            build_cfg = ydata.get("build")
                            if isinstance(build_cfg, dict) and build_cfg.get("kconfig"):
                                k_candidates.append(build_cfg.get("kconfig"))
                except Exception:
                    pass
            for k in ["zephyr/Kconfig", "Kconfig", "Kconfig.zephyr"]:
                if k not in k_candidates:
                    k_candidates.append(k)
            for k in k_candidates:
                kpath = os.path.join(m, k)
                if tracker is not None:
                    tracker.add(kpath)
                if os.path.exists(kpath):
                    f.write(f'osource "{os.path.abspath(kpath)}"\n')
                    break
            if 'PIGWEED' not in module_name:
                # Pigweed already defines config ZEPHYR_PIGWEED_MODULE.
                f.write(f"""config ZEPHYR_{module_name}_MODULE
    bool
    default y
""")

def sanitize_host_env(env=None):
    """Strips host Kconfig/Zephyr/Python environment variables and pins UTF-8/hash seed."""
    target = os.environ if env is None else env
    for key in list(target.keys()):
        if (
            key.startswith(("KCONFIG_", "ZEPHYR_", "CONFIG_"))
            or key in ("PYTHONSTARTUP", "PYTHONUSERBASE")
        ):
            del target[key]
    target["PYTHONDONTWRITEBYTECODE"] = "1"
    target["PYTHONNOUSERSITE"] = "1"
    target["PYTHONHASHSEED"] = "0"
    target["PYTHONUTF8"] = "1"
    return target


def generate_kconfig_dts(zephyr_base, output_file, dts_roots, tracker = None):
    """Generates Kconfig.dts from DT bindings.

    Records the script, every binding file and directory it walks, and missing
    bindings dir candidates into 'tracker'.
    """
    bindings_dirs = []
    for dts_root in dts_roots:
        for b in ["zephyr/dts/bindings", "dts/bindings"]:
            bdir = Path(dts_root) / b
            if bdir.exists():
                bindings_dirs.append(str(bdir.resolve()))
                break # Only use the first one found
            elif tracker is not None:
                tracker.add(str(bdir))

    gen_driver_kconfig_dts_py = os.path.join(zephyr_base, "scripts", "dts", "gen_driver_kconfig_dts.py")
    cmd = [
        sys.executable,
        "-B",
        "-s",
        gen_driver_kconfig_dts_py,
        "--kconfig-out", output_file,
        "--bindings-dirs"
    ] + bindings_dirs

    env = os.environ.copy()
    # Ensure kconfiglib is available for the script without trailing empty path entries
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [os.path.join(zephyr_base, "scripts", "kconfig"), env.get("PYTHONPATH", "")] if p
    )

    if tracker is not None:
        tracker.add(gen_driver_kconfig_dts_py)
        for bdir in bindings_dirs:
            tracker.add_tree(bdir, BINDING_SUFFIXES)

    subprocess.run(cmd, env=env, check=True)


def filtered_walk(top, tracker = None, followlinks=False):
    """A wrapper around os.walk that filters out standard VCS directories.

    Every visited directory is recorded in 'tracker' if provided.
    """
    for root, dirs, files in os.walk(top, topdown=True, followlinks=followlinks):
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_DIR_NAMES)
        files.sort()
        if tracker is not None:
            tracker.add_dir(root)
        yield root, dirs, files
