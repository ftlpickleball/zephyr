# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Scans directories for Zephyr modules."""

import argparse
import json
import os
import re
import sys

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
    return parser.parse_args(argv)


def sanitize_name(name):
    return re.sub(r"[^a-zA-Z0-9]", "_", name)


def extract_apparent_name(canonical_name):
    """Extracts the apparent name from Bazel 8 canonical names.

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


def get_module_info(path):
    """Checks if path is a module, returns (sanitized name, kconfig) if it is."""
    module_yml = os.path.join(path, "zephyr", "module.yml")
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


def check_zephyr_module_target_in_build(build_file, target_name):
    """Checks if a BUILD.bazel file defines a zephyr_module target matching target_name.

    Modules with a BUILD.bazel containing a zephyr_module with a matching
    module name are autolinked, and all others are scan-only.
    """
    try:
        with open(build_file, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = r"\bname\s*=\s*[\"']" + re.escape(target_name) + r"[\"']"
        if re.search(pattern, content) and "zephyr_module" in content:
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

    discovered = []

    for label, info in modules_dirs.items():
        path = info["root"]
        package_dir = info["package_dir"]

        if not os.path.exists(path):
            continue

        # Check if the directory itself is a module
        name, kconfig = get_module_info(path)
        if name:
            build_file = os.path.join(package_dir, "BUILD.bazel")
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
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and not entry.name.startswith("."):
                    name, kconfig = get_module_info(entry.path)
                    if name:
                        build_file = os.path.join(entry.path, "BUILD.bazel")
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
        except Exception as e:
            print(f"Error scanning {path}: {e}", file=sys.stderr)

    print(json.dumps(discovered))


if __name__ == "__main__":
    main()
