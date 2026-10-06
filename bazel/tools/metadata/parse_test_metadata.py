# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys

import input_recorder


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apps-json",
        required=True,
        help="Path to input JSON containing discovered apps",
    )
    parser.add_argument(
        "--zephyr-root",
        required=True,
        help="Path to the Zephyr repository root",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to write the output JSON file",
    )
    input_recorder.add_arguments(parser)
    return parser.parse_args(argv)


def lightweight_yaml_parse_platform_allow(file_path):
    """Internal lightweight fallback for parsing platform_allow from yaml."""
    platforms = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for platform_allow:
        for match in re.finditer(
            r"platform_allow:\s*\n((?:\s*-\s*\S+\s*\n)+)", content
        ):
            list_content = match.group(1)
            platforms.extend(re.findall(r"-\s*(\S+)", list_content))

        # Look for integration_platforms:
        for match in re.finditer(
            r"integration_platforms:\s*\n((?:\s*-\s*\S+\s*\n)+)", content
        ):
            list_content = match.group(1)
            platforms.extend(re.findall(r"-\s*(\S+)", list_content))
    except:
        pass

    if not platforms:
        return None
    return platforms


def main(argv=None):
    args = parse_args(argv)
    with open(args.apps_json, "r", encoding="utf-8") as f:
        apps = json.load(f)

    deps = input_recorder.InputRecorder(__file__)

    results = {}

    for app_pkg, app_path in apps.items():
        metadata_file = None

        for name in ["testcase.yaml", "sample.yaml"]:
            p = os.path.join(app_path, name)
            # Read if present; if missing, creating it would change the
            # result. Candidates after the first existing one are unused.
            deps.add_file(p)
            if os.path.exists(p):
                metadata_file = p
                break

        if metadata_file:
            platforms = lightweight_yaml_parse_platform_allow(metadata_file)
            results[app_pkg] = platforms
        else:
            # No yaml metadata
            results[app_pkg] = None

    # Dump final JSON mapping to output file.
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f)

    deps.write(args.deps_out, args.dirs_out)


if __name__ == "__main__":
    main()
