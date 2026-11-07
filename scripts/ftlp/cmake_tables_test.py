# SPDX-License-Identifier: Apache-2.0
"""Tests for cmake_tables: parsing, and that the checked-in .bzl is current."""

import pathlib
import unittest

import cmake_tables

_CMAKE = """\
zephyr_compile_definitions_ifdef(CONFIG_SOC_NRF54LM20B          NRF54LM20B_XXAA)
zephyr_compile_definitions_ifdef(CONFIG_SOC_NRF54H20_CPUAPP     NRF54H20_XXAA
                                                                NRF_APPLICATION)
zephyr_compile_definitions_ifdef(CONFIG_SOC_NRF5340_CPUAPP NRF_SKIP_FICR_NS_COPY_TO_RAM)
zephyr_compile_definitions_ifdef(CONFIG_SOC_NRF5340_CPUAPP NRF_SKIP_FICR_NS_COPY_TO_RAM)
zephyr_library_compile_definitions_ifdef(CONFIG_NRF_TRACE_PORT ENABLE_TRACE)
zephyr_library_sources_ifdef(CONFIG_NRFX_CLOCK   ${SRC_DIR}/nrfx_clock.c)
zephyr_library_sources_ifdef(CONFIG_NRFX_CLOCK   ${SRC_DIR}/nrfx_clock_xo.c)
zephyr_library_sources_ifdef(CONFIG_NRFX_PRS     ${SRC_DIR}/prs/nrfx_prs.c)
zephyr_library_sources_ifdef(CONFIG_SOC_NRF52840 ${MDK_DIR}/system_nrf52840.c)
"""


def _runfile(path: str) -> pathlib.Path:
    for root in (pathlib.Path("."), pathlib.Path("_main"), pathlib.Path("zephyr")):
        if (root / path).exists():
            return root / path
    raise FileNotFoundError(path)


class ParseTest(unittest.TestCase):
    def test_multiline_defines_keep_every_token(self):
        defs = cmake_tables.parse_defines(_CMAKE)
        self.assertEqual(defs["CONFIG_SOC_NRF54H20_CPUAPP"], ["NRF54H20_XXAA", "NRF_APPLICATION"])

    def test_repeated_symbol_dedupes(self):
        defs = cmake_tables.parse_defines(_CMAKE)
        self.assertEqual(defs["CONFIG_SOC_NRF5340_CPUAPP"], ["NRF_SKIP_FICR_NS_COPY_TO_RAM"])

    def test_library_scoped_defines_are_excluded(self):
        self.assertNotIn("CONFIG_NRF_TRACE_PORT", cmake_tables.parse_defines(_CMAKE))

    def test_driver_sources_group_by_symbol_and_keep_subdirs(self):
        srcs = cmake_tables.parse_driver_sources(_CMAKE)
        self.assertEqual(srcs["CONFIG_NRFX_CLOCK"], ["nrfx_clock.c", "nrfx_clock_xo.c"])
        self.assertEqual(srcs["CONFIG_NRFX_PRS"], ["prs/nrfx_prs.c"])

    def test_non_nrfx_sources_are_excluded(self):
        self.assertNotIn("CONFIG_SOC_NRF52840", cmake_tables.parse_driver_sources(_CMAKE))


class RealCMakeTest(unittest.TestCase):
    """Guards the gaps that broke nRF54L links: values come from the real CMake file."""

    def setUp(self):
        self.cmake = _runfile(cmake_tables.CMAKE).read_text()

    def test_nrf54l_drivers_present(self):
        srcs = cmake_tables.parse_driver_sources(self.cmake)
        for sym in ("CONFIG_NRFX_GRTC", "CONFIG_NRFX_SPIM", "CONFIG_NRFX_CRACEN"):
            self.assertIn(sym, srcs)

    def test_nrf54lm20b_chip_define_present(self):
        self.assertIn("NRF54LM20B_XXAA", cmake_tables.parse_defines(self.cmake)["CONFIG_SOC_NRF54LM20B"])

    def test_checked_in_bzl_is_current(self):
        want = cmake_tables.render(self.cmake)
        have = _runfile(cmake_tables.OUT).read_text()
        self.assertEqual(have, want, "stale: run `bazel run //scripts/ftlp:cmake_tables`")


if __name__ == "__main__":
    unittest.main()
