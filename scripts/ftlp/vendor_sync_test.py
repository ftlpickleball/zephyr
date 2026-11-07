# SPDX-License-Identifier: Apache-2.0
"""Unit tests for vendor_sync (pure functions; no network)."""

import pathlib
import unittest

import vendor_sync as vs

_WEST = """\
manifest:
  projects:
    - name: zephyr
      repo-path: sdk-zephyr
      revision: ncs-v3.4.2
    - name: nrfxlib
      repo-path: sdk-nrfxlib
      path: nrfxlib
      revision: v3.4.2
    - name: no-revision
      path: x
"""

_VERSION = "VERSION_MAJOR = 4\nVERSION_MINOR = 4\nPATCHLEVEL = 2\nVERSION_TWEAK = 0\n"

_SHA = "4bd4ed32e7d5f2873e73f96f695ec836afcd27a9"


def _runfile(path: str) -> pathlib.Path:
    for root in (pathlib.Path("."), pathlib.Path("_main"), pathlib.Path("zephyr")):
        if (root / path).exists():
            return root / path
    raise FileNotFoundError(path)


class TagTest(unittest.TestCase):
    def test_latest_skips_previews_and_compares_numerically(self):
        tags = ["v3.4.2", "v3.10.0-rc1", "v3.5.0-preview4", "v3.4.10", "v2.9.9", "v2.6.4-NCSDK-34113"]
        self.assertEqual(vs.latest_release_tag(tags), "v3.4.10")

    def test_latest_without_releases_raises(self):
        with self.assertRaises(ValueError):
            vs.latest_release_tag(["v3.5.0-preview4"])

    def test_ls_remote_drops_peeled_refs(self):
        out = "a\trefs/tags/v3.4.2\nb\trefs/tags/v3.4.2^{}\nc\trefs/heads/main\n"
        self.assertEqual(vs.parse_ls_remote_tags(out), ["v3.4.2"])


class ManifestTest(unittest.TestCase):
    def test_west_revisions_by_project(self):
        west = vs.parse_west(_WEST)
        self.assertEqual(west["zephyr"], "ncs-v3.4.2")
        self.assertEqual(west["nrfxlib"], "v3.4.2")
        self.assertNotIn("no-revision", west)

    def test_version_file(self):
        self.assertEqual(vs.parse_version(_VERSION), (4, 4, 2))

    def test_lockstep_accepts_patch_difference(self):
        vs.check_lockstep((4, 4, 2), (4, 4, 0))

    def test_lockstep_refuses_minor_difference(self):
        with self.assertRaises(SystemExit):
            vs.check_lockstep((4, 4, 99), (4, 5, 0))
        with self.assertRaises(SystemExit):
            vs.check_lockstep((4, 5, 0), (4, 4, 2))


class ArchiveTest(unittest.TestCase):
    def test_tag_url_and_prefix_drop_v(self):
        a = vs.Archive("nrfxlib", "nrfconnect/sdk-nrfxlib", "v3.4.2", "//x:y.BUILD")
        self.assertEqual(a.url, "https://github.com/nrfconnect/sdk-nrfxlib/archive/refs/tags/v3.4.2.tar.gz")
        self.assertEqual(a.strip_prefix, "sdk-nrfxlib-3.4.2")

    def test_sha_url_and_prefix_keep_sha(self):
        a = vs.Archive("p", vs.ST_PID_REPO, _SHA, "//x:y.BUILD")
        self.assertEqual(a.url, f"https://github.com/{vs.ST_PID_REPO}/archive/{_SHA}.tar.gz")
        self.assertEqual(a.strip_prefix, f"lsm6dsk320x-pid-{_SHA}")


class BlockTest(unittest.TestCase):
    def _archives(self):
        return [dataclass_with_sha(a) for a in vs.wanted_archives("v3.4.2", "v3.4.2", "v3.0.0", _SHA)]

    def test_render_parse_round_trip_keeps_pins(self):
        text = "head\n" + vs.render_block(self._archives(), "c") + "\ntail\n"
        parsed = vs.parse_block(text)
        self.assertEqual([(a.name, a.repo, a.rev, a.sha256) for a in parsed],
                         [(a.name, a.repo, a.rev, a.sha256) for a in self._archives()])

    def test_replace_keeps_surrounding_text(self):
        text = "head\n" + vs.BEGIN + "\nold\n" + vs.END + "\ntail\n"
        out = vs.replace_block(text, vs.BEGIN + "\nnew\n" + vs.END)
        self.assertEqual(out, "head\n" + vs.BEGIN + "\nnew\n" + vs.END + "\ntail\n")

    def test_replace_without_block_raises(self):
        with self.assertRaises(ValueError):
            vs.replace_block("no markers", "x")

    def test_every_nordic_archive_is_patched_to_a_slim_module(self):
        for a in self._archives():
            if a.repo.startswith(vs.NCS_ORG):
                self.assertTrue(a.patch, a.name)


class EdgeAiTagTest(unittest.TestCase):
    def test_picks_newest_release_on_same_ncs_minor(self):
        revs = {"v3.0.0": "v3.4.1", "v2.3.0": "v3.3.0", "v3.1.0": "v3.5.0", "v3.0.1-rc1": "v3.4.2"}
        self.assertEqual(vs.matching_release(revs, "v3.4.2"), "v3.0.0")

    def test_refuses_when_no_release_matches(self):
        with self.assertRaises(SystemExit):
            vs.matching_release({"v3.1.0": "v3.5.0-preview4"}, "v3.4.2")


class CheckedInTest(unittest.TestCase):
    """The real MODULE.bazel block and BUILD files, as the tool will see them."""

    def test_module_block_matches_tool_output(self):
        text = _runfile("MODULE.bazel").read_text()
        pinned = vs.parse_block(text)
        ncs_tag = next(a.rev for a in pinned if a.name == "sdk_nrf")
        nrfxlib = next(a.rev for a in pinned if a.name == "nrfxlib")
        edge_ai = next(a.rev for a in pinned if a.name == "sdk_edge_ai")
        st = next(a.rev for a in pinned if a.name == "lsm6dsk320x_pid")
        wanted = [
            vs.dataclasses.replace(a, sha256=next(p.sha256 for p in pinned if p.name == a.name))
            for a in vs.wanted_archives(ncs_tag, nrfxlib, edge_ai, st)
        ]
        start = text.find(vs.BEGIN)
        comment_end = text.find("\n", text.find("\n", start) + 1)
        comment = text[text.find("\n", start) + 3 : comment_end]
        self.assertEqual(text[start : text.find(vs.END) + len(vs.END)], vs.render_block(wanted, comment),
                         "hand-edited block: run `bazel run //scripts/ftlp:vendor_sync -- sync`")

    def test_build_files_name_controller_sources(self):
        paths = vs.build_file_paths(_runfile("modules/nordic_sdk/sdk_nrf.BUILD").read_text())
        self.assertIn("subsys/bluetooth/controller/hci_driver.c", paths)
        self.assertIn("subsys/mpsl/init/mpsl_init.c", paths)

    def test_missing_paths_reports_only_absent(self):
        names = ["sdk-nrf-3.4.2/a.c", "sdk-nrf-3.4.2/b/c.h"]
        self.assertEqual(vs.missing_paths(names, ["a.c", "b/c.h", "gone.c"], "sdk-nrf-3.4.2"), ["gone.c"])


def dataclass_with_sha(a):
    return vs.dataclasses.replace(a, sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
