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
import kconfig_gen_symbols
import kconfig_utils


class TestKconfigGenSymbols(unittest.TestCase):
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

        # Create some Kconfig files
        (self.zephyr_base / "Kconfig").write_text(
            'mainmenu "Test"\nsource "arch/Kconfig"\n'
        )
        (self.zephyr_base / "arch" / "Kconfig").write_text(
            'config ARCH_ARM\n  bool "ARM"\n'
        )
        (self.zephyr_base / "soc" / "nordic" / "nrf52" / "soc.yml").touch()
        (self.zephyr_base / "soc" / "nordic" / "nrf52" / "Kconfig").write_text(
            'config SOC_NRF52840\n  bool "nRF52840"\n'
        )
        (self.zephyr_base / "boards" / "arm" / "nrf52840dk" / "board.yml").write_text(
            "boards:\n  - name: nrf52840dk\n"
        )
        (self.zephyr_base / "boards" / "arm" / "nrf52840dk" / "Kconfig").write_text(
            'config BOARD_NRF52840DK\n  bool "nRF52840DK"\n'
        )

        # Mock kconfiglib
        self.kconfig_mock = MagicMock()
        sys.modules["kconfiglib"] = self.kconfig_mock

        # Default mock for Kconfig
        self.mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = self.mock_kconf
        self.mock_kconf.warnings = []

        # Mock ProcessPoolExecutor to execute synchronously in tests
        class DummyFuture:
            def __init__(self, result_val):
                self._result = result_val

            def result(self):
                return self._result

        class DummyProcessPoolExecutor:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def submit(self, fn, *args, **kwargs):
                return DummyFuture(fn(*args, **kwargs))

        self.executor_patcher = patch(
            "kconfig_gen_symbols.ProcessPoolExecutor", DummyProcessPoolExecutor
        )
        self.executor_patcher.start()

    def tearDown(self):
        self.executor_patcher.stop()
        shutil.rmtree(self.test_dir)

    def test_find_soc_source_directories(self):
        dirs = kconfig_gen_symbols.find_soc_source_directories(str(self.zephyr_base))
        self.assertTrue(any("nordic/nrf52" in d for d in dirs))

        # Test with OOT modules
        module_dir = os.path.join(self.test_dir, "my_module")
        (Path(module_dir) / "soc" / "my_soc").mkdir(parents=True)
        (Path(module_dir) / "soc" / "my_soc" / "soc.yml").touch()

        dirs_with_mods = kconfig_gen_symbols.find_soc_source_directories(
            str(self.zephyr_base), [module_dir]
        )
        self.assertTrue(any("nordic/nrf52" in d for d in dirs_with_mods))
        self.assertTrue(any("my_module/soc/my_soc" in d for d in dirs_with_mods))

    def test_find_board_source_directories(self):
        dirs = kconfig_gen_symbols.find_board_source_directories(
            [str(self.zephyr_base / "boards")]
        )
        self.assertTrue(any("nrf52840dk" in d for d in dirs))

    def test_discover_board_variants_yaml(self):
        # 1. Test singular 'board'
        board_dir_1 = Path(self.test_dir) / "board1"
        board_dir_1.mkdir()
        (board_dir_1 / "board.yml").write_text("""
board:
  name: test_board_1
  socs:
    - name: nrf52840
""")

        # 2. Test plural 'boards'
        board_dir_2 = Path(self.test_dir) / "board2"
        board_dir_2.mkdir()
        (board_dir_2 / "board.yml").write_text("""
boards:
  - name: test_board_2
    socs:
      - name: stm32f405
  - name: test_board_3
    socs:
      - name: esp32
""")

        # 3. Test board with revisions (dict containing revisions list)
        board_dir_3 = Path(self.test_dir) / "board3"
        board_dir_3.mkdir()
        (board_dir_3 / "board.yml").write_text("""
board:
  name: test_board_3_rev
  revision:
    revisions:
      - name: 1.0.0
  socs:
    - name: nrf52840
""")

        # 4. Test board with revision as a top-level list
        board_dir_4 = Path(self.test_dir) / "board4"
        board_dir_4.mkdir()
        (board_dir_4 / "board.yml").write_text("""
board:
  name: test_board_4_rev_list
  revision:
    - name: 2.0.0
  socs:
    - name: nrf52840
""")

        # 5. Test board with plural top-level revisions list
        board_dir_5 = Path(self.test_dir) / "board5"
        board_dir_5.mkdir()
        (board_dir_5 / "board.yml").write_text("""
board:
  name: test_board_5_plural
  revisions:
    - name: 3.0.0
  socs:
    - name: nrf52840
""")

        soc_to_clusters = {"nrf52840": ["cpu0"]}
        symbols = {}

        kconfig_gen_symbols.discover_board_variants(
            [str(board_dir_1), str(board_dir_2), str(board_dir_3), str(board_dir_4), str(board_dir_5)], soc_to_clusters, symbols
        )

        self.assertIn("CONFIG_BOARD_TEST_BOARD_1_NRF52840", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_1_NRF52840_CPU0", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_2_STM32F405", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_3_ESP32", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_3_REV_1_0_0", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_3_REV_NRF52840_1_0_0", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_3_REV_NRF52840_CPU0_1_0_0", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_4_REV_LIST_2_0_0", symbols)
        self.assertIn("CONFIG_BOARD_TEST_BOARD_5_PLURAL_3_0_0", symbols)

    @patch("kconfig_utils.generate_kconfig_dts")
    def test_main_execution(self, mock_gen_dts):
        output_file = os.path.join(self.test_dir, "BUILD.bazel")

        # Mock kconfiglib behavior
        mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = mock_kconf
        mock_kconf.warnings = []

        # Define some symbols
        sym1 = MagicMock()
        sym1.type = 2  # BOOL
        sym1.name = "MY_SYMBOL"

        sym2 = MagicMock()
        sym2.type = 4  # INT
        sym2.name = "MY_INT"

        mock_kconf.syms = {"MY_SYMBOL": sym1, "MY_INT": sym2}

        # Set kconfiglib constants
        self.kconfig_mock.UNKNOWN = 0
        self.kconfig_mock.INT = 4
        self.kconfig_mock.HEX = 5
        self.kconfig_mock.STRING = 6

        # Run main
        with patch(
            "sys.argv",
            [
                "kconfig_gen_symbols.py",
                "--zephyr-base",
                str(self.zephyr_base),
                "--output",
                output_file,
            ],
        ):
            kconfig_gen_symbols.main()

        # Verify kconfiglib was called
        self.kconfig_mock.Kconfig.assert_called()
        content = Path(output_file).read_text()
        self.assertIn('bool_flag(name = "CONFIG_MY_SYMBOL"', content)
        self.assertIn('int_flag(name = "CONFIG_MY_INT"', content)

    @patch("kconfig_utils.generate_kconfig_dts")
    def test_logging_template_fallback(self, mock_gen_dts):
        app_dir = Path(self.test_dir) / "app"
        app_dir.mkdir()
        (app_dir / "Kconfig").write_text(
            'module = MY_APP\nsource "subsys/logging/Kconfig.template.log_config"'
        )

        output_file = os.path.join(self.test_dir, "BUILD.bazel")
        self.kconfig_mock.Kconfig.return_value.syms = {}

        with patch(
            "sys.argv",
            [
                "kconfig_gen_symbols.py",
                "--zephyr-base",
                str(self.zephyr_base),
                "--modules",
                str(app_dir),
                "--output",
                output_file,
            ],
        ):
            kconfig_gen_symbols.main()

        content = Path(output_file).read_text()
        self.assertIn("CONFIG_MY_APP_LOG_LEVEL", content)

    @patch("kconfig_utils.generate_kconfig_dts")
    @patch("kconfig_gen_symbols.find_soc_source_directories")
    @patch("kconfig_gen_symbols.find_board_source_directories")
    def test_main_smoke(self, mock_find_board, mock_find_soc, mock_gen_dts):
        # Smoke test to ensure no NameErrors in main
        output_file = os.path.join(self.test_dir, "BUILD.bazel")
        mock_find_soc.return_value = []
        mock_find_board.return_value = []

        # Mock kconfiglib behavior
        mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = mock_kconf
        mock_kconf.warnings = []
        mock_kconf.syms = {}

        with patch(
            "sys.argv",
            [
                "kconfig_gen_symbols.py",
                "--zephyr-base",
                str(self.zephyr_base),
                "--output",
                output_file,
            ],
        ):
            kconfig_gen_symbols.main()

    @patch("kconfig_utils.generate_kconfig_dts")
    def test_warnings_not_fatal(self, mock_gen_dts):
        output_file = os.path.join(self.test_dir, "BUILD.bazel")

        # Mock kconfiglib to produce warnings
        mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = mock_kconf
        mock_kconf.warnings = ["Warning 1", "Warning 2"]
        mock_kconf.syms = {}

        with patch(
            "sys.argv",
            [
                "kconfig_gen_symbols.py",
                "--zephyr-base",
                str(self.zephyr_base),
                "--output",
                output_file,
            ],
        ):
            kconfig_gen_symbols.main()

        # Verify that it completed and generated warnings file
        output_dir = os.path.dirname(os.path.abspath(output_file))
        warnings_file = os.path.join(output_dir, "kconfig_warnings.c")
        self.assertTrue(os.path.exists(warnings_file))

        content = Path(warnings_file).read_text()
        self.assertIn('#warning "Kconfig warning: Warning 1"', content)
        self.assertIn('#warning "Kconfig warning: Warning 2"', content)

    def test_setup_kconfig_environment_with_bzlmod_modules(self):
        tmp_dir = os.path.join(self.test_dir, "tmp")
        module_dir = os.path.join(self.test_dir, "external", "+_repo_rules+hal_nordic")
        os.makedirs(module_dir, exist_ok=True)

        kconfig_gen_symbols.setup_kconfig_environment(
            str(self.zephyr_base), tmp_dir, [module_dir]
        )

        self.assertEqual(
            os.environ["ZEPHYR_HAL_NORDIC_MODULE_DIR"], os.path.abspath(module_dir)
        )

        kconfig_env_file = os.path.join(tmp_dir, "kconfig_module_dirs.env")
        self.assertTrue(os.path.exists(kconfig_env_file))
        content = Path(kconfig_env_file).read_text()
        self.assertIn(
            f"ZEPHYR_HAL_NORDIC_MODULE_DIR={os.path.abspath(module_dir)}", content
        )

    @patch("kconfig_utils.generate_kconfig_dts")
    def test_single_job_execution(self, mock_gen_dts):
        output_file = os.path.join(self.test_dir, "BUILD.bazel")
        mock_kconf = MagicMock()
        self.kconfig_mock.Kconfig.return_value = mock_kconf
        mock_kconf.warnings = []
        mock_kconf.syms = {}

        with patch(
            "sys.argv",
            [
                "kconfig_gen_symbols.py",
                "--zephyr-base",
                str(self.zephyr_base),
                "--output",
                output_file,
                "--jobs",
                "1",
            ],
        ):
            kconfig_gen_symbols.main()

        self.kconfig_mock.Kconfig.assert_called()


if __name__ == "__main__":
    unittest.main()
