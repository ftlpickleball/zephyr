# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Scans directories for Zephyr modules."""

import argparse
import ast
import json
import os
import re
import sys

import input_recorder

try:
    import yaml
except ImportError:
    print("PyYAML is required but not found.", file=sys.stderr)
    sys.exit(1)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modules-dirs-json",
        required=True,
        help="JSON string mapping modules_dirs labels to absolute paths",
    )
    input_recorder.add_arguments(parser)
    return parser.parse_args(argv)


def sanitize_name(name):
    return re.sub(r"[^a-zA-Z0-9]", "_", name)


def extract_apparent_name(canonical_name):
    """Extracts the apparent name from Bazel 8+ canonical names.

    Examples:
        - "rules_python~1.8.3" -> "rules_python"
        - "zephyr-bazel++zephyr_setup+zephyr_kconfig" -> "zephyr_kconfig"
        - "+_repo_rules+hal_atmel" -> "hal_atmel"
    """
    if "~" in canonical_name:
        parts = canonical_name.split("~")
        if not parts[0]:
            raise ValueError(
                f"Invalid canonical name (starts with '~'): '{canonical_name}'"
            )
        return parts[0]

    if "+" in canonical_name:
        parts = canonical_name.split("+")

        # Check for "module+version" or "module+" format (Bazel 8 module names)
        if len(parts) == 2 and parts[0]:
            return parts[0]

        # Check for "owner++extension+repo" format
        if "" in parts:
            if len(parts) >= 2 and parts[1] == "":
                if len(parts) < 4:
                    raise ValueError(
                        "Invalid canonical name (expected "
                        f"'owner++extension+repo'): '{canonical_name}'"
                    )
                if not parts[3]:
                    raise ValueError(
                        "Invalid canonical name (empty repo name in "
                        f"'owner++extension+repo'): '{canonical_name}'"
                    )
                return parts[3]

        # Check for "+_repo_rules+repo" or "+extension+repo" format
        if parts[0] == "":
            if len(parts) >= 2 and parts[1] == "_repo_rules":
                if len(parts) < 3:
                    raise ValueError(
                        "Invalid canonical name (expected "
                        f"'+_repo_rules+repo'): '{canonical_name}'"
                    )
                if not parts[2]:
                    raise ValueError(
                        "Invalid canonical name (empty repo name in "
                        f"'+_repo_rules+repo'): '{canonical_name}'"
                    )
                return parts[2]
            else:
                # General "+extension+repo" format
                if len(parts) >= 3:
                    if not parts[2]:
                        raise ValueError(
                            "Invalid canonical name (empty repo name in "
                            f"'+extension+repo'): '{canonical_name}'"
                        )
                    return parts[2]
                raise ValueError(
                    "Invalid canonical name (starts with '+' but unknown "
                    f"format): '{canonical_name}'"
                )

    return canonical_name


