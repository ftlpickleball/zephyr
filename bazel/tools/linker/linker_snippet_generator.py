# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Generates Zephyr's linker snippet files containing sorted lines of linker
section includes. These generated linker snippets will be included in Zephyr's
linker script template, so that sections are placed in the desired order.

Zephyr has a CMake function that produces the same file. This script does the
same thing in Python.
"""

import argparse
import collections
import os
from pathlib import Path

# Mapping from CMake location names to the generated filename.
LOCATION_TO_FILENAME = {
    "SECTIONS": "snippets-sections.ld",
    "ROM_SECTIONS": "snippets-rom-sections.ld",
    "RAM_SECTIONS": "snippets-ram-sections.ld",
    "DATA_SECTIONS": "snippets-data-sections.ld",
    "TEXT_SECTIONS": "snippets-text-sections.ld",
    "ROM_START": "snippets-rom-start.ld",
    "NOINIT": "snippets-noinit.ld",
    "RWDATA": "snippets-rwdata.ld",
    "RODATA": "snippets-rodata.ld",
    "RAMFUNC_SECTION": "snippets-ramfunc-section.ld",
    "NOCACHE_SECTION": "snippets-nocache-section.ld",
    "ITCM_SECTION": "snippets-itcm-section.ld",
    "DTCM_SECTION": "snippets-dtcm-section.ld",
    "PINNED_RAM_SECTIONS": "snippets-pinned-ram-sections.ld",
    "PINNED_DATA_SECTIONS": "snippets-pinned-data-sections.ld",
    "PINNED_RODATA": "snippets-pinned-rodata.ld",
    "TEXT_SECTIONS": "snippets-text-sections.ld",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--zephyr-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    # Group include lines by their location.
    includes_by_location = collections.defaultdict(list)

    with open(args.manifest, "r") as f:
        for line in f:
            location, sort_key, path = line.strip().split(" ", 2)
            if location not in LOCATION_TO_FILENAME:
                print(f"Warning: Unknown linker location '{location}', skipping.")
                continue

            relative_path = os.path.relpath(path, start=args.zephyr_root)
            # Create the include string, mirroring CMake's format for sorting.
            # The relative path needs to be calculated based on an include root,
            # but for simplicity here we use the full path. A real implementation
            # would need to make this relative to a known root.
            include_str = f'/* Sort key: "{sort_key}" */#include "{relative_path}"'
            includes_by_location[location].append(include_str)

    # Write the sorted include lines to their respective snippet files.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for location, filename in LOCATION_TO_FILENAME.items():
        output_path = args.output_dir / filename

        # Get the list of includes for this location.
        # The .get() method safely returns an empty list if the location was not in the manifest.
        includes = includes_by_location.get(location, [])

        content = ""
        if includes:
            # If we have includes, sort them and join them with newlines.
            includes.sort()
            content = "\n".join(includes) + "\n"

        # Write the file. This will be empty if there were no includes for this location.
        with open(output_path, "w") as f:
            f.write(content)

if __name__ == "__main__":
    main()

