# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
import os
import shutil
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

# Import the script to test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
import kconfig_gen_values
import kconfig_utils

class TestKconfigGenValues(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.zephyr_base = Path(self.test_dir) / "zephyr"
        self.zephyr_base.mkdir()

        # Create minimal Zephyr structure
        (self.zephyr_base / "scripts" / "kconfig").mkdir(parents=True)
        (self.zephyr_base / "arch" / "arm").mkdir(parents=True)
        (self.zephyr_base / "soc" / "nordic" / "nrf52").mkdir(parents=True)
        (self.zephyr_base / "boards" / "arm" / "nrf52840dk").mkdir(parents=True)
        (self.zephyr_base / "cmake" / "toolchain" / "zephyr").mkdir(parents=True)
        (self.zephyr_base / "cmake" / "toolchain" / "gnuarmemb").mkdir(parents=True)

        # Create some Kconfig files
        (self.zephyr_base / "Kconfig").write_text("mainmenu \"Test\"\n")

        # Mock kconfiglib and its wrapper
        self.kconfig_mock = MagicMock()
        sys.modules['kconfiglib'] = self.kconfig_mock
        self.kconfig_wrapper_mock = MagicMock()
        sys.modules['kconfig'] = self.kconfig_wrapper_mock

        # Mock pcpp
        self.pcpp_mock = MagicMock()
        self.pcpp_mock.__file__ = '/mock/pcpp/__init__.py'
        sys.modules['pcpp'] = self.pcpp_mock

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_setup_environment(self):
        args = MagicMock()
        args.board = "nrf52840dk/nrf52840"
        args.toolchain_variant = None
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)

        self.assertEqual(os.environ["BOARD"], "nrf52840dk")
        self.assertEqual(os.environ["BOARD_QUALIFIERS"], "nrf52840")
        self.assertEqual(os.environ["ARCH"], "*")
        self.assertEqual(os.environ["ZEPHYR_BASE"], str(self.zephyr_base))
        self.assertEqual(os.environ["TOOLCHAIN_KCONFIG_DIR"], os.path.join(str(self.zephyr_base), "cmake", "toolchain", "zephyr"))

    def test_setup_environment_native(self):
        args = MagicMock()
        args.board = "native_sim"
        args.toolchain_variant = None
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "boards/native/native_sim")
        os.makedirs(output_dir, exist_ok=True)

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)
        self.assertEqual(os.environ["TOOLCHAIN_KCONFIG_DIR"], os.path.join(str(self.zephyr_base), "cmake", "toolchain", "host"))

    def test_setup_environment_explicit_toolchain(self):
        args = MagicMock()
        args.board = "nrf52840dk"
        args.toolchain_variant = "gnuarmemb"
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")
        os.makedirs(output_dir, exist_ok=True)

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)
        self.assertEqual(os.environ["TOOLCHAIN_KCONFIG_DIR"], os.path.join(str(self.zephyr_base), "cmake", "toolchain", "gnuarmemb"))

    @patch('subprocess.run')
    def test_main_success(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = str(self.zephyr_base / "boards" / "arm" / "nrf52840dk")

        # Mock subprocess.run for kconfig.py
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        # Side effect to create dummy files that main() expects to read
        def create_files(*args, **kwargs):
             os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)
             with open(os.path.join(output_dir, ".config"), "w") as f:
                 f.write("CONFIG_FOO=y\n")
             with open(os.path.join(output_dir, "zephyr", "autoconf.h"), "w") as f:
                 f.write("#define CONFIG_FOO 1\n")
             return mock_res
        mock_run.side_effect = create_files

        # Mock kconfiglib
        mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = mock_kconf
        mock_kconf.unique_defined_syms = []

        with patch('sys.argv', [
            'kconfig_gen_values.py',
            '--zephyr-base', str(self.zephyr_base),
            '--app-dir', self.test_dir,
            '--board', 'nrf52840dk',
            '--board-dir', board_dir,
            '--parent-platform', '//platforms:test',
            '--output-dir', output_dir,
            '--app-name', 'my_custom_app'
        ]):
            # We need to mock other subprocess calls in main like generate_kconfig_dts
            with patch('kconfig_utils.generate_kconfig_dts'), \
                 patch('kconfig_gen_values.preprocess_dts') as mock_pre, \
                 patch('kconfig_gen_values.generate_edt_pickle'):
                mock_pre.return_value = ("merged.dts", [])
                kconfig_gen_values.main()

        # Verify APP_NAME was added
        autoconf_path = os.path.join(output_dir, "zephyr", "autoconf.h")
        content = Path(autoconf_path).read_text()
        self.assertIn('#define APP_NAME "my_custom_app"', content)

    @patch('subprocess.run')
    def test_main_failure(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = str(self.zephyr_base / "boards" / "arm" / "nrf52840dk")

        # Mock subprocess.run to fail
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "Some Kconfig error"
        mock_run.return_value = mock_res

        with patch('sys.argv', [
            'kconfig_gen_values.py',
            '--zephyr-base', str(self.zephyr_base),
            '--app-dir', self.test_dir,
            '--board', 'nrf52840dk',
            '--board-dir', board_dir,
            '--parent-platform', '//platforms:test',
            '--output-dir', output_dir
        ]):
            with patch('kconfig_utils.generate_kconfig_dts'), \
                 patch('kconfig_gen_values.preprocess_dts') as mock_pre, \
                 patch('kconfig_gen_values.generate_edt_pickle'):
                mock_pre.return_value = ("merged.dts", [])

                with self.assertRaises(SystemExit) as cm:
                    kconfig_gen_values.main()

                self.assertEqual(str(cm.exception), "Kconfig generation failed with exit code 1")

    def test_get_conf_files_with_qualifiers(self):
        args = MagicMock()
        args.app_dir = self.test_dir
        board_dir = os.path.join(self.test_dir, "board")
        os.makedirs(board_dir, exist_ok=True)

        # Create a dummy defconfig file with underscores
        defconfig_path = os.path.join(board_dir, "harriet_evb2_mimxrt595s_cm33_defconfig")
        with open(defconfig_path, "w") as f:
            f.write("CONFIG_FOO=y\n")

        os.environ["BOARD"] = "harriet_evb2"
        os.environ["BOARD_QUALIFIERS"] = "mimxrt595s/cm33"

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir)

        self.assertIn(defconfig_path, conf_files)

    def test_get_conf_files_app_specific_with_nested_qualifier(self):
        args = MagicMock()
        args.app_dir = self.test_dir
        board_dir = os.path.join(self.test_dir, "board")
        os.makedirs(board_dir, exist_ok=True)

        # Create an app boards dir
        app_boards_dir = os.path.join(self.test_dir, "boards")
        os.makedirs(app_boards_dir, exist_ok=True)
        conf_path = os.path.join(app_boards_dir, "rpi_pico2_rp2350a_m33.conf")
        with open(conf_path, "w") as f:
             f.write("CONFIG_BAR=y\n")

        os.environ["BOARD"] = "rpi_pico2"
        os.environ["BOARD_QUALIFIERS"] = "rp2350a/m33"

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir)

        self.assertIn(conf_path, conf_files)

    def test_get_conf_files_with_revisions(self):
        args = MagicMock()
        args.app_dir = self.test_dir
        board_dir = os.path.join(self.test_dir, "board")
        os.makedirs(board_dir, exist_ok=True)

        app_boards_dir = os.path.join(self.test_dir, "boards")
        os.makedirs(app_boards_dir, exist_ok=True)

        board_defconfig = os.path.join(board_dir, "nrf52840dk_defconfig")
        with open(board_defconfig, "w") as f:
            f.write("CONFIG_BASE=y\n")

        rev_defconfig = os.path.join(board_dir, "nrf52840dk_1_0_0_defconfig")
        with open(rev_defconfig, "w") as f:
            f.write("CONFIG_REV=y\n")

        app_rev_conf = os.path.join(app_boards_dir, "nrf52840dk@1.0.0.conf")
        with open(app_rev_conf, "w") as f:
            f.write("CONFIG_APP_REV=y\n")

        os.environ["BOARD"] = "nrf52840dk"
        os.environ["BOARD_QUALIFIERS"] = "nrf52840"
        os.environ["BOARD_REVISION"] = "1.0.0"

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir)

        self.assertIn(board_defconfig, conf_files)
        self.assertIn(rev_defconfig, conf_files)
        self.assertIn(app_rev_conf, conf_files)
        # Verify order: base defconfig before revision defconfig, before app revision conf
        self.assertTrue(conf_files.index(board_defconfig) < conf_files.index(rev_defconfig))
        self.assertTrue(conf_files.index(rev_defconfig) < conf_files.index(app_rev_conf))

    def test_discover_overlays_none(self):
        app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(app_dir, exist_ok=True)
        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "")
        self.assertEqual(overlays, [])

    def test_discover_overlays_app_only(self):
        app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(app_dir, exist_ok=True)
        app_overlay = os.path.join(app_dir, "app.overlay")
        Path(app_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "")
        self.assertEqual(overlays, [app_overlay])

    def test_discover_overlays_board_only(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        os.makedirs(boards_dir, exist_ok=True)
        board_overlay = os.path.join(boards_dir, "board.overlay")
        Path(board_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "")
        self.assertEqual(overlays, [board_overlay])

    def test_discover_overlays_qualified_board(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        os.makedirs(boards_dir, exist_ok=True)

        board_overlay = os.path.join(boards_dir, "board.overlay")
        soc_overlay = os.path.join(boards_dir, "board_soc.overlay")
        Path(board_overlay).touch()
        Path(soc_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "/soc")
        self.assertEqual(overlays, [board_overlay, soc_overlay])

    def test_discover_overlays_with_revisions(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        board_dir = os.path.join(self.test_dir, "board_dir")
        board_rev_dir = os.path.join(board_dir, "revisions")
        os.makedirs(boards_dir, exist_ok=True)
        os.makedirs(board_rev_dir, exist_ok=True)

        board_rev_overlay = os.path.join(board_rev_dir, "1.0.0.overlay")
        app_board_overlay = os.path.join(boards_dir, "board.overlay")
        app_rev_overlay = os.path.join(boards_dir, "board@1.0.0.overlay")
        app_overlay = os.path.join(app_dir, "app.overlay")

        Path(board_rev_overlay).touch()
        Path(app_board_overlay).touch()
        Path(app_rev_overlay).touch()
        Path(app_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "soc", "1.0.0", board_dir)
        self.assertEqual(overlays, [board_rev_overlay, app_board_overlay, app_rev_overlay, app_overlay])

    def test_discover_overlays_all(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        os.makedirs(boards_dir, exist_ok=True)

        app_overlay = os.path.join(app_dir, "app.overlay")
        board_overlay = os.path.join(boards_dir, "board.overlay")
        soc_overlay = os.path.join(boards_dir, "board_soc.overlay")

        Path(app_overlay).touch()
        Path(board_overlay).touch()
        Path(soc_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "/soc")
        self.assertEqual(overlays, [board_overlay, soc_overlay, app_overlay])

    @patch('subprocess.run')
    def test_preprocess_dts_generates_input_c(self, mock_run):
        app_dir = os.path.join(self.test_dir, "app")
        board_dir = os.path.join(self.test_dir, "board")
        output_dir = os.path.join(self.test_dir, "out")
        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(board_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        base_dts = os.path.join(board_dir, "my_board.dts")
        Path(base_dts).touch()

        app_overlay = os.path.join(app_dir, "app.overlay")
        Path(app_overlay).touch()

        os.environ["BOARD"] = "my_board"
        os.environ["BOARD_QUALIFIERS"] = ""

        args = MagicMock()
        args.board = "my_board"
        args.app_dir = app_dir
        args.oot_dts_roots = []
        args.modules = []

        mock_run.return_value = MagicMock(returncode=0)

        merged_dts_path, dts_roots = kconfig_gen_values.preprocess_dts(
            args, str(self.zephyr_base), output_dir, board_dir
        )

        dts_input_path = os.path.join(output_dir, "dts_input.c")
        self.assertTrue(os.path.exists(dts_input_path))

        content = Path(dts_input_path).read_text()
        self.assertIn(f'#include "{os.path.abspath(base_dts)}"', content)
        self.assertIn(f'#include "{os.path.abspath(app_overlay)}"', content)

    @patch('subprocess.run')
    def test_generate_dts_headers(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        edt_pickle_path = os.path.join(output_dir, "edt.pickle")

        kconfig_gen_values.generate_dts_headers(
            str(self.zephyr_base), output_dir, edt_pickle_path
        )

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn(os.path.join(str(self.zephyr_base), "scripts", "dts", "gen_defines.py"), cmd)
        self.assertIn("--edt-pickle", cmd)
        self.assertIn(edt_pickle_path, cmd)
        self.assertIn("--header-out", cmd)
        self.assertIn(os.path.join(output_dir, "zephyr", "devicetree_generated.h"), cmd)

    def test_setup_environment_with_bzlmod_modules(self):
        args = MagicMock()
        args.board = "nrf52840dk"
        args.toolchain_variant = None
        # Bzlmod canonical name format for injected repos
        module_dir = os.path.join(self.test_dir, "external", "+_repo_rules+hal_nordic")
        os.makedirs(module_dir, exist_ok=True)
        args.modules = [module_dir]

        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)

        # Verify ZEPHYR_<MODULE>_MODULE_DIR is set correctly
        # 'hal_nordic+...' -> 'HAL_NORDIC'
        self.assertEqual(os.environ["ZEPHYR_HAL_NORDIC_MODULE_DIR"], os.path.abspath(module_dir))

        # Check if it was written to the env file
        kconfig_env_file = os.path.join(output_dir, "kconfig_module_dirs.env")
        self.assertTrue(os.path.exists(kconfig_env_file))
        content = Path(kconfig_env_file).read_text()
        self.assertIn(f"ZEPHYR_HAL_NORDIC_MODULE_DIR={os.path.abspath(module_dir)}", content)

    def test_generate_kconfig_aggregations_with_modules(self):
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")

        # Create soc.yml in Zephyr to ensure it is discovered
        (self.zephyr_base / "soc" / "nordic" / "nrf52" / "soc.yml").touch()

        # Create an OOT module with soc.yml
        module_dir = os.path.join(self.test_dir, "my_module")
        (Path(module_dir) / "soc" / "my_soc").mkdir(parents=True)
        (Path(module_dir) / "soc" / "my_soc" / "soc.yml").touch()
        (Path(module_dir) / "soc" / "my_soc" / "Kconfig.defconfig").write_text("config SOC_MY_SOC\n")
        (Path(module_dir) / "soc" / "my_soc" / "Kconfig").write_text("config SOC_MY_SOC\n")

        args = MagicMock()
        args.modules = [module_dir]

        os.environ["BOARD"] = "nrf52840dk"
        with patch('kconfig_utils.generate_aggregation_file') as mock_gen:
            kconfig_gen_values.generate_kconfig_aggregations(str(self.zephyr_base), args, output_dir, board_dir)

            # Verify that generate_aggregation_file was called with the OOT soc directory
            mock_gen.assert_any_call(
                os.path.join(output_dir, "soc", "Kconfig.defconfig"),
                [os.path.join(str(self.zephyr_base), "soc/nordic/nrf52"), os.path.join(module_dir, "soc/my_soc")],
                "SoC defconfigs"
            )

    @patch('subprocess.run')
    def test_preprocess_dts_deduplicates_roots(self, mock_run):
        app_dir = os.path.join(self.test_dir, "app")
        board_dir = os.path.join(self.test_dir, "board")
        output_dir = os.path.join(self.test_dir, "out")
        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(board_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        base_dts = os.path.join(board_dir, "my_board.dts")
        Path(base_dts).touch()

        os.environ["BOARD"] = "my_board"
        os.environ["BOARD_QUALIFIERS"] = ""

        args = MagicMock()
        args.board = "my_board"
        args.app_dir = app_dir
        # Duplicate roots
        args.oot_dts_roots = [self.test_dir, self.test_dir]
        args.modules = []

        mock_run.return_value = MagicMock(returncode=0)

        with patch('kconfig_gen_values.discover_overlays') as mock_overlays:
            mock_overlays.return_value = []
            merged_dts_path, dts_roots = kconfig_gen_values.preprocess_dts(
                args, str(self.zephyr_base), output_dir, board_dir
            )

        # Verify dts_roots has no duplicates
        self.assertEqual(dts_roots.count(Path(self.test_dir)), 1)

    @patch('subprocess.run')
    def test_generate_edt_pickle_resolves_and_deduplicates_bindings(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        os.makedirs(output_dir, exist_ok=True)

        # Create two paths that resolve to the same absolute path (via symlink or relative)
        dir1 = os.path.join(self.test_dir, "dir1")
        os.makedirs(os.path.join(dir1, "dts", "bindings"))

        # Relative path to dir1
        dir2 = os.path.join(self.test_dir, "out", "..", "dir1")

        dts_roots = [Path(dir1), Path(dir2)]

        kconfig_gen_values.generate_edt_pickle(
            str(self.zephyr_base), output_dir, dts_roots, "merged.dts"
        )

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]

        # Count occurrences of bindings dir in arguments
        resolved_bdir = str(Path(dir1).resolve() / "dts" / "bindings")
        bindings_args = [a for a in args if a == resolved_bdir]
        # Should be deduplicated
        self.assertEqual(len(bindings_args), 1)

if __name__ == '__main__':
    unittest.main()
