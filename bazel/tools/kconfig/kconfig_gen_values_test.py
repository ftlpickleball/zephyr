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


class _DummyDt:
    def __init__(self, filename, base_dir):
        self.filename = filename
        self._base_dir = base_dir


class _DummyBinding:
    def __init__(self, path, included_paths):
        self.path = path
        self._included_binding_paths = included_paths
        self.child_binding = None


class _DummyEdt:
    def __init__(self, dts_path, dt_filename, dt_base_dir, binding_path, included_paths):
        self.dts_path = dts_path
        self._dt = _DummyDt(dt_filename, dt_base_dir)
        self.bindings_dirs = []
        self._binding_paths = []
        self._binding_fname2path = {}
        self._compat2binding = {"vnd,foo": _DummyBinding(binding_path, included_paths)}
        self.nodes = []


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
        args.app_dir = os.path.join(self.test_dir, "app")
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)

        self.assertEqual(os.environ["BOARD"], "nrf52840dk")
        self.assertEqual(os.environ["BOARD_QUALIFIERS"], "nrf52840")
        self.assertEqual(os.environ["ARCH"], "*")
        self.assertEqual(os.environ["ZEPHYR_BASE"], str(self.zephyr_base))
        self.assertEqual(os.environ["APPLICATION_SOURCE_DIR"], os.path.abspath(args.app_dir))
        self.assertEqual(os.environ["KCONFIG_BOARD_DIR"], os.path.join(output_dir, "boards"))
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

    def test_setup_environment_bazel_platform_variants_resolve_to_zephyr_or_host(self):
        output_dir = os.path.join(self.test_dir, "out")
        os.makedirs(output_dir, exist_ok=True)

        for variant in ("gcc", "llvm"):
            args = MagicMock()
            args.board = "nrf52840dk/nrf52840"
            args.toolchain_variant = variant
            board_dir = os.path.join(self.test_dir, "board")
            kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)
            self.assertEqual(os.environ["ZEPHYR_TOOLCHAIN_VARIANT"], "zephyr")
            self.assertEqual(
                os.environ["TOOLCHAIN_KCONFIG_DIR"],
                os.path.join(str(self.zephyr_base), "cmake", "toolchain", "zephyr"),
            )

            args.board = "native_sim"
            board_dir = os.path.join(self.test_dir, "boards/native/native_sim")
            kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)
            self.assertEqual(os.environ["ZEPHYR_TOOLCHAIN_VARIANT"], "host")
            self.assertEqual(
                os.environ["TOOLCHAIN_KCONFIG_DIR"],
                os.path.join(str(self.zephyr_base), "cmake", "toolchain", "host"),
            )

    def test_setup_environment_default_board_revision(self):
        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "boards", "vendor", "target_board")
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(board_dir, exist_ok=True)
        board_yml = os.path.join(board_dir, "board.yml")
        with open(board_yml, "w", encoding="utf-8") as f:
            f.write(
                "boards:\n"
                "- name: target_board\n"
                "  revision:\n"
                "    format: custom\n"
                "    default: revC\n"
                "    revisions:\n"
                "      - name: revA\n"
                "      - name: revC\n"
            )

        args = MagicMock()
        args.board = "target_board/test_soc/cpu0"
        args.toolchain_variant = None
        args.app_dir = os.path.join(self.test_dir, "app")
        tracker = kconfig_utils.InputRecorder()

        kconfig_gen_values.setup_environment(
            args, str(self.zephyr_base), output_dir, board_dir, tracker=tracker
        )

        self.assertEqual(os.environ["BOARD"], "target_board")
        self.assertEqual(os.environ["BOARD_QUALIFIERS"], "test_soc/cpu0")
        self.assertEqual(os.environ["BOARD_REVISION"], "revC")
        self.assertIn(os.path.realpath(board_yml), tracker.files)

        explicit_tracker = kconfig_utils.InputRecorder()
        args.board = "target_board@revA/test_soc/cpu0"
        kconfig_gen_values.setup_environment(
            args,
            str(self.zephyr_base),
            output_dir,
            board_dir,
            tracker=explicit_tracker,
        )
        self.assertEqual(os.environ["BOARD_REVISION"], "revA")
        self.assertNotIn(os.path.realpath(board_yml), explicit_tracker.files)

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
                self.assertEqual(mock_pre.call_args.kwargs.get("rel_base_dir"), os.path.abspath(output_dir))

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
        self.assertEqual(overlays, [board_rev_overlay, app_board_overlay, app_rev_overlay])

    def test_discover_overlays_board_shadows_app_overlay(self):
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
        self.assertEqual(overlays, [board_overlay, soc_overlay])

    def test_discover_overlays_board_app_overlay_precedence(self):
        app_dir = os.path.join(self.test_dir, "app")
        boards_dir = os.path.join(app_dir, "boards")
        board_dir = os.path.join(self.test_dir, "board_dir")
        board_rev_dir = os.path.join(board_dir, "revisions")
        os.makedirs(boards_dir, exist_ok=True)
        os.makedirs(board_rev_dir, exist_ok=True)

        board_rev_overlay = os.path.join(board_rev_dir, "1.0.0.overlay")
        board_app_overlay = os.path.join(board_dir, "mcuboot.overlay")
        app_board_overlay = os.path.join(boards_dir, "board.overlay")
        app_overlay = os.path.join(app_dir, "app.overlay")

        Path(board_rev_overlay).touch()
        Path(board_app_overlay).touch()
        Path(app_board_overlay).touch()
        Path(app_overlay).touch()

        tracker = kconfig_utils.InputRecorder()
        overlays = kconfig_gen_values.discover_overlays(
            app_dir, "board", "soc", "1.0.0", board_dir, "mcuboot", tracker=tracker
        )
        self.assertEqual(overlays, [board_rev_overlay, board_app_overlay, app_board_overlay])
        self.assertIn(os.path.realpath(board_app_overlay), tracker.files)

        # Even without app_board_overlay, board_app_overlay should shadow app.overlay
        os.remove(app_board_overlay)
        overlays_no_app_board = kconfig_gen_values.discover_overlays(
            app_dir, "board", "soc", "1.0.0", board_dir, "mcuboot", tracker=kconfig_utils.InputRecorder()
        )
        self.assertEqual(overlays_no_app_board, [board_rev_overlay, board_app_overlay])

    def test_get_conf_files_board_app_conf_precedence(self):
        args = MagicMock()
        args.app_dir = os.path.join(self.test_dir, "app")
        args.app_name = "mcuboot"
        board_dir = os.path.join(self.test_dir, "board_dir")
        app_boards_dir = os.path.join(args.app_dir, "boards")
        os.makedirs(board_dir, exist_ok=True)
        os.makedirs(app_boards_dir, exist_ok=True)

        prj_conf = os.path.join(args.app_dir, "prj.conf")
        board_app_conf = os.path.join(board_dir, "mcuboot.conf")
        app_board_conf = os.path.join(app_boards_dir, "nrf52840dk.conf")
        Path(prj_conf).touch()
        Path(board_app_conf).touch()
        Path(app_board_conf).touch()

        tracker = kconfig_utils.InputRecorder()
        with patch.dict(os.environ, {"BOARD": "nrf52840dk", "BOARD_QUALIFIERS": "", "BOARD_REVISION": ""}):
            conf_files = kconfig_gen_values.get_conf_files(args, board_dir, tracker=tracker)

        self.assertEqual(conf_files, [prj_conf, board_app_conf, app_board_conf])
        self.assertIn(os.path.realpath(board_app_conf), tracker.files)

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
    def test_preprocess_dts_rel_base_dir_with_tmp_dir(self, mock_run):
        app_dir = os.path.join(self.test_dir, "app")
        board_dir = os.path.join(self.test_dir, "board")
        tmp_dir = os.path.join(self.test_dir, "tmp_work")
        repo_out_dir = os.path.join(self.test_dir, "ob", "external", "zc_app")
        sibling_mod_dir = os.path.join(self.test_dir, "ob", "external", "hal_mod+")
        for d in (app_dir, board_dir, tmp_dir, repo_out_dir, os.path.join(sibling_mod_dir, "dts")):
            os.makedirs(d, exist_ok=True)

        base_dts = os.path.join(board_dir, "my_board.dts")
        Path(base_dts).touch()
        sibling_dtsi = os.path.join(sibling_mod_dir, "dts", "soc.dtsi")
        Path(sibling_dtsi).touch()

        os.environ["BOARD"] = "my_board"
        os.environ["BOARD_QUALIFIERS"] = ""

        args = MagicMock()
        args.board = "my_board"
        args.app_dir = app_dir
        args.oot_dts_roots = []
        args.modules = [sibling_mod_dir]

        def fake_preprocessor(cmd_args):
            out_idx = cmd_args.index("-o") + 1
            out_path = cmd_args[out_idx]
            with open(out_path, "w") as f:
                f.write(f'#line 1 "{sibling_dtsi}"\n/dts-v1/;\n')
            mock_cpp = MagicMock()
            mock_cpp.include_times = []
            mock_cpp.probed_includes = []
            return mock_cpp
        self.pcmd_mock.CmdPreprocessor.side_effect = fake_preprocessor

        merged_dts_path, _ = kconfig_gen_values.preprocess_dts(
            args,
            str(self.zephyr_base),
            tmp_dir,
            board_dir,
            tracker=kconfig_utils.InputRecorder(),
            rel_base_dir=repo_out_dir,
        )

        dts_content = Path(merged_dts_path).read_text()
        expected_rel = os.path.join("..", "hal_mod+", "dts", "soc.dtsi")
        self.assertIn(f'#line 1 "{expected_rel}"', dts_content)
        self.assertNotIn(self.test_dir, dts_content)

    def test_normalize_edt_pickle_cleans_base_dir_and_included_bindings(self):
        checkout = os.path.join(self.test_dir, "checkout")
        output_dir = os.path.join(self.test_dir, "ob", "external", "zc_app")
        os.makedirs(checkout, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        Path(os.path.join(checkout, "MODULE.bazel")).touch()

        binding_file = os.path.join(checkout, "dts", "bindings", "foo.yaml")
        included_file = os.path.join(checkout, "dts", "bindings", "base.yaml")
        pickle_path = os.path.join(output_dir, "edt.pickle")

        import pickle
        edt = _DummyEdt(
            dts_path=os.path.join(self.test_dir, "tmp", "zephyr.dts"),
            dt_filename=os.path.join(self.test_dir, "tmp", "zephyr.dts"),
            dt_base_dir=os.path.join(self.test_dir, "tmp"),
            binding_path=binding_file,
            included_paths={included_file},
        )
        with open(pickle_path, "wb") as f:
            pickle.dump(edt, f, protocol=4)

        kconfig_gen_values._normalize_edt_pickle(pickle_path, str(self.zephyr_base), output_dir)

        with open(pickle_path, "rb") as f:
            cleaned = pickle.load(f)
        self.assertEqual(cleaned.dts_path, "zephyr.dts")
        self.assertEqual(cleaned._dt.filename, "zephyr.dts")
        self.assertEqual(cleaned._dt._base_dir, ".")
        self.assertEqual(cleaned._compat2binding["vnd,foo"].path, os.path.join("dts", "bindings", "foo.yaml"))
        self.assertEqual(
            cleaned._compat2binding["vnd,foo"]._included_binding_paths,
            {os.path.join("dts", "bindings", "base.yaml")},
        )

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

    def test_setup_environment_with_bazel_module_repo(self):
        args = MagicMock()
        args.board = "nrf52840dk"
        args.toolchain_variant = None
        # A bazel_dep module's repo is named "<module>+".
        module_dir = os.path.join(self.test_dir, "external", "hal_nordic+")
        os.makedirs(module_dir, exist_ok=True)
        args.modules = [module_dir]

        output_dir = os.path.join(self.test_dir, "out")
        board_dir = os.path.join(self.test_dir, "board")

        kconfig_gen_values.setup_environment(args, str(self.zephyr_base), output_dir, board_dir)

        self.assertEqual(os.environ["ZEPHYR_HAL_NORDIC_MODULE_DIR"], os.path.abspath(module_dir))

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

        # Verify dts_roots includes app_dir and board_dir and has no duplicates
        self.assertIn(Path(app_dir), dts_roots)
        self.assertIn(Path(board_dir), dts_roots)
        self.assertEqual(dts_roots.count(Path(self.test_dir)), 1)
        pcpp_args = self.pcmd_mock.CmdPreprocessor.call_args[0][0]
        self.assertIn("-D__DTS__=1", pcpp_args)

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

        def run_kconfig(cmd, **kwargs):
            if "--handwritten-input-configs" in cmd:
                idx = cmd.index("--handwritten-input-configs")
                config_out = cmd[idx + 2]
                autoconf_out = cmd[idx + 3]
                kconfig_list_out = cmd[idx + 4]
                os.makedirs(os.path.dirname(autoconf_out), exist_ok=True)
                Path(config_out).write_text("CONFIG_FOO=y\n")
                Path(autoconf_out).write_text("#define CONFIG_FOO 1\n")
                # kconfig.py lists every Kconfig file it parsed.
                Path(kconfig_list_out).write_text(f"{zephyr_kconfig}\n{app_kconfig}\n")
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
                self.assertEqual(mock_pre.call_args.kwargs.get("rel_base_dir"), os.path.abspath(output_dir))

        self.assertEqual(
            set(os.listdir(output_dir)),
            {"BUILD.bazel", ".config", "zephyr", "deps.txt", "dep_dirs.txt"},
        )

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
        ws_idx = cmd.index("--workspace-dir")
        self.assertEqual(cmd[ws_idx + 1], ".")
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

    def test_generate_bazel_build_filters_flags_by_kconfig_symbols_file(self):
        out_dir = os.path.join(self.test_dir, "out_filtered_flags")
        os.makedirs(out_dir, exist_ok=True)
        symbols_file = os.path.join(self.test_dir, "symbols.txt")
        Path(symbols_file).write_text("CONFIG_ALLOWED_SYM\n")

        def make_bool_sym(name, val):
            s = MagicMock()
            s.name = name
            s.str_value = val
            s.type = self.kconfig_mock.BOOL
            s.nodes = [MagicMock()]
            return s

        kconf = MagicMock()
        kconf.syms = {
            "ARCH_POSIX": MagicMock(str_value="y"),
            "SOC": MagicMock(str_value="inf_clock"),
        }
        kconf.unique_defined_syms = [
            make_bool_sym("ALLOWED_SYM", "y"),
            make_bool_sym("UNREFERENCED_SYM", "y"),
        ]

        args = MagicMock()
        args.app_dir = self.test_dir
        args.zephyr_base = str(self.zephyr_base)
        args.parent_platform = "@zephyr//boards/native/native_sim:native"
        args.kconfig_symbols_file = symbols_file

        kconfig_gen_values.generate_bazel_build(
            args, kconf, out_dir, self.kconfig_mock
        )

        build_content = Path(out_dir, "BUILD.bazel").read_text()
        self.assertIn(
            '"--@zephyr_kconfig//:CONFIG_ALLOWED_SYM=true"', build_content
        )
        self.assertNotIn("CONFIG_UNREFERENCED_SYM", build_content)

    def test_can_reuse_kconfig_dts(self):
        kconfig_dts = os.path.join(self.test_dir, "Kconfig.dts")
        Path(kconfig_dts).write_text("# Generated devicetree Kconfig\n")
        app_dir = os.path.join(self.test_dir, "app_reuse")
        board_dir = os.path.join(self.test_dir, "board_reuse")
        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(board_dir, exist_ok=True)
        (self.zephyr_base / "dts" / "bindings").mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.kconfig_dts_file = kconfig_dts
        args.app_dir = app_dir
        args.modules = []
        args.oot_dts_roots = []

        self.assertTrue(
            kconfig_gen_values._can_reuse_kconfig_dts(
                args, str(self.zephyr_base), board_dir
            )
        )

        # App with its own unshared dts/bindings cannot reuse shared Kconfig.dts
        os.makedirs(os.path.join(app_dir, "dts", "bindings"), exist_ok=True)
        self.assertFalse(
            kconfig_gen_values._can_reuse_kconfig_dts(
                args, str(self.zephyr_base), board_dir
            )
        )

        # If app_dir is also in oot_dts_roots, its bindings are already in shared Kconfig.dts
        args.oot_dts_roots = [app_dir]
        self.assertTrue(
            kconfig_gen_values._can_reuse_kconfig_dts(
                args, str(self.zephyr_base), board_dir
            )
        )

    def test_run_kconfig_in_process_evaluates_and_records_inputs(self):
        kconfigfunctions_mock = MagicMock()
        sys.modules["kconfigfunctions"] = kconfigfunctions_mock

        kconfig_root = str(self.zephyr_base / "Kconfig")
        conf_a = os.path.join(self.test_dir, "board_defconfig")
        conf_b = os.path.join(self.test_dir, "prj.conf")
        Path(conf_a).write_text("CONFIG_FOO=y\n")
        Path(conf_b).write_text("CONFIG_BAR=y\n")

        out_dir = os.path.join(self.test_dir, "out_in_proc")
        config_out = os.path.join(out_dir, ".config")
        autoconf_out = os.path.join(out_dir, "zephyr", "autoconf.h")

        mock_kconf = MagicMock()
        mock_kconf.srctree = str(self.zephyr_base)
        mock_kconf.kconfig_filenames = ["Kconfig", "arch/arm/Kconfig"]
        mock_kconf.warnings = []
        mock_kconf.y = MagicMock(tri_value=2)
        mock_kconf.syms = {}
        observed_edt = []

        def make_kconf(*_args, **_kwargs):
            observed_edt.append(kconfigfunctions_mock.edt)
            return mock_kconf

        self.kconfig_mock.Kconfig.side_effect = make_kconf

        def write_cfg(path):
            if path != os.devnull:
                Path(path).write_text("CONFIG_FOO=y\nCONFIG_BAR=y\n")

        def write_hdr(path):
            Path(path).write_text("#define CONFIG_FOO 1\n#define CONFIG_BAR 1\n")

        mock_kconf.write_config.side_effect = write_cfg
        mock_kconf.write_autoconf.side_effect = write_hdr

        dummy_edt = MagicMock()
        tracker = kconfig_utils.InputRecorder()
        kconf, _ = kconfig_gen_values.run_kconfig_in_process(
            str(self.zephyr_base),
            kconfig_root,
            [conf_a, conf_b],
            config_out,
            autoconf_out,
            tracker=tracker,
            edt=dummy_edt,
        )

        self.assertIs(kconf, mock_kconf)
        self.assertEqual(observed_edt, [dummy_edt])
        self.assertIsNone(kconfigfunctions_mock.edt)
        self.assertIsNone(kconfigfunctions_mock.edtlib)
        mock_kconf.load_config.assert_any_call(conf_a)
        mock_kconf.load_config.assert_any_call(conf_b, replace=False)
        self.kconfig_wrapper_mock.check_no_promptless_assign.assert_called_once_with(
            mock_kconf
        )
        self.kconfig_wrapper_mock.check_assigned_sym_values.assert_called_once_with(
            mock_kconf
        )
        self.kconfig_wrapper_mock.check_assigned_choice_values.assert_called_once_with(
            mock_kconf
        )
        self.assertTrue(os.path.isfile(config_out))
        self.assertTrue(os.path.isfile(autoconf_out))
        self.assertIn(os.path.realpath(kconfig_root), tracker.files)

        # Verify forced_input_configs ignores "set more than once" warnings
        self.kconfig_wrapper_mock.err.reset_mock()
        mock_kconf.warnings = ['warning: FOO (defined at Kconfig:1) was set more than once.']
        kconfig_gen_values.run_kconfig_in_process(
            str(self.zephyr_base),
            kconfig_root,
            [conf_a, conf_b],
            config_out,
            autoconf_out,
            tracker=tracker,
            edt=dummy_edt,
            forced_input_configs=True,
        )
        self.kconfig_wrapper_mock.err.assert_not_called()

    def test_generate_dts_headers_in_process_does_not_mutate_stdlib_pickle(self):
        import pickle as stdlib_pickle
        import types

        dts_dir = self.zephyr_base / "scripts" / "dts"
        dts_dir.mkdir(parents=True, exist_ok=True)
        gen_defines_py = dts_dir / "gen_defines.py"
        gen_defines_py.write_text("# stub\n")

        out_dir = os.path.join(self.test_dir, "out_dts_hdr")
        os.makedirs(out_dir, exist_ok=True)
        non_existent_pickle = os.path.join(out_dir, "missing_edt.pickle")

        orig_stdlib_load = stdlib_pickle.load
        dummy_edt = MagicMock()
        observed = {}

        fake_gen_defines = types.ModuleType("gen_defines")
        fake_gen_defines.pickle = stdlib_pickle

        def fake_main():
            observed["stdlib_load_during_main"] = stdlib_pickle.load
            observed["argv_during_main"] = list(sys.argv)
            with open(sys.argv[sys.argv.index("--edt-pickle") + 1], "rb") as f:
                observed["loaded_edt"] = fake_gen_defines.pickle.load(f)
            hdr_out = sys.argv[sys.argv.index("--header-out") + 1]
            Path(hdr_out).parent.mkdir(parents=True, exist_ok=True)
            Path(hdr_out).write_text("/* generated */\n")

        fake_gen_defines.main = fake_main

        tracker = kconfig_utils.InputRecorder()
        with patch.dict(sys.modules, {"gen_defines": fake_gen_defines}):
            kconfig_gen_values.generate_dts_headers(
                str(self.zephyr_base),
                out_dir,
                non_existent_pickle,
                tracker=tracker,
                edt=dummy_edt,
            )

        self.assertIs(observed["stdlib_load_during_main"], orig_stdlib_load)
        self.assertIs(observed["loaded_edt"], dummy_edt)
        self.assertIs(fake_gen_defines.pickle, stdlib_pickle)
        self.assertTrue(
            os.path.isfile(os.path.join(out_dir, "zephyr", "devicetree_generated.h"))
        )

    def _make_sb_kconf(self, values, user_values=None):
        user_values = user_values or {}
        syms = {}
        for name, val in values.items():
            sym = MagicMock()
            sym.str_value = val
            sym.user_value = user_values.get(name)
            syms[name] = sym
        sb_kconf = MagicMock()
        sb_kconf.syms = syms
        return sb_kconf

    def test_translate_sysbuild_kconfig_to_domain_bootloader_ram_load(self):
        sb_kconf = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "MCUBOOT_MODE_RAM_LOAD": "y",
            "MCUBOOT_MODE_RAM_LOAD_WITH_REVERT": "n",
            "BOOT_SIGNATURE_TYPE_RSA": "y",
        })
        lines = kconfig_gen_values.translate_sysbuild_kconfig_to_domain(sb_kconf, "BOOTLOADER")
        self.assertIn("CONFIG_BOOT_RAM_LOAD=y", lines)
        self.assertIn("# CONFIG_BOOT_RAM_LOAD_REVERT is not set", lines)
        self.assertIn("# CONFIG_BOOT_SWAP_USING_MOVE is not set", lines)
        self.assertIn("CONFIG_BOOT_SIGNATURE_TYPE_RSA=y", lines)
        self.assertNotIn("CONFIG_BOOTLOADER_MCUBOOT=y", lines)

    def test_translate_sysbuild_kconfig_to_domain_main_ram_load(self):
        sb_kconf = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "MCUBOOT_MODE_RAM_LOAD": "y",
            "MCUBOOT_MODE_RAM_LOAD_WITH_REVERT": "n",
            "MCUBOOT_RAMLOAD_ALLOW_XIP": "y",
        })
        lines = kconfig_gen_values.translate_sysbuild_kconfig_to_domain(sb_kconf, "MAIN")
        self.assertIn("CONFIG_BOOTLOADER_MCUBOOT=y", lines)
        self.assertIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_RAM_LOAD=y", lines)
        self.assertNotIn("CONFIG_MCUBOOT_BOOTLOADER_MODE_RAM_LOAD_WITH_REVERT=y", lines)
        self.assertNotIn("# CONFIG_XIP is not set", lines)

        # When MCUBOOT_RAMLOAD_ALLOW_XIP is n, XIP is disabled
        sb_kconf_no_xip = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "MCUBOOT_MODE_RAM_LOAD": "y",
            "MCUBOOT_RAMLOAD_ALLOW_XIP": "n",
        })
        lines_no_xip = kconfig_gen_values.translate_sysbuild_kconfig_to_domain(sb_kconf_no_xip, "MAIN")
        self.assertIn("# CONFIG_XIP is not set", lines_no_xip)
        self.assertIn("CONFIG_FLASH_SIZE=0", lines_no_xip)

    def test_boot_signature_key_file_kconfig_default_and_multi_key(self):
        # Default value from Kconfig.sysbuild (user_value is None) with comma-separated keys
        sb_kconf = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "BOOT_SIGNATURE_KEY_FILE": "key1.pem,key2.pem",
            "BOOT_ENCRYPTION": "y",
            "BOOT_ENCRYPTION_KEY_FILE": "enc.pem",
        })
        main_lines = kconfig_gen_values.translate_sysbuild_kconfig_to_domain(
            sb_kconf, "MAIN"
        )
        self.assertIn('CONFIG_MCUBOOT_SIGNATURE_KEY_FILE="key1.pem"', main_lines)
        self.assertIn('CONFIG_MCUBOOT_ENCRYPTION_KEY_FILE="enc.pem"', main_lines)

        boot_lines = kconfig_gen_values.translate_sysbuild_kconfig_to_domain(
            sb_kconf, "BOOTLOADER"
        )
        self.assertIn(
            'CONFIG_BOOT_SIGNATURE_KEY_FILE="key1.pem,key2.pem"', boot_lines
        )
        self.assertIn('CONFIG_BOOT_ENCRYPTION_KEY_FILE="enc.pem"', boot_lines)

    def test_generate_sysbuild_forced_config_bootloader_board_kconfig_sysbuild(self):
        sysbuild_dir = self.zephyr_base / "share" / "sysbuild"
        sysbuild_dir.mkdir(parents=True)
        (sysbuild_dir / "Kconfig").write_text("# dummy sysbuild Kconfig\n")

        board_dir = self.zephyr_base / "boards" / "arm" / "nrf52840dk"
        (board_dir / "Kconfig.sysbuild").write_text("choice MCUBOOT_MODE\n\tdefault MCUBOOT_MODE_RAM_LOAD\nendchoice\n")

        app_dir = os.path.join(self.test_dir, "mcuboot")
        os.makedirs(app_dir)
        output_dir = os.path.join(self.test_dir, "out")
        os.makedirs(output_dir)

        sb_kconf = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "MCUBOOT_MODE_RAM_LOAD": "y",
            "MCUBOOT_MODE_RAM_LOAD_WITH_REVERT": "n",
            "BOOT_SIGNATURE_TYPE_RSA": "y",
        })
        sb_kconf.kconfig_filenames = [str(sysbuild_dir / "Kconfig"), str(board_dir / "Kconfig.sysbuild")]
        self.kconfig_mock.Kconfig.return_value = sb_kconf

        args = MagicMock()
        args.app_dir = app_dir
        args.sysbuild_app_dir = None
        args.app_name = "mcuboot"
        args.forced_conf_fragments = []
        tracker = kconfig_utils.InputRecorder()

        with patch.dict(os.environ, {"BOARD": "nrf52840dk", "BOARD_QUALIFIERS": "", "BOARD_REVISION": ""}):
            forced_path = kconfig_gen_values.generate_sysbuild_forced_config(
                str(self.zephyr_base), args, output_dir, str(board_dir), tracker=tracker
            )

        self.assertEqual(forced_path, os.path.join(output_dir, ".config.sysbuild"))
        self.assertTrue(os.path.exists(forced_path))
        content = Path(forced_path).read_text()
        self.assertIn("CONFIG_BOOT_RAM_LOAD=y", content)
        self.assertIn("# CONFIG_BOOT_RAM_LOAD_REVERT is not set", content)
        sb_kconf.syms["BOOTLOADER_MCUBOOT"].set_value.assert_called_once_with("y")

    def test_generate_sysbuild_forced_config_bootloader_uses_parent_sysbuild_app_dir(self):
        sysbuild_dir = self.zephyr_base / "share" / "sysbuild"
        sysbuild_dir.mkdir(parents=True)
        (sysbuild_dir / "Kconfig").write_text("# dummy sysbuild Kconfig\n")

        board_dir = self.zephyr_base / "boards" / "arm" / "nrf52840dk"
        mcuboot_dir = os.path.join(self.test_dir, "mcuboot_repo")
        parent_app_dir = os.path.join(self.test_dir, "parent_app")
        os.makedirs(mcuboot_dir)
        os.makedirs(parent_app_dir)
        parent_kconfig_sb = os.path.join(parent_app_dir, "Kconfig.sysbuild")
        Path(parent_kconfig_sb).write_text(
            'source "share/sysbuild/Kconfig"\nconfig BOOT_SIGNATURE_KEY_FILE\n\tdefault "parent_key.pem"\n'
        )
        output_dir = os.path.join(self.test_dir, "out_parent_sb")
        os.makedirs(output_dir)

        sb_kconf = self._make_sb_kconf({
            "BOOTLOADER_MCUBOOT": "y",
            "BOOT_SIGNATURE_KEY_FILE": "parent_key.pem",
        })
        sb_kconf.srctree = str(self.zephyr_base)
        sb_kconf.kconfig_filenames = [parent_kconfig_sb]
        self.kconfig_mock.Kconfig.return_value = sb_kconf

        args = MagicMock()
        args.app_dir = mcuboot_dir
        args.sysbuild_app_dir = parent_app_dir
        args.app_name = "mcuboot"
        args.forced_conf_fragments = []
        tracker = kconfig_utils.InputRecorder()

        with patch.dict(
            os.environ,
            {"BOARD": "nrf52840dk", "BOARD_QUALIFIERS": "", "BOARD_REVISION": ""},
        ):
            forced_path = kconfig_gen_values.generate_sysbuild_forced_config(
                str(self.zephyr_base),
                args,
                output_dir,
                str(board_dir),
                tracker=tracker,
            )

        self.kconfig_mock.Kconfig.assert_called_with(
            parent_kconfig_sb, warn_to_stderr=False
        )
        content = Path(forced_path).read_text()
        self.assertIn('CONFIG_BOOT_SIGNATURE_KEY_FILE="parent_key.pem"', content)

    def test_generate_sysbuild_forced_config_in_tree_mcuboot_test_not_bootloader(self):
        sysbuild_dir = self.zephyr_base / "share" / "sysbuild"
        sysbuild_dir.mkdir(parents=True)
        (sysbuild_dir / "Kconfig").write_text("# dummy sysbuild Kconfig\n")

        board_dir = self.zephyr_base / "boards" / "arm" / "nrf52840dk"
        (board_dir / "Kconfig.sysbuild").write_text(
            "choice MCUBOOT_MODE\n\tdefault MCUBOOT_MODE_RAM_LOAD\nendchoice\n"
        )

        # An in-tree test under <zephyr_base>/tests/subsys/dfu/mcuboot has
        # app_name="mcuboot" and basename="mcuboot" but is a normal test app
        # (MAIN), not the MCUboot bootloader image.
        test_app_dir = self.zephyr_base / "tests" / "subsys" / "dfu" / "mcuboot"
        test_app_dir.mkdir(parents=True)
        output_dir = os.path.join(self.test_dir, "out_dfu_test")
        os.makedirs(output_dir)
        soc_out_dir = os.path.join(output_dir, "soc")
        os.makedirs(soc_out_dir)
        Path(os.path.join(soc_out_dir, "Kconfig.sysbuild")).write_text(
            'osource "/some/soc/Kconfig.sysbuild"\n'
        )

        args = MagicMock()
        args.app_dir = str(test_app_dir)
        args.sysbuild_app_dir = None
        args.app_name = "mcuboot"
        args.forced_conf_fragments = []
        tracker = kconfig_utils.InputRecorder()

        with patch.dict(
            os.environ,
            {"BOARD": "nrf52840dk", "BOARD_QUALIFIERS": "", "BOARD_REVISION": ""},
        ):
            forced_path = kconfig_gen_values.generate_sysbuild_forced_config(
                str(self.zephyr_base),
                args,
                output_dir,
                str(board_dir),
                tracker=tracker,
            )

        self.assertIsNone(forced_path)


if __name__ == '__main__':
    unittest.main()