def get_module_info(path, deps):
    """Checks if path is a module, returns (sanitized name, kconfig) if it is."""
    module_yml = os.path.join(path, "zephyr", "module.yml")
    # Read if present; creating it would turn `path` into a module.
    deps.add_file(module_yml)
    if not os.path.exists(module_yml):
        return None, None

    name = extract_apparent_name(os.path.basename(path))
    kconfig = None
    try:
        with open(module_yml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and isinstance(data, dict):
                name = data.get("name", name)
                build_cfg = data.get("build")
                if isinstance(build_cfg, dict):
                    kconfig = build_cfg.get("kconfig")
    except Exception as e:
        print(
            f"Warning: failed to parse {module_yml}: {e}", file=sys.stderr
        )

    return sanitize_name(name), kconfig


# Known non-module rules and macros. Modules whose BUILD.bazel only defines
# `<module_name>` using one of these rules are scan-only (Kconfig/DTS only,
# linked via explicit `deps`), whereas `zephyr_module` and custom wrapper
# macros that delegate to `zephyr_module` emit `<name>._zephyr_module` and are
# autolinked via `@zephyr_index//:local_modules`.
_NON_MODULE_RULES = frozenset(
    {
        "alias",
        "cc_binary",
        "cc_import",
        "cc_library",
        "cc_shared_library",
        "cc_test",
        "config_setting",
        "config_setting_group",
        "exports_files",
        "filegroup",
        "genrule",
        "label_flag",
        "label_setting",
        "package",
        "py_binary",
        "py_library",
        "py_test",
        "rust_binary",
        "rust_library",
        "rust_proc_macro",
        "rust_shared_library",
        "rust_static_library",
        "rust_test",
        "sh_binary",
        "sh_library",
        "sh_test",
        "zephyr_app",
        "zephyr_cc_binary",
        "zephyr_cc_library",
        "zephyr_constants_library",
        "zephyr_freestanding_library",
        "zephyr_linker_fragment",
        "zephyr_llext_inc_target",
        "zephyr_soc_library",
        "zephyr_sysbuild",
        "zephyr_unit_test",
        "ztest",
    }
)


def _has_scan_only_tag(call_node):
    """Returns True if `call_node` passes `tags = [..., "zephyr_scan_only", ...]`."""
    for kw in call_node.keywords:
        if kw.arg == "tags" and isinstance(kw.value, (ast.List, ast.Tuple)):
            for elt in kw.value.elts:
                if (
                    isinstance(elt, ast.Constant)
                    and elt.value == "zephyr_scan_only"
                ):
                    return True
    return False


def check_zephyr_module_target_in_build(build_file, target_name):
    """Checks if a BUILD.bazel file defines a module target matching target_name.

    Modules with a BUILD.bazel containing `zephyr_module` (or a custom wrapper
    macro delegating to `zephyr_module`, verified at analysis time via the
    `:<name>._zephyr_module` marker alias) with a matching module name are
    autolinked, and all others are scan-only.
    """
    try:
        with open(build_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=build_file)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if not func_name or func_name in _NON_MODULE_RULES:
                continue
            if _has_scan_only_tag(node):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == target_name
                ):
                    return True
    except Exception as e:
        print(f"Warning: failed to read {build_file}: {e}", file=sys.stderr)
    return False


def main(argv=None):
    args = parse_args(argv)

    try:
        modules_dirs = json.loads(args.modules_dirs_json)
    except Exception as e:
        print(f"Error parsing modules-dirs-json: {e}", file=sys.stderr)
        sys.exit(1)

    deps = input_recorder.InputRecorder(__file__)

    discovered = []

    for label, info in modules_dirs.items():
        path = info["root"]
        package_dir = info["package_dir"]

        if not os.path.exists(path):
            deps.add_file(path)
            continue

        # Check if the directory itself is a module
        name, kconfig = get_module_info(path, deps)
        if name:
            build_file = os.path.join(package_dir, "BUILD.bazel")
            deps.add_file(build_file)
            has_zephyr_module_target_in_build = os.path.exists(build_file) and check_zephyr_module_target_in_build(build_file, name)
            discovered.append(
                {
                    "modules_dir_label": label,
                    "relpath": "",
                    "name": name,
                    "abs_path": path,
                    "has_zephyr_module_target_in_build": has_zephyr_module_target_in_build,
                    "kconfig": kconfig,
                }
            )
            continue

        # Otherwise scan subdirectories (depth 1)
        if os.path.isdir(path):
            deps.add_dir(path)
        else:
            deps.add_file(path)
        try:
            for entry in sorted(os.scandir(path), key=lambda e: e.name):
                if entry.is_dir() and not entry.name.startswith("."):
                    name, kconfig = get_module_info(entry.path, deps)
                    if name:
                        build_file = os.path.join(entry.path, "BUILD.bazel")
                        deps.add_file(build_file)
                        has_zephyr_module_target_in_build = os.path.exists(build_file) and check_zephyr_module_target_in_build(build_file, name)
                        discovered.append(
                            {
                                "modules_dir_label": label,
                                "relpath": entry.name,
                                "name": name,
                                "abs_path": entry.path,
                                "has_zephyr_module_target_in_build": has_zephyr_module_target_in_build,
                                "kconfig": kconfig,
                            }
                        )
                elif entry.is_symlink() and not entry.name.startswith("."):
                    # DirectoryListingStateValue records (name, Dirent.Type), so
                    # a regular file turning into a directory changes the
                    # listing of `path`, whereas a dangling symlink turning into
                    # a module directory does not.
                    deps.add_file(
                        os.path.join(entry.path, "zephyr", "module.yml")
                    )
        except Exception as e:
            print(f"Error scanning {path}: {e}", file=sys.stderr)

    print(json.dumps(discovered))

    deps.write(args.deps_out, args.dirs_out)


if __name__ == "__main__":
    main()
