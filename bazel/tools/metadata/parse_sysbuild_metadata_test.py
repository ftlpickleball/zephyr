# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import os
import tempfile
import shutil
import sys
import json

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import input_recorder
import parse_sysbuild_metadata

class TestParseSysbuildMetadata(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_parser(self, apps_dict):
        apps_json_path = os.path.join(self.test_dir, "apps.json")
        output_json_path = os.path.join(self.test_dir, "output.json")

        with open(apps_json_path, "w", encoding="utf-8") as f:
             json.dump(apps_dict, f)

        parse_sysbuild_metadata.main([
            "--apps-json", apps_json_path,
            "--output-json", output_json_path
        ])

        with open(output_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_parse_empty_app(self):
        apps = {"//apps/empty": self.test_dir}
        output = self.run_parser(apps)
        self.assertEqual(output["custom_repos"], [])

    def test_parse_global_helpers(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        with open(os.path.join(app_path, "sysbuild.yml"), 'w', encoding="utf-8") as f:
            f.write("""
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("//apps/my_app", output["raw_metadata"])
        self.assertIn("mcuboot", output["raw_metadata"]["//apps/my_app"]["helpers"])

    def test_parse_custom_repo_detection_from_conf(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        with open(os.path.join(app_path, "sysbuild.yml"), 'w', encoding="utf-8") as f:
            f.write("""
helpers:
  helper_app:
    target: "//hello_bazel"
""")

        # Create sysbuild.conf with helper setting to trigger custom repo
        with open(os.path.join(app_path, "sysbuild.conf"), 'w', encoding="utf-8") as f:
            f.write("helper_app_CONFIG_LOG=y\n")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertEqual(len(output["custom_repos"]), 1)
        self.assertEqual(output["custom_repos"][0]["helper_name"], "helper_app")
        self.assertIn("CONFIG_LOG=y", output["custom_repos"][0]["extra_kconfig"])

    def test_parse_namespaced_settings(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, 'w', encoding="utf-8") as f:
            f.write("""
mcuboot_CONFIG_BOOT_SIGNATURE_TYPE_RSA=y
net_app_CONFIG_SOME_OPTION=value
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("translated_confs", output)
        translated = output["translated_confs"]
        self.assertIn("//apps/my_app", translated)
        self.assertIn("mcuboot", translated["//apps/my_app"])
        self.assertIn("CONFIG_BOOT_SIGNATURE_TYPE_RSA=y", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("net_app", translated["//apps/my_app"])
        self.assertIn("CONFIG_SOME_OPTION=value", translated["//apps/my_app"]["net_app"])

    def test_translate_sb_config(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, 'w', encoding="utf-8") as f:
            f.write("""
SB_CONFIG_BOOTLOADER_MCUBOOT=y
SB_CONFIG_MCUBOOT_MODE_UPGRADE_ONLY=y
SB_CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        self.assertIn("translated_confs", output)
        translated = output["translated_confs"]
        self.assertIn("//apps/my_app", translated)
        self.assertIn("mcuboot", translated["//apps/my_app"])
        self.assertIn("CONFIG_BOOT_UPGRADE_ONLY=y", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("# CONFIG_BOOT_RAM_LOAD_REVERT is not set", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y", translated["//apps/my_app"]["mcuboot"])
        self.assertNotIn("CONFIG_BOOTLOADER_MCUBOOT=y", translated["//apps/my_app"]["mcuboot"])
        self.assertNotIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_", translated["//apps/my_app"]["mcuboot"])
        self.assertIn("main", translated["//apps/my_app"])
        self.assertIn("CONFIG_BOOTLOADER_MCUBOOT=y", translated["//apps/my_app"]["main"])
        self.assertIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_OVERWRITE_ONLY=y", translated["//apps/my_app"]["main"])
        self.assertNotIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_UPGRADE_ONLY=y", translated["//apps/my_app"]["main"])
        self.assertNotIn("CONFIG_BOOT_UPGRADE_ONLY=y", translated["//apps/my_app"]["main"])

    def test_translate_sb_config_modes(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, "w", encoding="utf-8") as f:
            f.write("""
SB_CONFIG_BOOTLOADER_MCUBOOT=y
SB_CONFIG_MCUBOOT_MODE_RAM_LOAD_WITH_REVERT=y
SB_CONFIG_MCUBOOT_MODE_SINGLE_APP_RAM_LOAD=y
SB_CONFIG_MCUBOOT_MODE_SWAP_WITHOUT_SCRATCH=y
SB_CONFIG_MCUBOOT_SWAP_USING_OFFSET=y
SB_CONFIG_MCUBOOT_MODE_SWAP_USING_OFFSET=y
SB_CONFIG_MCUBOOT_MODE_SWAP_USING_MOVE=y
SB_CONFIG_MCUBOOT_MODE_FIRMWARE_UPDATER=y
SB_CONFIG_MCUBOOT_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE=y
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        translated = output["translated_confs"]["//apps/my_app"]
        self.assertIn("CONFIG_BOOTLOADER_MCUBOOT=y", translated["main"])
        self.assertIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_RAM_LOAD_WITH_REVERT=y",
            translated["main"],
        )
        self.assertIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_SINGLE_APP_RAM_LOAD=y",
            translated["main"],
        )
        self.assertIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_SWAP_USING_OFFSET=y",
            translated["main"],
        )
        self.assertIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_SWAP_USING_MOVE=y",
            translated["main"],
        )
        self.assertIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_FIRMWARE_UPDATER=y",
            translated["main"],
        )
        self.assertNotIn(
            "CONFIG_MCUBOOT_BOOTLOADER_MODE_FIRMWARE_UPDATER_BOOT_MODE_ENTRANCE=y",
            translated["main"],
        )
        self.assertIn("CONFIG_XIP=n", translated["main"])
        self.assertIn("CONFIG_FLASH_SIZE=0", translated["main"])
        self.assertIn("CONFIG_RETAINED_MEM=y", translated["main"])
        self.assertIn("CONFIG_RETENTION=y", translated["main"])
        self.assertIn("CONFIG_RETENTION_BOOT_MODE=y", translated["main"])
        self.assertIn("CONFIG_REBOOT=y", translated["main"])
        self.assertIn("CONFIG_BOOT_RAM_LOAD=y", translated["mcuboot"])
        self.assertIn("CONFIG_BOOT_RAM_LOAD_REVERT=y", translated["mcuboot"])
        self.assertIn(
            "CONFIG_SINGLE_APPLICATION_SLOT_RAM_LOAD=y",
            translated["mcuboot"],
        )
        self.assertIn("CONFIG_BOOT_SWAP_USING_OFFSET=y", translated["mcuboot"])
        self.assertIn("CONFIG_BOOT_SWAP_USING_MOVE=y", translated["mcuboot"])
        self.assertIn("CONFIG_BOOT_FIRMWARE_LOADER=y", translated["mcuboot"])
        self.assertIn(
            "CONFIG_BOOT_FIRMWARE_LOADER_BOOT_MODE=y",
            translated["mcuboot"],
        )
        self.assertNotIn("CONFIG_BOOT_SERIAL_BOOT_MODE=y", translated["mcuboot"])

    def test_mcuboot_mode_deselected_variant_does_not_clobber_shared_boot_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "sysbuild.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write(
                    "SB_CONFIG_BOOTLOADER_MCUBOOT=y\n"
                    "SB_CONFIG_MCUBOOT_MODE_DIRECT_XIP=y\n"
                    "SB_CONFIG_MCUBOOT_MODE_DIRECT_XIP_WITH_REVERT=n\n"
                )
            res = parse_sysbuild_metadata.process_sysbuild_conf(conf)
            mcuboot_lines = res["mcuboot"].strip().splitlines()
            self.assertIn("CONFIG_BOOT_DIRECT_XIP=y", mcuboot_lines)
            self.assertNotIn("CONFIG_BOOT_DIRECT_XIP=n", mcuboot_lines)

    def test_translate_sb_config_ram_load(self):
        app_path = os.path.join(self.test_dir, "my_app")
        os.makedirs(app_path)

        conf_file = os.path.join(app_path, "sysbuild.conf")
        with open(conf_file, 'w', encoding="utf-8") as f:
            f.write("""
SB_CONFIG_BOOTLOADER_MCUBOOT=y
SB_CONFIG_MCUBOOT_MODE_RAM_LOAD=y
""")

        apps = {"//apps/my_app": app_path}
        output = self.run_parser(apps)
        translated = output["translated_confs"]["//apps/my_app"]
        self.assertIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_RAM_LOAD=y", translated["main"])
        self.assertIn("CONFIG_BOOT_RAM_LOAD=y", translated["mcuboot"])
        self.assertIn("# CONFIG_BOOT_RAM_LOAD_REVERT is not set", translated["mcuboot"])

    def test_parse_overlays_and_board_helpers(self):
        app_path = os.path.join(self.test_dir, "my_app")
        boards_dir = os.path.join(app_path, "boards")
        sysbuild_dir = os.path.join(app_path, "sysbuild")
        mcuboot_boards_dir = os.path.join(sysbuild_dir, "mcuboot", "boards")
        os.makedirs(boards_dir)
        os.makedirs(mcuboot_boards_dir)

        with open(os.path.join(app_path, "sysbuild.yml"), "w", encoding="utf-8") as f:
            f.write("""
overlays:
  - "sysbuild/common.overlay"
  - "//boards/common:extra.overlay"
helpers:
  mcuboot:
    target: "//bootloader/mcuboot:mcuboot"
""")

        with open(
            os.path.join(boards_dir, "nrf5340dk_nrf5340_cpuapp.sysbuild.yml"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("""
overlays:
  - "sysbuild/board.overlay"
helpers:
  remote:
    target: "//samples/sysbuild/hello_world/remote:remote"
    platform: "//boards/nordic/nrf5340dk:nrf5340_cpunet"
""")

        with open(os.path.join(sysbuild_dir, "remote.conf"), "w", encoding="utf-8") as f:
            f.write("CONFIG_LOG=y\n")
        with open(os.path.join(sysbuild_dir, "mcuboot.conf"), "w", encoding="utf-8") as f:
            f.write("CONFIG_BOOT_MAX_IMG_SECTORS=256\n")
        with open(
            os.path.join(mcuboot_boards_dir, "nrf52840dk_nrf52840.conf"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("CONFIG_BOOT_MAX_IMG_SECTORS=512\n")

        apps = {"samples/sysbuild/hello_world": app_path}
        output = self.run_parser(apps)
        raw = output["raw_metadata"]["samples/sysbuild/hello_world"]
        self.assertEqual(
            raw["overlays"],
            [
                "samples/sysbuild/hello_world/sysbuild/common.overlay",
                "boards/common/extra.overlay",
            ],
        )
        self.assertEqual(
            raw["board_overlays"]["nrf5340dk_nrf5340_cpuapp"],
            ["samples/sysbuild/hello_world/sysbuild/board.overlay"],
        )
        # Specific boards (nrf52840dk_nrf52840, nrf5340dk_nrf5340_cpuapp) must precede default_board
        board_ids = [r["board_id"] for r in output["custom_repos"]]
        self.assertEqual(board_ids[-1], "default_board")
        remote_repos = [
            r for r in output["custom_repos"] if r["helper_name"] == "remote"
        ]
        self.assertEqual(len(remote_repos), 1)
        self.assertEqual(remote_repos[0]["board_id"], "nrf5340dk/nrf5340/cpunet")
        self.assertEqual(
            remote_repos[0]["platform"],
            "//boards/nordic/nrf5340dk:nrf5340_cpunet",
        )
        mcuboot_52840 = [
            r
            for r in output["custom_repos"]
            if r["helper_name"] == "mcuboot"
            and r["board_id"] == "nrf52840dk_nrf52840"
        ]
        self.assertEqual(len(mcuboot_52840), 1)
        self.assertIn(
            "sysbuild/mcuboot/boards/nrf52840dk_nrf52840.conf",
            mcuboot_52840[0]["conf_fragments"],
        )
        self.assertEqual(
            parse_sysbuild_metadata.sanitize_board_id("board@1.0/soc"),
            "board_1_0_soc",
        )


class TestParseSysbuildMetadataDeps(unittest.TestCase):
    """Tests for --deps-out / --dirs-out."""

    def setUp(self):
        self.test_dir = os.path.realpath(tempfile.mkdtemp())
        self.out_dir = tempfile.mkdtemp()
        self.script = os.path.realpath(parse_sysbuild_metadata.__file__)

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.out_dir)

    def write(self, rel_path, content=""):
        path = os.path.join(self.test_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def path(self, *parts):
        return os.path.join(self.test_dir, *parts)

    def run_main(self, apps, deps_flags=True):
        """Returns (output bytes, deps lines, dirs lines)."""
        apps_json = os.path.join(self.out_dir, "apps.json")
        output_json = os.path.join(self.out_dir, "out.json")
        deps_out = os.path.join(self.out_dir, "deps.txt")
        dirs_out = os.path.join(self.out_dir, "dirs.txt")
        with open(apps_json, "w", encoding="utf-8") as f:
            json.dump(apps, f)
        argv = ["--apps-json", apps_json, "--output-json", output_json]
        if deps_flags:
            argv += ["--deps-out", deps_out, "--dirs-out", dirs_out]
        parse_sysbuild_metadata.main(argv)
        with open(output_json, "rb") as f:
            output = f.read()
        if not deps_flags:
            self.assertFalse(os.path.exists(deps_out))
            self.assertFalse(os.path.exists(dirs_out))
            return output, None, None
        lines = []
        for out in (deps_out, dirs_out):
            with open(out, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content == "" or content.endswith("\n"))
            lines.append(content.splitlines())
        return output, lines[0], lines[1]

    def _missing_candidates(self, app_dir, img_names, boards):
        cands = [
            self.path(app_dir, "sysbuild", img, "boards")
            for img in img_names
        ]
        for img in img_names:
            cands.extend([
                self.path(app_dir, "sysbuild", img, "prj.conf"),
                *[self.path(app_dir, "sysbuild", img, "boards", f"{b}.conf") for b in boards if b != "default_board"],
                self.path(app_dir, "sysbuild", f"{img}.conf"),
                *[self.path(app_dir, "sysbuild", img, "boards", f"{b}.overlay") for b in boards if b != "default_board"],
                self.path(app_dir, "sysbuild", img, "app.overlay"),
                self.path(app_dir, "sysbuild", f"{img}.overlay"),
            ])
        return cands

    def test_deps_full_app(self):
        self.write("app/sysbuild.yml", """
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
  net:
    target: "//net"
  ext:
    target: "//ext"
    type: external
""")
        self.write("app/boards/b1.sysbuild.yml", """
helpers:
  board_helper:
    target: "//bh"
""")
        self.write("app/boards/b1.conf")
        self.write("app/sysbuild.conf", "mcuboot_CONFIG_LOG=y\n")
        self.write("app/sysbuild/mcuboot.conf", "CONFIG_FOO=y\n")
        self.write("app/sysbuild/net/boards/b1.conf", "CONFIG_NET_B1=y\n")
        apps = {"//app": self.path("app")}

        out_without, _, _ = self.run_main(apps, deps_flags=False)
        out_with, deps, dirs = self.run_main(apps)

        self.assertEqual(out_with, out_without)
        repos = json.loads(out_with)["custom_repos"]
        self.assertEqual([r["helper_name"] for r in repos], ["mcuboot", "net", "mcuboot"])
        expected_missing = set(
            self._missing_candidates(
                "app",
                ["mcuboot", "zephyr_project", "net", "board_helper", "bh"],
                ["b1"],
            )
        ) - {
            self.path("app", "sysbuild", "mcuboot.conf"),
            self.path("app", "sysbuild", "net", "boards"),
            self.path("app", "sysbuild", "net", "boards", "b1.conf"),
        }
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.path("app", "sysbuild.yml"),
                self.path("app", "boards", "b1.sysbuild.yml"),
                self.path("app", "sysbuild.conf"),
                self.path("app", "Kconfig.sysbuild"),
                # Missing fragments/overlays: creating them would declare repos.
                # The external helper is never probed.
                *expected_missing,
            ]),
        )
        # sysbuild/mcuboot.conf and sysbuild/net/boards/b1.conf are only checked
        # for existence, so their parent directory listings are tracked rather
        # than their contents.
        self.assertEqual(
            dirs,
            sorted([
                self.path("app", "boards"),
                self.path("app", "sysbuild"),
                self.path("app", "sysbuild", "net", "boards"),
            ]),
        )

    def test_deps_empty_app(self):
        os.makedirs(self.path("app"))

        _, deps, dirs = self.run_main({"//app": self.path("app")})

        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.path("app", "sysbuild.yml"),
                self.path("app", "boards"),
                self.path("app", "sysbuild.conf"),
            ]),
        )
        self.assertEqual(dirs, [])

    def test_deps_symlinked_app_and_fragment(self):
        self.write("real_app/sysbuild.yml", """
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
""")
        self.write("shared/mcuboot.conf")
        os.makedirs(self.path("real_app", "sysbuild"))
        os.symlink(
            self.path("shared", "mcuboot.conf"),
            self.path("real_app", "sysbuild", "mcuboot.conf"),
        )
        os.symlink(self.path("real_app"), self.path("app"))

        _, deps, dirs = self.run_main({"//app": self.path("app")})

        expected_missing = set(
            self._missing_candidates(
                "real_app",
                ["mcuboot", "zephyr_project"],
                ["default_board"],
            )
        ) - {self.path("real_app", "sysbuild", "mcuboot.conf")}
        self.assertEqual(
            deps,
            sorted([
                self.script,
                os.path.realpath(input_recorder.__file__),
                self.path("real_app", "sysbuild.yml"),
                self.path("real_app", "boards"),
                self.path("real_app", "sysbuild.conf"),
                self.path("real_app", "Kconfig.sysbuild"),
                *expected_missing,
            ]),
        )
        # The listing of sysbuild/ can't see the link target vanish, so the
        # target's parent directory listing (shared/) is tracked instead of the
        # target file's content.
        self.assertEqual(
            dirs,
            sorted([self.path("real_app", "sysbuild"), self.path("shared")]),
        )

    def test_kconfig_sysbuild_declares_custom_repo(self):
        self.write("app/sysbuild.yml", """
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
""")
        self.write(
            "app/Kconfig.sysbuild",
            'source "share/sysbuild/Kconfig"\nconfig BOOT_SIGNATURE_KEY_FILE\n\tdefault "app_key.pem"\n',
        )

        out, deps, _ = self.run_main({"//app": self.path("app")})
        repos = json.loads(out)["custom_repos"]
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["helper_name"], "mcuboot")
        self.assertEqual(repos[0]["parent_app"], "//app")
        self.assertIn(self.path("app", "Kconfig.sysbuild"), deps)

    def test_sysbuild_conf_declares_custom_repo_and_splits_multi_key(self):
        self.write("app/sysbuild.yml", """
helpers:
  mcuboot:
    target: "@mcuboot//boot/zephyr:zephyr_project"
""")
        self.write(
            "app/sysbuild.conf",
            'SB_CONFIG_BOOT_ENCRYPTION=y\nSB_CONFIG_BOOT_ENCRYPTION_KEY_FILE="enc.pem"\n',
        )

        out, _, _ = self.run_main({"//app": self.path("app")})
        repos = json.loads(out)["custom_repos"]
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["helper_name"], "mcuboot")
        self.assertEqual(repos[0]["parent_app"], "//app")

        self.write(
            "app/sysbuild.conf",
            'SB_CONFIG_BOOT_SIGNATURE_KEY_FILE="key1.pem,key2.pem"\n',
        )
        res = parse_sysbuild_metadata.process_sysbuild_conf(
            self.path("app", "sysbuild.conf")
        )
        self.assertIn('CONFIG_MCUBOOT_SIGNATURE_KEY_FILE="key1.pem"', res["main"])
        self.assertIn(
            'CONFIG_BOOT_SIGNATURE_KEY_FILE="key1.pem,key2.pem"',
            res["mcuboot"],
        )


if __name__ == '__main__':
    unittest.main()
