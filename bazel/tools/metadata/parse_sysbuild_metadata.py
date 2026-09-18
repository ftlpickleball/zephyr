# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
import argparse
import collections
import glob
import hashlib
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
        "--apps-json",
        required=True,
        help="Path to input JSON containing discovered apps",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to output JSON file",
    )
    return parser.parse_args(argv)


def parse_sysbuild_yaml(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return None


def process_sysbuild_conf(file_path):
    fragments = collections.defaultdict(list)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Match global SB_CONFIG_ settings FIRST
                match = re.match(r"^SB_CONFIG_([a-zA-Z0-9_]+)=(.*)$", line)
                if match:
                    option = match.group(1)
                    value = match.group(2)

                    # Global SB_CONFIG_ options are generally for Sysbuild itself and
                    # ignored, except for specific settings that have hardcoded side-effects
                    # on the Kconfig of target images (like enabling MCUboot or its mode).
                    if option == "BOOTLOADER_MCUBOOT" and value == "y":
                        fragments["main"].append("CONFIG_BOOTLOADER_MCUBOOT=y")
                        fragments["mcuboot"].append(
                            "CONFIG_BOOTLOADER_MCUBOOT=y"
                        )
                    elif option.startswith("MCUBOOT_MODE_"):
                        translated_option = option.replace(
                            "MCUBOOT_MODE_", "CONFIG_MCUBOOT_BOOTLOADER_MODE_"
                        )
                        fragments["mcuboot"].append(
                            f"{translated_option}={value}"
                        )
                    continue

                # Match namespaced settings: domain_CONFIG_OPTION=value
                match = re.match(
                    r"^([a-zA-Z0-9_]+)_(CONFIG_[a-zA-Z0-9_]+)=(.*)$", line
                )
                if match:
                    domain = match.group(1)
                    setting = f"{match.group(2)}={match.group(3)}"
                    fragments[domain].append(setting)
                    continue
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)

    return {
        domain: "\n".join(settings) + "\n"
        for domain, settings in fragments.items()
    }


def get_app_hash(app_pkg):
    norm_app = app_pkg.lstrip("@").lstrip("/").lstrip(":")
    if ":" in norm_app:
        pkg, target = norm_app.split(":", 1)
        if pkg.endswith(target) or target == pkg.split("/")[-1]:
            norm_app = pkg
    h = hashlib.md5(norm_app.encode("utf-8")).hexdigest()[:8]
    return h


def sanitize_board_id(board_id):
    return board_id.replace("/", "_").replace("-", "_").replace(".", "_")


def main(argv=None):
    args = parse_args(argv)
    with open(args.apps_json, "r", encoding="utf-8") as f:
        apps = json.load(f)

    raw_metadata = {}
    translated_confs = {}

    for app_pkg, app_path in apps.items():
        app_graph = {"helpers": {}, "board_helpers": {}}

        global_file = os.path.join(app_path, "sysbuild.yml")
        if os.path.exists(global_file):
            content = parse_sysbuild_yaml(global_file)
            if content and "helpers" in content:
                helpers = {
                    k: (v if isinstance(v, dict) else {})
                    for k, v in content["helpers"].items()
                }
                top_cond = content.get("condition")
                if top_cond:
                    for h in helpers.values():
                        h.setdefault("condition", top_cond)
                app_graph["helpers"] = helpers

        boards_dir = os.path.join(app_path, "boards")
        if os.path.exists(boards_dir):
            pattern = os.path.join(boards_dir, "*.sysbuild.yml")
            for board_file in glob.glob(pattern):
                filename = os.path.basename(board_file)
                board_name = filename.replace(".sysbuild.yml", "")
                content = parse_sysbuild_yaml(board_file)
                if content and "helpers" in content:
                    helpers = {
                        k: (v if isinstance(v, dict) else {})
                        for k, v in content["helpers"].items()
                    }
                    top_cond = content.get("condition")
                    if top_cond:
                        for h in helpers.values():
                            h.setdefault("condition", top_cond)
                    app_graph["board_helpers"][board_name] = helpers

        if app_graph["helpers"] or app_graph["board_helpers"]:
            raw_metadata[app_pkg] = app_graph

        sysbuild_conf = os.path.join(app_path, "sysbuild.conf")
        if os.path.exists(sysbuild_conf):
            app_fragments = process_sysbuild_conf(sysbuild_conf)
            if app_fragments:
                translated_confs[app_pkg] = app_fragments

    repos_to_declare = []

    for app_pkg, app_path in apps.items():
        if app_pkg not in raw_metadata:
            continue

        app_graph = raw_metadata[app_pkg]
        app_fragments = translated_confs.get(app_pkg, {})

        boards = set(app_graph["board_helpers"].keys())
        if not boards:
            boards.add("default_board")

        for board_id in boards:
            helpers = {}
            helpers.update(app_graph["helpers"])
            helpers.update(app_graph["board_helpers"].get(board_id, {}))

            for helper_name, helper_config in helpers.items():
                helper_target = helper_config.get("target")
                if not helper_target:
                    continue

                if helper_config.get("type") == "external":
                    continue

                platform = helper_config.get("platform")
                if platform:
                    # Use helper's platform as board_id for repo naming
                    helper_board_id = (
                        platform.split(":")[-1]
                        if ":" in platform
                        else os.path.basename(platform)
                    )
                else:
                    helper_board_id = board_id

                rel_conf_fragment_path = os.path.join(
                    "sysbuild", f"{helper_name}.conf"
                )
                conf_fragment_path = os.path.join(
                    app_path, rel_conf_fragment_path
                )
                has_conf_fragment = os.path.exists(conf_fragment_path)

                helper_fragment = app_fragments.get(helper_name, "")

                if has_conf_fragment or helper_fragment:
                    path_str = f"{app_pkg}->{helper_name}"
                    path_hash = hashlib.md5(
                        path_str.encode("utf-8")
                    ).hexdigest()[:8]
                    safe_board = sanitize_board_id(helper_board_id)
                    repo_name = f"zc_{path_hash}_{safe_board}"

                    conf_fragments = []
                    if has_conf_fragment:
                        conf_fragments.append(rel_conf_fragment_path)

                    repos_to_declare.append({
                        "name": repo_name,
                        "app_label": helper_target,
                        "board_id": helper_board_id,  # Use helper's board ID
                        "conf_fragments": conf_fragments,
                        "extra_kconfig": helper_fragment,
                        "parent_app": app_pkg,
                        "helper_name": helper_name,
                    })

    results = {
        "raw_metadata": raw_metadata,
        "custom_repos": repos_to_declare,
        "translated_confs": translated_confs,
    }

    # Dump final JSON mapping to output file.
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f)


if __name__ == "__main__":
    main()
