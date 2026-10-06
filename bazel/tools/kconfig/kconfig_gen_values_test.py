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
        # A mock module is not a package: submodules must be mocked too.
        self.pcmd_mock = MagicMock()
        sys.modules['pcpp.pcmd'] = self.pcmd_mock

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

        # Verify deps.txt and dep_dirs.txt were generated
        self.assertTrue(os.path.exists(os.path.join(output_dir, "deps.txt")))
        self.assertTrue(os.path.exists(os.path.join(output_dir, "dep_dirs.txt")))

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

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir, tracker=kconfig_utils.InputRecorder())

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

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir, tracker=kconfig_utils.InputRecorder())

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

        conf_files = kconfig_gen_values.get_conf_files(args, board_dir, tracker=kconfig_utils.InputRecorder())

        self.assertIn(board_defconfig, conf_files)
        self.assertIn(rev_defconfig, conf_files)
        self.assertIn(app_rev_conf, conf_files)
        # Verify order: base defconfig before revision defconfig, before app revision conf
        self.assertTrue(conf_files.index(board_defconfig) < conf_files.index(rev_defconfig))
        self.assertTrue(conf_files.index(rev_defconfig) < conf_files.index(app_rev_conf))

    def test_discover_overlays_none(self):
        app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(app_dir, exist_ok=True)
        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "", tracker=kconfig_utils.InputRecorder())
        self.assertEqual(overlays, [])

    def test_discover_overlays_app_only(self):
        app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(app_dir, exist_ok=True)
        app_overlay = os.path.join(app_dir, "app.overlay")
        Path(app_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "", tracker=kconfig_utils.InputRecorder())
        self.assertEqual(overlays, [app_overlay])

    def test_discover_overlays_board_only(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        os.makedirs(boards_dir, exist_ok=True)
        board_overlay = os.path.join(boards_dir, "board.overlay")
        Path(board_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "", tracker=kconfig_utils.InputRecorder())
        self.assertEqual(overlays, [board_overlay])

    def test_discover_overlays_qualified_board(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        os.makedirs(boards_dir, exist_ok=True)

        board_overlay = os.path.join(boards_dir, "board.overlay")
        soc_overlay = os.path.join(boards_dir, "board_soc.overlay")
        Path(board_overlay).touch()
        Path(soc_overlay).touch()

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "/soc", tracker=kconfig_utils.InputRecorder())
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

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "soc", "1.0.0", board_dir, tracker=kconfig_utils.InputRecorder())
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

        overlays = kconfig_gen_values.discover_overlays(app_dir, "board", "/soc", tracker=kconfig_utils.InputRecorder())
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

        abs_dts_path = os.path.join(self.test_dir, "some_included.dts")
        def fake_preprocessor(cmd_args):
            out_idx = cmd_args.index("-o") + 1
            out_path = cmd_args[out_idx]
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "w") as f:
                f.write(f'#line 1 "{abs_dts_path}"\n/dts-v1/;\n#line 10 "rel_file.dtsi"\n')
            mock_cpp = MagicMock()
            mock_cpp.include_times = []
            mock_cpp.probed_includes = []
            return mock_cpp
        self.pcmd_mock.CmdPreprocessor.side_effect = fake_preprocessor

        merged_dts_path, dts_roots = kconfig_gen_values.preprocess_dts(
            args, str(self.zephyr_base), output_dir, board_dir, tracker=kconfig_utils.InputRecorder()
        )

        dts_input_path = os.path.join(output_dir, "dts_input.c")
        self.assertTrue(os.path.exists(dts_input_path))

        content = Path(dts_input_path).read_text()
        self.assertIn(f'#include "{os.path.relpath(base_dts, output_dir)}"', content)
        self.assertIn(f'#include "{os.path.relpath(app_overlay, output_dir)}"', content)
        self.assertNotIn(self.test_dir, content)

        # Verify zephyr.dts #line directives were relativized
        self.assertTrue(os.path.exists(merged_dts_path))
        dts_content = Path(merged_dts_path).read_text()
        rel_dts_path = os.path.relpath(abs_dts_path, output_dir)
        self.assertIn(f'#line 1 "{rel_dts_path}"', dts_content)
        self.assertIn('#line 10 "rel_file.dtsi"', dts_content)
        self.assertNotIn(self.test_dir, dts_content)

    @patch('subprocess.run')
    def test_generate_dts_headers(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        edt_pickle_path = os.path.join(output_dir, "edt.pickle")

        kconfig_gen_values.generate_dts_headers(
            str(self.zephyr_base), output_dir, edt_pickle_path, tracker=kconfig_utils.InputRecorder()
        )

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn(os.path.join(str(self.zephyr_base), "scripts", "dts", "gen_defines.py"), cmd)
        self.assertIn("--edt-pickle", cmd)
        self.assertIn(os.path.relpath(edt_pickle_path, output_dir), cmd)
        self.assertIn("--header-out", cmd)
        self.assertIn(os.path.relpath(os.path.join(output_dir, "zephyr", "devicetree_generated.h"), output_dir), cmd)
        self.assertEqual(kwargs.get("cwd"), output_dir)

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

        tracker = kconfig_utils.InputRecorder()
        os.environ["BOARD"] = "nrf52840dk"
        with patch('kconfig_utils.generate_aggregation_file') as mock_gen:
            kconfig_gen_values.generate_kconfig_aggregations(str(self.zephyr_base), args, output_dir, board_dir, tracker=tracker)

            # Verify that generate_aggregation_file was called with the OOT soc directory
            mock_gen.assert_any_call(
                os.path.join(output_dir, "soc", "Kconfig.defconfig"),
                [os.path.join(str(self.zephyr_base), "soc/nordic/nrf52"), os.path.join(module_dir, "soc/my_soc")],
                "SoC defconfigs",
                tracker=tracker,
            )
            mock_gen.assert_any_call(
                os.path.join(output_dir, "boards", "Kconfig.nrf52840dk"),
                [board_dir],
                "Board v2 Kconfigs",
                tracker=tracker,
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
                args, str(self.zephyr_base), output_dir, board_dir, tracker=kconfig_utils.InputRecorder()
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
            str(self.zephyr_base), output_dir, dts_roots, "merged.dts", tracker=kconfig_utils.InputRecorder()
        )

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]

        # Count occurrences of bindings dir in arguments
        rel_bdir = os.path.relpath(str(Path(dir1).resolve() / "dts" / "bindings"), output_dir)
        bindings_args = [a for a in cmd if a == rel_bdir]
        # Should be deduplicated and relative to output_dir
        self.assertEqual(len(bindings_args), 1)
        self.assertFalse(os.path.isabs(rel_bdir))
        self.assertEqual(kwargs.get("cwd"), output_dir)

    @patch('subprocess.run')
    def test_main_writes_deps(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(app_dir)
        app_kconfig = os.path.join(app_dir, "Kconfig")
        Path(app_kconfig).write_text('source "Kconfig.zephyr"\n')
        board_dir = self.zephyr_base / "boards" / "arm" / "nrf52840dk"
        (board_dir / "board.yml").write_text("board:\n  name: nrf52840dk\n")
        (self.zephyr_base / "soc" / "nordic" / "nrf52" / "soc.yml").touch()
        zephyr_kconfig = str(self.zephyr_base / "Kconfig")

        def run_kconfig(*args, **kwargs):
            os.makedirs(os.path.join(output_dir, "zephyr"), exist_ok=True)
            Path(output_dir, ".config").write_text("CONFIG_FOO=y\n")
            Path(output_dir, "zephyr", "autoconf.h").write_text("#define CONFIG_FOO 1\n")
            # kconfig.py lists every Kconfig file it parsed.
            Path(output_dir, "kconfig_list.txt").write_text(f"{zephyr_kconfig}\n{app_kconfig}\n")
            return MagicMock(returncode=0, stderr="")
        mock_run.side_effect = run_kconfig
        self.kconfig_mock.Kconfig.return_value.unique_defined_syms = []

        with patch('sys.argv', [
            'kconfig_gen_values.py',
            '--zephyr-base', str(self.zephyr_base),
            '--app-dir', app_dir,
            '--board', 'nrf52840dk',
            '--board-dir', str(board_dir),
            '--parent-platform', '//platforms:test',
            '--output-dir', output_dir,
        ]):
            with patch('kconfig_utils.generate_kconfig_dts'), \
                 patch('kconfig_gen_values.preprocess_dts') as mock_pre, \
                 patch('kconfig_gen_values.generate_edt_pickle'):
                mock_pre.return_value = ("merged.dts", [])
                kconfig_gen_values.main()

        real = os.path.realpath
        deps = Path(output_dir, "deps.txt").read_text().splitlines()
        dep_dirs = Path(output_dir, "dep_dirs.txt").read_text().splitlines()
        for lines in (deps, dep_dirs):
            self.assertEqual(lines, sorted(set(lines)))
            self.assertTrue(all(p == real(p) for p in lines))
            self.assertFalse([p for p in lines if (p + os.sep).startswith(real(output_dir) + os.sep)])

        self.assertIn(real(zephyr_kconfig), deps)
        self.assertIn(real(app_kconfig), deps)
        # Candidates that don't exist: creating app/boards/ with it adds a fragment.
        self.assertIn(real(os.path.join(app_dir, "boards", "nrf52840dk.conf")), deps)
        for path in [
            os.path.join(app_dir, "prj.conf"),
            str(board_dir / "board.yml"),
            str(board_dir / "Kconfig"),
            str(self.zephyr_base / "soc" / "nordic" / "nrf52" / "soc.yml"),
            str(self.zephyr_base / "scripts" / "kconfig" / "kconfig.py"),
            kconfig_gen_values.__file__,
            kconfig_utils.__file__,
        ]:
            self.assertIn(real(path), deps)
        # Directories walked for soc.yml files (scoped to soc/) and listed for arch/ Kconfigs.
        for path in [self.zephyr_base / "soc", self.zephyr_base / "soc" / "nordic" / "nrf52", self.zephyr_base / "arch"]:
            self.assertIn(real(str(path)), dep_dirs)
        self.assertNotIn(real(str(self.zephyr_base)), dep_dirs)

    def test_preprocess_dts_records_include_probes(self):
        board_dir = os.path.join(self.test_dir, "board")
        app_dir = os.path.join(self.test_dir, "app")
        output_dir = os.path.join(self.test_dir, "out")
        oot_root = os.path.join(self.test_dir, "oot")
        zephyr_base = str(self.zephyr_base)
        for d in [board_dir, app_dir, os.path.join(oot_root, "dts"),
                  os.path.join(zephyr_base, "dts", "common"), os.path.join(zephyr_base, "include", "zephyr")]:
            os.makedirs(d, exist_ok=True)
        Path(board_dir, "my_board.dts").write_text(
            '/dts-v1/;\n#include <common.dtsi>\n#include "local.dtsi"\n/ { model = "test"; };\n'
        )
        Path(board_dir, "local.dtsi").write_text("/ { local_node {}; };\n")
        Path(zephyr_base, "dts", "common", "common.dtsi").write_text("/ { common_node {}; };\n")
        extra_overlay = os.path.join(self.test_dir, "extra.overlay")
        Path(extra_overlay).write_text("/ { extra_node {}; };\n")

        args = MagicMock()
        args.board = "my_board"
        args.app_dir = app_dir
        args.oot_dts_roots = [oot_root]
        args.modules = []
        args.dtc_overlays = [extra_overlay]
        tracker = kconfig_utils.InputRecorder()

        with patch.dict(sys.modules), \
             patch.dict(os.environ, {"BOARD": "my_board", "BOARD_QUALIFIERS": "", "BOARD_REVISION": ""}):
            # Preprocess with the real pcpp rather than setUp's mocks.
            for name in [n for n in sys.modules if n == "pcpp" or n.startswith("pcpp.")]:
                del sys.modules[name]
            try:
                import pcpp.pcmd  # noqa: F401
            except ImportError:
                self.skipTest("pcpp is not available")
            merged_dts_path, _ = kconfig_gen_values.preprocess_dts(args, zephyr_base, output_dir, board_dir, tracker=tracker)

        merged = Path(merged_dts_path).read_text()
        self.assertIn("common_node", merged)
        self.assertIn("local_node", merged)
        self.assertIn("extra_node", merged)

        real = os.path.realpath
        deps = tracker.files
        # Every path tried for <common.dtsi>, in -I order: creating one of them
        # would shadow the header found now.
        for path in [
            os.path.join(oot_root, "dts", "common.dtsi"),
            os.path.join(zephyr_base, "include", "common.dtsi"),
            os.path.join(zephyr_base, "include", "zephyr", "common.dtsi"),
            os.path.join(zephyr_base, "dts", "common.dtsi"),
        ]:
            self.assertIn(real(path), deps)
        for path in [
            os.path.join(zephyr_base, "dts", "common", "common.dtsi"),
            os.path.join(board_dir, "local.dtsi"),
            os.path.join(board_dir, "my_board.dts"),
            extra_overlay,
        ]:
            self.assertIn(real(path), deps)
        # Missing include dirs (creating one adds an include path) and board.yml probes.
        for path in [
            os.path.join(oot_root, "include"),
            os.path.join(oot_root, "dts", "arm"),
            os.path.join(zephyr_base, "dts", "vendor"),
            os.path.join(board_dir, "board.yml"),
            os.path.join(board_dir, "board.yaml"),
        ]:
            self.assertIn(real(path), deps)

    def test_get_conf_files_records_missing_candidates(self):
        args = MagicMock()
        args.app_dir = os.path.join(self.test_dir, "app")
        os.makedirs(args.app_dir)
        board_dir = os.path.join(self.test_dir, "board")
        os.makedirs(board_dir)
        tracker = kconfig_utils.InputRecorder()

        with patch.dict(os.environ, {"BOARD": "nrf52840dk", "BOARD_QUALIFIERS": "nrf52840", "BOARD_REVISION": "1.0.0"}):
            self.assertEqual(kconfig_gen_values.get_conf_files(args, board_dir, tracker=tracker), [])

        real = os.path.realpath
        deps = tracker.files
        # app/boards/ doesn't exist; creating it with one of these adds a fragment.
        for name in ["nrf52840dk.conf", "nrf52840dk_nrf52840.conf", "nrf52840dk@1.0.0.conf"]:
            path = os.path.join(args.app_dir, "boards", name)
            self.assertIn(real(path), deps)
        for path in [
            os.path.join(board_dir, "nrf52840dk_defconfig"),
            os.path.join(board_dir, "revisions", "1_0_0_defconfig"),
            os.path.join(board_dir, "nrf52840dk_nrf52840_1_0_0_defconfig"),
            os.path.join(args.app_dir, "prj.conf"),
            os.path.join(args.app_dir, "Kconfig"),
        ]:
            self.assertIn(real(path), deps)

    def test_discover_overlays_records_missing_candidates(self):
        app_dir = os.path.join(self.test_dir, "app")
        board_dir = os.path.join(self.test_dir, "board_dir")
        os.makedirs(app_dir)
        os.makedirs(board_dir)
        tracker = kconfig_utils.InputRecorder()

        self.assertEqual(kconfig_gen_values.discover_overlays(app_dir, "board", "soc", "1.0.0", board_dir, tracker=tracker), [])

        real = os.path.realpath
        deps = tracker.files
        for name in ["board.overlay", "board_soc.overlay", "board_soc@1.0.0.overlay"]:
            path = os.path.join(app_dir, "boards", name)
            self.assertIn(real(path), deps)
        for path in [
            os.path.join(board_dir, "revisions", "1_0_0.overlay"),
            os.path.join(board_dir, "board_soc_1_0_0.overlay"),
            os.path.join(app_dir, "app.overlay"),
        ]:
            self.assertIn(real(path), deps)

    @patch('subprocess.run')
    def test_generate_edt_pickle_records_inputs(self, mock_run):
        output_dir = os.path.join(self.test_dir, "out")
        scripts_dts = self.zephyr_base / "scripts" / "dts"
        package = scripts_dts / "python-devicetree" / "src" / "devicetree"
        package.mkdir(parents=True)
        (scripts_dts / "gen_edt.py").touch()
        (package / "edtlib.py").touch()
        bindings = self.zephyr_base / "dts" / "bindings"
        (bindings / "vendor").mkdir(parents=True)
        (bindings / "vendor" / "foo.yaml").touch()
        (bindings / "vendor" / "notes.txt").touch()
        (bindings / "vendor-prefixes.txt").touch()
        oot_root = Path(self.test_dir) / "oot"
        oot_root.mkdir()

        tracker = kconfig_utils.InputRecorder()
        kconfig_gen_values.generate_edt_pickle(
            str(self.zephyr_base), output_dir, [oot_root, self.zephyr_base], "merged.dts", tracker=tracker
        )

        cmd = mock_run.call_args[0][0]
        self.assertIn(str(scripts_dts / "gen_edt.py"), cmd)
        real = lambda p: os.path.realpath(str(p))
        self.assertLessEqual({
            real(bindings / "vendor" / "foo.yaml"),
            real(bindings / "vendor-prefixes.txt"),
            real(scripts_dts / "gen_edt.py"),
            real(scripts_dts / "edtlib_logger.py"),
            real(package / "edtlib.py"),
            # Creating these would add or switch a bindings dir.
            real(oot_root / "zephyr" / "dts" / "bindings"),
            real(oot_root / "dts" / "bindings"),
            real(self.zephyr_base / "zephyr" / "dts" / "bindings"),
        }, tracker.files)
        self.assertNotIn(real(bindings / "vendor" / "notes.txt"), tracker.files)
        self.assertEqual(tracker.dirs, {real(bindings), real(bindings / "vendor")})

    def test_generate_kconfig_aggregations_records_inputs(self):
        board_dir = str(self.zephyr_base / "boards" / "arm" / "nrf52840dk")
        soc_dir = self.zephyr_base / "soc" / "nordic" / "nrf52"
        (soc_dir / "soc.yml").touch()
        (soc_dir / "Kconfig.soc").touch()
        (self.zephyr_base / "arch" / "arm" / "Kconfig").touch()
        Path(board_dir, "Kconfig.nrf52840dk").touch()
        missing_module = os.path.join(self.test_dir, "missing_module")
        args = MagicMock()
        args.modules = [missing_module]

        tracker = kconfig_utils.InputRecorder()
        output_dir = os.path.join(self.test_dir, "out")
        with patch.dict(os.environ, {"BOARD": "nrf52840dk"}):
            kconfig_gen_values.generate_kconfig_aggregations(
                str(self.zephyr_base), args, output_dir, board_dir, tracker=tracker
            )

        real = lambda p: os.path.realpath(str(p))
        self.assertLessEqual({
            real(soc_dir / "soc.yml"),
            real(soc_dir / "Kconfig.soc"),
            real(soc_dir / "Kconfig.defconfig"),  # Probed, missing.
            real(self.zephyr_base / "arch" / "arm" / "Kconfig"),
            real(os.path.join(board_dir, "Kconfig")),  # Probed, missing.
            real(os.path.join(board_dir, "Kconfig.nrf52840dk")),
            real(self.zephyr_base / "modules"),  # Missing: no Kconfig.modules entries.
            real(os.path.join(missing_module, "soc")),
        }, tracker.files)
        self.assertLessEqual({
            real(self.zephyr_base / "soc"),
            real(self.zephyr_base / "soc" / "nordic"),
            real(soc_dir),
            real(self.zephyr_base / "arch"),
        }, tracker.dirs)
        self.assertNotIn(real(self.zephyr_base), tracker.dirs)

if __name__ == '__main__':
    unittest.main()
