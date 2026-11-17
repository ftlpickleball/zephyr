#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import argparse
import collections
import glob
import hashlib
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
        "--apps-json",
        required=True,
        help="Path to input JSON containing discovered apps",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to output JSON file",
    )
    input_recorder.add_arguments(parser)
    return parser.parse_args(argv)


def parse_sysbuild_yaml(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return None


def _normalize_overlay_path(app_pkg, ov):
    if ov.startswith("//"):
        return ov[2:].replace(":", "/")
    if not ov.startswith("/"):
        return f"{app_pkg}/{ov.lstrip(':')}"
    return ov


def _parse_sysbuild_dict(content, app_pkg):
    if not isinstance(content, dict):
        return [], {}
    overlays = []
    if isinstance(content.get("overlays"), list):
        overlays = [
            _normalize_overlay_path(app_pkg, ov) for ov in content["overlays"]
        ]
    helpers = {}
    if isinstance(content.get("helpers"), dict):
        helpers = {
            k: (dict(v) if isinstance(v, dict) else {})
            for k, v in content["helpers"].items()
        }
        top_cond = content.get("condition")
        if top_cond:
            for h in helpers.values():
                h.setdefault("condition", top_cond)
    return overlays, helpers


_MCUBOOT_MODE_BOOTLOADER_MAP = {
    "MCUBOOT_MODE_SINGLE_APP": ("CONFIG_SINGLE_APPLICATION_SLOT",),
    "MCUBOOT_MODE_SWAP_SCRATCH": ("CONFIG_BOOT_SWAP_USING_SCRATCH",),
    "MCUBOOT_MODE_SWAP_USING_OFFSET": ("CONFIG_BOOT_SWAP_USING_OFFSET",),
    "MCUBOOT_MODE_SWAP_USING_MOVE": ("CONFIG_BOOT_SWAP_USING_MOVE",),
    "MCUBOOT_MODE_OVERWRITE_ONLY": ("CONFIG_BOOT_UPGRADE_ONLY",),
    "MCUBOOT_MODE_UPGRADE_ONLY": ("CONFIG_BOOT_UPGRADE_ONLY",),
    "MCUBOOT_MODE_DIRECT_XIP": ("CONFIG_BOOT_DIRECT_XIP",),
    "MCUBOOT_MODE_DIRECT_XIP_WITH_REVERT": (
        "CONFIG_BOOT_DIRECT_XIP",
        "CONFIG_BOOT_DIRECT_XIP_REVERT",
    ),
    "MCUBOOT_MODE_RAM_LOAD": ("CONFIG_BOOT_RAM_LOAD",),
    "MCUBOOT_MODE_RAM_LOAD_WITH_REVERT": (
        "CONFIG_BOOT_RAM_LOAD",
        "CONFIG_BOOT_RAM_LOAD_REVERT",
    ),
    "MCUBOOT_MODE_SINGLE_APP_RAM_LOAD": (
        "CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD",
    ),
    "MCUBOOT_MODE_FIRMWARE_UPDATER": ("CONFIG_BOOT_FIRMWARE_LOADER",),
}

_RAM_LOAD_MODES = frozenset({
    "MCUBOOT_MODE_RAM_LOAD",
    "MCUBOOT_MODE_RAM_LOAD_WITH_REVERT",
    "MCUBOOT_MODE_SINGLE_APP_RAM_LOAD",
})

_BOOT_SIGNATURE_OPTIONS = frozenset({
    "BOOT_SIGNATURE_TYPE_RSA",
    "BOOT_SIGNATURE_TYPE_ECDSA_P256",
    "BOOT_SIGNATURE_TYPE_ED25519",
    "BOOT_SIGNATURE_TYPE_NONE",
})


def process_sysbuild_conf(file_path):
    fragments = collections.defaultdict(list)
    sb_options = []
    sb_dict = {}
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
                    sb_options.append((option, value))
                    sb_dict[option] = value
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

    # Mirror share/sysbuild/image_configurations/MAIN_image_default.cmake and
    # BOOTLOADER_image_default.cmake so main and mcuboot images receive only
    # their own valid Kconfig symbols.
    swap_using_offset = sb_dict.get("MCUBOOT_SWAP_USING_OFFSET") == "y"
    ramload_allow_xip = sb_dict.get("MCUBOOT_RAMLOAD_ALLOW_XIP") == "y"
    fw_updater_boot_mode = (
        sb_dict.get("MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE") == "y"
        or sb_dict.get("MCUBOOT_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE") == "y"
    )

    def _mcuboot_mode_main_option(opt):
        if opt == "MCUBOOT_MODE_UPGRADE_ONLY":
            return "CONFIG_MCUBOOT_BOOTLOADER_MODE_OVERWRITE_ONLY"
        if opt == "MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH" and swap_using_offset:
            return "CONFIG_MCUBOOT_BOOTLOADER_MODE_SWAP_USING_OFFSET"
        if opt == "MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH":
            return "CONFIG_MCUBOOT_BOOTLOADER_MODE_SWAP_USING_MOVE"
        return opt.replace("MCUBOOT_MODE_", "CONFIG_MCUBOOT_BOOTLOADER_MODE_")

    def _mcuboot_mode_boot_syms(opt):
        if opt == "MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH":
            return (
                "CONFIG_BOOT_SWAP_USING_OFFSET"
                if swap_using_offset
                else "CONFIG_BOOT_SWAP_USING_MOVE",
            )
        return _MCUBOOT_MODE_BOOTLOADER_MAP.get(opt, ())

    enabled_main_mode_syms = set()
    enabled_boot_mode_syms = set()
    for opt, val in sb_dict.items():
        if (
            val == "y"
            and opt.startswith("MCUBOOT_MODE_")
            and opt != "MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE"
        ):
            enabled_main_mode_syms.add(_mcuboot_mode_main_option(opt))
            enabled_boot_mode_syms.update(_mcuboot_mode_boot_syms(opt))

    for option, value in sb_options:
        if option == "BOOTLOADER_MCUBOOT":
            if value == "y":
                fragments["main"].append("CONFIG_BOOTLOADER_MCUBOOT=y")
            elif value == "n":
                fragments["main"].append("# CONFIG_BOOTLOADER_MCUBOOT is not set")
        elif option.startswith("MCUBOOT_MODE_"):
            if option == "MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE":
                continue
            main_option = _mcuboot_mode_main_option(option)
            if not (value == "n" and main_option in enabled_main_mode_syms):
                fragments["main"].append(f"{main_option}={value}")
            if (
                value == "y"
                and option in _RAM_LOAD_MODES
                and not ramload_allow_xip
            ):
                fragments["main"].append("CONFIG_XIP=n")
                fragments["main"].append("CONFIG_FLASH_SIZE=0")
            if (
                value == "y"
                and option == "MCUBOOT_MODE_FIRMWARE_UPDATER"
                and fw_updater_boot_mode
            ):
                fragments["main"].extend([
                    "CONFIG_RETAINED_MEM=y",
                    "CONFIG_RETENTION=y",
                    "CONFIG_RETENTION_BOOT_MODE=y",
                    "CONFIG_REBOOT=y",
                ])

            for boot_sym in _mcuboot_mode_boot_syms(option):
                if not (value == "n" and boot_sym in enabled_boot_mode_syms):
                    fragments["mcuboot"].append(f"{boot_sym}={value}")
            if value == "y":
                if "CONFIG_BOOT_DIRECT_XIP_REVERT" not in enabled_boot_mode_syms:
                    fragments["mcuboot"].append(
                        "# CONFIG_BOOT_DIRECT_XIP_REVERT is not set"
                    )
                if "CONFIG_BOOT_RAM_LOAD_REVERT" not in enabled_boot_mode_syms:
                    fragments["mcuboot"].append(
                        "# CONFIG_BOOT_RAM_LOAD_REVERT is not set"
                    )
            if (
                value == "y"
                and option == "MCUBOOT_MODE_FIRMWARE_UPDATER"
                and fw_updater_boot_mode
            ):
                fragments["mcuboot"].extend([
                    "CONFIG_RETAINED_MEM=y",
                    "CONFIG_RETENTION=y",
                    "CONFIG_RETENTION_BOOT_MODE=y",
                    "CONFIG_BOOT_FIRMWARE_LOADER_BOOT_MODE=y",
                ])
        elif option in _BOOT_SIGNATURE_OPTIONS or option.startswith("BOOT_SIGNATURE_TYPE_"):
            fragments["mcuboot"].append(f"CONFIG_{option}={value}")
        elif option == "BOOT_SIGNATURE_KEY_FILE":
            raw_key = value.strip().strip('"')
            first_key = raw_key.split(",")[0].strip()
            fragments["main"].append(
                f'CONFIG_MCUBOOT_SIGNATURE_KEY_FILE="{first_key}"'
            )
            fragments["mcuboot"].append(
                f"CONFIG_BOOT_SIGNATURE_KEY_FILE={value}"
            )
        elif option == "MCUBOOT_NO_DOWNGRADE":
            if value == "y":
                fragments["main"].append(
                    "CONFIG_MCUBOOT_BOOTLOADER_NO_DOWNGRADE=y"
                )
            elif value == "n":
                fragments["main"].append(
                    "# CONFIG_MCUBOOT_BOOTLOADER_NO_DOWNGRADE is not set"
                )
        elif option == "COMPILER_WARNINGS_AS_ERRORS":
            if value == "y":
                fragments["main"].append("CONFIG_COMPILER_WARNINGS_AS_ERRORS=y")
                fragments["mcuboot"].append("CONFIG_COMPILER_WARNINGS_AS_ERRORS=y")
            elif value == "n":
                fragments["main"].append("# CONFIG_COMPILER_WARNINGS_AS_ERRORS is not set")
                fragments["mcuboot"].append("# CONFIG_COMPILER_WARNINGS_AS_ERRORS is not set")

    return {
        domain: "\n".join(settings) + "\n"
        for domain, settings in fragments.items()
    }


def sanitize_board_id(board_id):
    return (
        board_id.replace("/", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("@", "_")
    )


def main(argv=None):
    args = parse_args(argv)
    with open(args.apps_json, "r", encoding="utf-8") as f:
        apps = json.load(f)

    deps = input_recorder.InputRecorder(__file__)

    raw_metadata = {}
    translated_confs = {}

    for app_pkg, app_path in apps.items():
        app_graph = {
            "helpers": {},
            "board_helpers": {},
            "overlays": [],
            "board_overlays": {},
        }

        global_file = os.path.join(app_path, "sysbuild.yml")
        deps.add_file(global_file)
        if os.path.exists(global_file):
            content = parse_sysbuild_yaml(global_file)
            overlays, helpers = _parse_sysbuild_dict(content, app_pkg)
            if overlays:
                app_graph["overlays"] = overlays
            if helpers:
                app_graph["helpers"] = helpers

        boards_dir = os.path.join(app_path, "boards")
        if os.path.isdir(boards_dir):
            # Adding or removing *.sysbuild.yml files changes the result.
            deps.add_dir(boards_dir)
        else:
            deps.add_file(boards_dir)
        if os.path.exists(boards_dir):
            pattern = os.path.join(boards_dir, "*.sysbuild.yml")
            for board_file in glob.glob(pattern):
                deps.add_file(board_file)
                filename = os.path.basename(board_file)
                board_name = filename.replace(".sysbuild.yml", "")
                content = parse_sysbuild_yaml(board_file)
                overlays, helpers = _parse_sysbuild_dict(content, app_pkg)
                if overlays:
                    app_graph["board_overlays"][board_name] = overlays
                if helpers:
                    app_graph["board_helpers"][board_name] = helpers

        if (
            app_graph["helpers"]
            or app_graph["board_helpers"]
            or app_graph["overlays"]
            or app_graph["board_overlays"]
        ):
            raw_metadata[app_pkg] = app_graph

        sysbuild_conf = os.path.join(app_path, "sysbuild.conf")
        deps.add_file(sysbuild_conf)
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
        kconfig_sysbuild = os.path.join(app_path, "Kconfig.sysbuild")
        deps.add_file(kconfig_sysbuild)
        has_kconfig_sysbuild = os.path.exists(kconfig_sysbuild)
        has_sysbuild_conf = os.path.exists(
            os.path.join(app_path, "sysbuild.conf")
        )

        def _helper_image_names(h_name, h_cfg):
            h_target = h_cfg.get("target", "")
            t_app = (
                h_target.split(":")[-1]
                if ":" in h_target
                else os.path.basename(h_target.rstrip("/"))
            )
            names = [h_name]
            if t_app and t_app not in names:
                names.append(t_app)
            return names, t_app

        boards = set(app_graph["board_helpers"].keys())
        has_img_boards = False
        all_helper_defs = list(app_graph["helpers"].items())
        for bh in app_graph["board_helpers"].values():
            all_helper_defs.extend(bh.items())
        seen_img_names = set()
        for h_name, h_cfg in all_helper_defs:
            if h_cfg.get("type") == "external" or not h_cfg.get("target"):
                continue
            img_names, _ = _helper_image_names(h_name, h_cfg)
            for img_name in img_names:
                if img_name in seen_img_names:
                    continue
                seen_img_names.add(img_name)
                img_boards_dir = os.path.join(
                    app_path, "sysbuild", img_name, "boards"
                )
                if os.path.isdir(img_boards_dir):
                    deps.add_dir(img_boards_dir)
                    for entry in os.listdir(img_boards_dir):
                        for ext in (".conf", ".overlay"):
                            if entry.endswith(ext):
                                boards.add(entry[: -len(ext)])
                                has_img_boards = True
                else:
                    deps.add_file(img_boards_dir)
        if has_img_boards or not boards:
            boards.add("default_board")

        for board_id in sorted(boards, key=lambda b: (b == "default_board", b)):
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
                    if ":" in platform:
                        plat_pkg, plat_target = platform.split(":", 1)
                        plat_board = os.path.basename(plat_pkg.rstrip("/"))
                        if plat_target == plat_board:
                            helper_board_id = plat_board
                        elif plat_target.startswith(plat_board + "_"):
                            suffix = plat_target[len(plat_board) + 1 :]
                            helper_board_id = (
                                f"{plat_board}/{suffix.replace('_', '/')}"
                            )
                        else:
                            helper_board_id = (
                                f"{plat_board}/{plat_target.replace('_', '/')}"
                            )
                    else:
                        helper_board_id = os.path.basename(platform)
                else:
                    helper_board_id = board_id

                image_names, target_app_name = _helper_image_names(
                    helper_name, helper_config
                )

                board_candidates = []
                if helper_board_id != "default_board":
                    board_candidates.append(helper_board_id)
                    safe_helper_board = sanitize_board_id(helper_board_id)
                    if safe_helper_board not in board_candidates:
                        board_candidates.append(safe_helper_board)

                def probe_candidate(rel_cand):
                    cand_path = os.path.join(app_path, rel_cand)
                    if os.path.exists(cand_path):
                        # Only its existence matters, not its content: track
                        # the listing of its directory so that editing the
                        # fragment/overlay does not invalidate this result.
                        deps.add_dir(os.path.dirname(cand_path))
                        if os.path.islink(cand_path):
                            # The listing of sysbuild/ can't see the link
                            # target vanish; track the target's parent
                            # directory listing so that editing the target's
                            # content still does not invalidate this result.
                            deps.add_dir(
                                os.path.dirname(deps.realpath(cand_path))
                            )
                        return True
                    deps.add_file(cand_path)
                    return False

                conf_fragments = []
                dtc_overlays = []
                for img_name in image_names:
                    for rel_cand in [
                        os.path.join("sysbuild", img_name, "prj.conf"),
                        *[
                            os.path.join("sysbuild", img_name, "boards", f"{b}.conf")
                            for b in board_candidates
                        ],
                        os.path.join("sysbuild", f"{img_name}.conf"),
                    ]:
                        if probe_candidate(rel_cand) and rel_cand not in conf_fragments:
                            conf_fragments.append(rel_cand)

                    for rel_cand in [
                        os.path.join("sysbuild", img_name, "app.overlay"),
                        os.path.join("sysbuild", f"{img_name}.overlay"),
                        *[
                            os.path.join("sysbuild", img_name, "boards", f"{b}.overlay")
                            for b in board_candidates
                        ],
                    ]:
                        if probe_candidate(rel_cand) and rel_cand not in dtc_overlays:
                            dtc_overlays.append(rel_cand)

                helper_fragment = app_fragments.get(helper_name, "")
                if not helper_fragment and target_app_name:
                    helper_fragment = app_fragments.get(target_app_name, "")

                if (
                    conf_fragments
                    or dtc_overlays
                    or helper_fragment
                    or has_kconfig_sysbuild
                    or (
                        has_sysbuild_conf
                        and (
                            helper_name in ("mcuboot", "firmware_loader")
                            or target_app_name in ("mcuboot", "firmware_loader")
                        )
                    )
                ):
                    path_str = f"{app_pkg}->{helper_name}"
                    path_hash = hashlib.md5(
                        path_str.encode("utf-8")
                    ).hexdigest()[:8]
                    safe_board = sanitize_board_id(helper_board_id)
                    repo_name = f"zc_{path_hash}_{safe_board}"

                    repos_to_declare.append({
                        "name": repo_name,
                        "app_label": helper_target,
                        "board_id": helper_board_id,
                        "platform": platform,
                        "conf_fragments": conf_fragments,
                        "dtc_overlays": dtc_overlays,
                        "extra_kconfig": helper_fragment,
                        "parent_app": app_pkg,
                        "helper_name": helper_name,
                    })

    results = {
        "raw_metadata": raw_metadata,
        "custom_repos": repos_to_declare,
        "translated_confs": translated_confs,
    }

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    deps.write(args.deps_out, args.dirs_out)


if __name__ == "__main__":
    main()
