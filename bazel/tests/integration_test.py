#!/usr/bin/env python3
# Copyright (c) 2026 Google LLC
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end integration tests for Zephyr Bazel configuration and hermeticity.

Exercises a sample downstream project (`bazel/tests/downstream_project`) that
consumes `@zephyr` as an external dependency, validating:
  - `audit_recorded_inputs.py` invariants (zero absolute path leaks, zero
    DIRTREE watches, zero external DIRENTS, bounded Skyframe batches, and
    non-invalidation on `.c` edits).
  - Explicit board/app pair scoping (`manual_boards` + out-of-tree boards)
    in `@zephyr_state//:state.json` and `@zephyr_index//:index.bzl`.
  - Discovery and clean deletion recovery of optional board-specific
    fragments/overlays (`boards/<board>.conf`, `boards/<board>.overlay`, and
    `sysbuild/<image>/boards/<board>.conf`).
  - CMake parity (`-D__DTS__` macro in DTS preprocessing, `KCONFIG_BOARD_DIR`
    sourcing `Kconfig.<board>`, and board overlay precedence).
  - `reproducible = True` on `gen_zephyr_config` and `zephyr_kconfig_schema`,
    zero checkout/output_base path leaks, cross-checkout byte-for-byte SHA-256
    identity, and `--repo_contents_cache` population/replay.
  - Fetched external `@zephyr` (staged tree without `.git`, exercising the
    `fetched_roots` path used by `git_override` / `archive_override`) vs. local
    git checkout override (`--override_repository` with `.git`).
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ZEPHYR_ROOT = Path(__file__).resolve().parents[2]
DOWNSTREAM_FIXTURE = Path(__file__).resolve().parent / "downstream_project"
AUDIT_SCRIPT = ZEPHYR_ROOT / "bazel" / "tools" / "deps" / "audit_recorded_inputs.py"

sys.path.insert(0, str(AUDIT_SCRIPT.parent))
import audit_recorded_inputs  # noqa: E402

def _starlark_app_hash(norm_app: str) -> str:
    """Computes Starlark's 32-bit String.hashCode() hex digest like bazel/naming.bzl."""
    h = 0
    for ch in norm_app:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    return f"{h:08x}"


MAIN_APP_HASH = _starlark_app_hash("apps/main_app")
ZC_MAIN_CUSTOM_SIM = f"zc_{MAIN_APP_HASH}_custom_sim_native"
ZC_MAIN_NATIVE_SIM = f"zc_{MAIN_APP_HASH}_native_sim_native"
ZC_MAIN_QEMU_CM3 = f"zc_{MAIN_APP_HASH}_qemu_cortex_m3_ti_lm3s6965"


def _default_scratch_parent() -> Path:
    """Returns a disk-backed directory for test output bases to avoid /tmp tmpfs inode exhaustion."""
    env_tmp = os.environ.get("TEST_TMPDIR")
    if env_tmp:
        p = Path(env_tmp)
        p.mkdir(parents=True, exist_ok=True)
        return p
    cache_dir = Path.home() / ".cache" / "bazel"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _stage_zephyr_tree(dest_dir: Path) -> None:
    """Stages the current Zephyr working tree (without .git) using hardlinks."""
    res_tracked = subprocess.run(
        ["git", "ls-files", "-z", "--cached"],
        cwd=ZEPHYR_ROOT,
        check=True,
        capture_output=True,
    )
    res_bazel = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard", "bazel"],
        cwd=ZEPHYR_ROOT,
        check=True,
        capture_output=True,
    )
    raw_files = set(res_tracked.stdout.split(b"\0")) | set(
        res_bazel.stdout.split(b"\0")
    )
    files = sorted(
        f.decode("utf-8")
        for f in raw_files
        if f
        and not f.decode("utf-8").startswith("bazel/tests/")
        and (
            (ZEPHYR_ROOT / f.decode("utf-8")).is_symlink()
            or (ZEPHYR_ROOT / f.decode("utf-8")).exists()
        )
    )
    dirs = {dest_dir / os.path.dirname(rel) for rel in files}
    for d in sorted(dirs):
        d.mkdir(parents=True, exist_ok=True)
    for rel in files:
        src = ZEPHYR_ROOT / rel
        dst = dest_dir / rel
        if src.is_symlink():
            os.symlink(os.readlink(src), dst)
        else:
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)


def _prepare_downstream_checkout(dest_dir: Path, zephyr_dir: Path) -> None:
    """Copies the downstream project fixture into `dest_dir` and configures MODULE.bazel."""
    shutil.copytree(DOWNSTREAM_FIXTURE, dest_dir)
    module_bazel = dest_dir / "MODULE.bazel"
    content = module_bazel.read_text(encoding="utf-8")
    target_override = (
        'local_path_override(\n    module_name = "zephyr",\n    path = "../../..",\n)'
    )
    assert target_override in content, (
        f"Expected {target_override!r} in {module_bazel}"
    )
    content = content.replace(
        target_override,
        f'local_path_override(\n    module_name = "zephyr",\n    path = "{zephyr_dir}",\n)',
        1,
    )
    root_module = (ZEPHYR_ROOT / "MODULE.bazel").read_text(encoding="utf-8")
    pw_match = re.search(
        r'git_override\(\s*module_name\s*=\s*"pigweed".*?commit\s*=\s*"([0-9a-f]{40})"',
        root_module,
        re.DOTALL,
    )
    assert pw_match, "Could not find pigweed git_override commit in root MODULE.bazel"
    content, count = re.subn(
        r'(git_override\(\s*module_name\s*=\s*"pigweed".*?commit\s*=\s*")[0-9a-f]{40}(")',
        rf"\g<1>{pw_match.group(1)}\2",
        content,
        count=1,
        flags=re.DOTALL,
    )
    assert count == 1, f"Expected to sync pigweed commit in {module_bazel}"
    module_bazel.write_text(content, encoding="utf-8")


def _tree_sha256(directory: Path) -> dict[str, str]:
    """Computes SHA-256 digests of every file under `directory`, keyed by relpath."""
    digests = {}
    for root, _, files in os.walk(directory):
        for fname in sorted(files):
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(directory))
            digests[rel] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    return digests


class DownstreamIntegrationTest(unittest.TestCase):
    """End-to-end integration test suite for a downstream Zephyr Bazel project."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp_obj = tempfile.TemporaryDirectory(
            prefix="zephyr_bazel_it_", dir=_default_scratch_parent()
        )
        cls.tmp_root = Path(cls._tmp_obj.name).resolve()
        cls.extra_bazel_args = shlex.split(
            os.environ.get("BAZEL_EXTRA_ARGS", "--config=remote_cache")
        )
        cls.shared_rcc = cls.tmp_root / "shared_rcc"
        cls.shared_rcc.mkdir(parents=True, exist_ok=True)

        cls.zephyr_tree = cls.tmp_root / "zephyr_tree"
        _stage_zephyr_tree(cls.zephyr_tree)

        cls.checkout_a = cls.tmp_root / "checkout_a"
        cls.ob_a = cls.tmp_root / "ob_a"
        _prepare_downstream_checkout(cls.checkout_a, cls.zephyr_tree)

        cls.checkout_b = cls.tmp_root / "checkout_b_different_path"
        cls.ob_b = cls.tmp_root / "ob_b"
        _prepare_downstream_checkout(cls.checkout_b, cls.zephyr_tree)

        cls._active_output_bases = [cls.ob_a, cls.ob_b]

    @classmethod
    def tearDownClass(cls):
        for ob in getattr(cls, "_active_output_bases", []):
            if ob.exists():
                subprocess.run(
                    ["bazelisk", f"--output_base={ob}", "shutdown"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        subprocess.run(
            ["chmod", "-R", "u+w", str(cls.tmp_root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        cls._tmp_obj.cleanup()
        super().tearDownClass()

    def _run_bazel(
        self,
        cwd: Path,
        output_base: Path,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        cmd = ["bazelisk", f"--output_base={output_base}"]
        cmd.extend(args)
        if args and args[0] in ("build", "test", "query", "cquery", "fetch"):
            cmd.extend(self.extra_bazel_args)
            cmd.append(f"--repo_contents_cache={self.shared_rcc}")
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        res = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            self.fail(
                f"Command {cmd} failed with exit code {res.returncode}:\n"
                f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
            )
        return res

    def _find_repo_dir(self, output_base: Path, suffix: str) -> Path:
        ext_dir = output_base / "external"
        matches = [
            p
            for p in ext_dir.iterdir()
            if p.is_dir() and (p.name == suffix or p.name.endswith(f"+{suffix}"))
        ]
        self.assertEqual(
            len(matches),
            1,
            f"Expected exactly 1 repo matching *{suffix} in {ext_dir}, found {matches}",
        )
        return matches[0]

    def _repo_eval_token(self, output_base: Path, suffix: str) -> tuple[int, str]:
        """Returns (repo_file_mtime_ns, resolved_dir) to detect repo rule re-evaluation."""
        repo_dir = self._find_repo_dir(output_base, suffix).resolve()
        anchor = (
            repo_dir / "state.json"
            if (repo_dir / "state.json").is_file()
            else repo_dir / "BUILD.bazel"
        )
        return (anchor.stat().st_mtime_ns, str(repo_dir))

    def _audit_output_base(
        self, output_base: Path, checkout: Path, max_batches: int = 20
    ) -> dict[str, audit_recorded_inputs.Entry]:
        lockfiles = []
        ws_lock = checkout / "MODULE.bazel.lock"
        if ws_lock.is_file():
            lockfiles.append(str(ws_lock))
        rc = audit_recorded_inputs.main(
            [
                str(output_base),
                *lockfiles,
                "--filter=@zephyr",
                "--filter=zc_",
                f"--max-batches={max_batches}",
            ]
        )
        self.assertEqual(
            rc, 0, f"audit_recorded_inputs.main failed on {output_base}"
        )
        entries = audit_recorded_inputs.collect_entries(
            str(output_base), lockfiles, ["@zephyr", "zc_"]
        )
        self.assertTrue(entries, "Expected non-empty audited entries")
        for entry in entries:
            if entry.name == "@zephyr+":
                # Built-in local_repository marker for local_path_override(module_name = "zephyr").
                continue
            abs_inputs = [i for i in entry.inputs if i.location == "absolute"]
            self.assertEqual(
                abs_inputs,
                [],
                f"Absolute path inputs leaked in {entry.name}: {abs_inputs}",
            )
        return {e.name: e for e in entries}

    def _ensure_baseline_built(self):
        """Ensures test_01's baseline builds in ob_a have run if tests are run standalone."""
        ext_dir = self.ob_a / "external"
        if ext_dir.is_dir():
            names = {p.name for p in ext_dir.iterdir()}
            if any(
                n == ZC_MAIN_CUSTOM_SIM or n.endswith(f"+{ZC_MAIN_CUSTOM_SIM}")
                for n in names
            ) and any(
                n == ZC_MAIN_QEMU_CM3 or n.endswith(f"+{ZC_MAIN_QEMU_CM3}")
                for n in names
            ):
                return
        self._run_bazel(
            self.checkout_a,
            self.ob_a,
            [
                "build",
                "--platforms=@zephyr//boards/qemu/cortex_m3:qemu_cortex_m3",
                "//apps/main_app:main_app",
            ],
        )
        self._run_bazel(
            self.checkout_a,
            self.ob_a,
            [
                "build",
                "--platforms=//boards/vendor/custom_sim:native",
                "//apps/main_app:main_app",
                "//apps/main_app:main_sysbuild",
            ],
        )

    def test_01_external_zephyr_build_pairs_cmake_parity_and_audit(self):
        """Builds downstream app & sysbuild against external @zephyr and audits recorded inputs."""
        self._ensure_baseline_built()

        # Verify explicit board/app pair scoping in @zephyr_state//:state.json and @zephyr_index//:index.bzl
        state_dir = self._find_repo_dir(self.ob_a, "zephyr_state")
        state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
        surviving = state["surviving_combinations"]
        main_boards = surviving.get("apps/main_app", [])
        helper_boards = surviving.get("apps/helper_app", [])
        self.assertGreater(len(state["board_index"]), 1000)
        self.assertIn("custom_sim/native", main_boards)
        self.assertIn("native_sim/native", main_boards)
        self.assertIn("qemu_cortex_m3/ti_lm3s6965", main_boards)
        self.assertLess(len(main_boards), 50)
        self.assertIn("custom_sim/native", helper_boards)
        self.assertIn("native_sim/native", helper_boards)
        self.assertLess(len(helper_boards), 50)

        index_dir = self._find_repo_dir(self.ob_a, "zephyr_index")
        index_bzl = (index_dir / "index.bzl").read_text(encoding="utf-8")
        self.assertIn(ZC_MAIN_CUSTOM_SIM, index_bzl)
        self.assertIn(ZC_MAIN_NATIVE_SIM, index_bzl)
        self.assertIn(ZC_MAIN_QEMU_CM3, index_bzl)

        # Verify CMake parity in generated headers of @zc_<main_app>_custom_sim_native
        zc_dir = self._find_repo_dir(self.ob_a, ZC_MAIN_CUSTOM_SIM)
        autoconf_h = (zc_dir / "zephyr" / "autoconf.h").read_text(encoding="utf-8")
        devicetree_h = (zc_dir / "zephyr" / "devicetree_generated.h").read_text(
            encoding="utf-8"
        )
        # 1. KCONFIG_BOARD_DIR resolved boards/vendor/custom_sim/Kconfig.custom_sim
        self.assertIn("#define CONFIG_CUSTOM_SIM_BOARD_FEATURE 1", autoconf_h)
        # 2. Auto-linked module Kconfig & app prj.conf applied
        self.assertIn("#define CONFIG_SAMPLE_MOD_ENABLED 1", autoconf_h)
        self.assertIn("#define CONFIG_SAMPLE_MOD_VALUE 11", autoconf_h)
        # 3. -D__DTS__ macro defined during preprocess_dts (sample-prop = 200, not 999)
        self.assertIn("#define DT_N_S_sample_dev_P_sample_prop 200", devicetree_h)

        # Run audit_recorded_inputs.py against ob_a
        self._audit_output_base(self.ob_a, self.checkout_a)

    def test_02_hermeticity_cross_checkout_identity_and_repo_contents_cache(self):
        """Verifies zero path leaks, cross-checkout byte identity, and cache replay."""
        self._ensure_baseline_built()
        kconfig_a = self._find_repo_dir(self.ob_a, "zephyr_kconfig")
        zc_a = self._find_repo_dir(self.ob_a, ZC_MAIN_CUSTOM_SIM)
        zc_qemu_a = self._find_repo_dir(self.ob_a, ZC_MAIN_QEMU_CM3)

        # Verify no file in @zephyr_kconfig or @zc_* contains checkout_a, ob_a, zephyr_tree, or ZEPHYR_ROOT
        forbidden_bytes = [
            str(self.checkout_a).encode("utf-8"),
            self.checkout_a.name.encode("utf-8"),
            str(self.ob_a).encode("utf-8"),
            str(self.zephyr_tree).encode("utf-8"),
            str(ZEPHYR_ROOT).encode("utf-8"),
        ]
        for repo_dir in (kconfig_a, zc_a, zc_qemu_a):
            for root, _, files in os.walk(repo_dir):
                for fname in files:
                    fpath = Path(root) / fname
                    data = fpath.read_bytes()
                    for needle in forbidden_bytes:
                        self.assertNotIn(
                            needle,
                            data,
                            f"Path leak {needle!r} found in {fpath.relative_to(repo_dir)}",
                        )

        # Verify --repo_contents_cache was populated by ob_a
        self.assertTrue(
            kconfig_a.is_symlink()
            and str(kconfig_a.resolve()).startswith(str(self.shared_rcc)),
            f"Expected @zephyr_kconfig ({kconfig_a}) to be cached in {self.shared_rcc}",
        )
        self.assertTrue(
            zc_a.is_symlink()
            and str(zc_a.resolve()).startswith(str(self.shared_rcc)),
            f"Expected @{ZC_MAIN_CUSTOM_SIM} ({zc_a}) to be cached in {self.shared_rcc}",
        )

        # Build in checkout_b (at a different path) with hostile host CONFIG_*/KCONFIG_* env vars
        self._run_bazel(
            self.checkout_b,
            self.ob_b,
            [
                "build",
                "--platforms=//boards/vendor/custom_sim:native",
                "//apps/main_app:main_app",
            ],
            extra_env={
                "CONFIG_HOST_ENV_LEAK": "y",
                "CONFIG_SAMPLE_MOD_VALUE": "9999",
                "KCONFIG_WARN_UNDEF": "y",
            },
        )

        kconfig_b = self._find_repo_dir(self.ob_b, "zephyr_kconfig")
        zc_b = self._find_repo_dir(self.ob_b, ZC_MAIN_CUSTOM_SIM)

        # Verify host CONFIG_* env vars did not leak
        autoconf_b = (zc_b / "zephyr" / "autoconf.h").read_text(encoding="utf-8")
        self.assertNotIn("CONFIG_HOST_ENV_LEAK", autoconf_b)
        self.assertIn("#define CONFIG_SAMPLE_MOD_VALUE 11", autoconf_b)

        # Assert 100% SHA-256 byte-for-byte identity and --repo_contents_cache hit across checkouts
        self.assertEqual(
            _tree_sha256(kconfig_a),
            _tree_sha256(kconfig_b),
            "@zephyr_kconfig files differed across checkouts",
        )
        self.assertEqual(
            _tree_sha256(zc_a),
            _tree_sha256(zc_b),
            f"@{ZC_MAIN_CUSTOM_SIM} files differed across checkouts",
        )
        self.assertEqual(
            kconfig_a.resolve(),
            kconfig_b.resolve(),
            "@zephyr_kconfig did not hit the shared --repo_contents_cache entry",
        )
        self.assertEqual(
            zc_a.resolve(),
            zc_b.resolve(),
            f"@{ZC_MAIN_CUSTOM_SIM} did not hit the shared --repo_contents_cache entry",
        )

    def test_03_warm_server_invalidation_and_recovery_invariants(self):
        """Verifies .c non-invalidation, config/overlay re-eval, and board dir creation/deletion recovery."""
        self._ensure_baseline_built()
        state_tok_0 = self._repo_eval_token(self.ob_a, "zephyr_state")
        kconfig_tok_0 = self._repo_eval_token(self.ob_a, "zephyr_kconfig")
        zc_tok_0 = self._repo_eval_token(self.ob_a, ZC_MAIN_CUSTOM_SIM)

        # 1. Editing .c files in app and module must NOT re-fetch any repo rules
        time.sleep(0.05)
        main_c = self.checkout_a / "apps" / "main_app" / "src" / "main.c"
        mod_c = self.checkout_a / "modules" / "sample_mod" / "sample_mod.c"
        orig_main_c = main_c.read_text(encoding="utf-8")
        orig_mod_c = mod_c.read_text(encoding="utf-8")
        try:
            main_c.write_text(orig_main_c + "\n// comment edit\n", encoding="utf-8")
            mod_c.write_text(orig_mod_c + "\n// module comment edit\n", encoding="utf-8")
            self._run_bazel(
                self.checkout_a,
                self.ob_a,
                [
                    "build",
                    "--platforms=//boards/vendor/custom_sim:native",
                    "//apps/main_app:main_app",
                ],
            )
            self.assertEqual(
                self._repo_eval_token(self.ob_a, "zephyr_state"),
                state_tok_0,
                "@zephyr_state should not re-evaluate on .c edit",
            )
            self.assertEqual(
                self._repo_eval_token(self.ob_a, "zephyr_kconfig"),
                kconfig_tok_0,
                "@zephyr_kconfig should not re-evaluate on .c edit",
            )
            self.assertEqual(
                self._repo_eval_token(self.ob_a, ZC_MAIN_CUSTOM_SIM),
                zc_tok_0,
                f"@{ZC_MAIN_CUSTOM_SIM} should not re-evaluate on .c edit",
            )
        finally:
            main_c.write_text(orig_main_c, encoding="utf-8")
            mod_c.write_text(orig_mod_c, encoding="utf-8")

        # 2. Editing prj.conf and app.overlay re-evaluates @zc_* without re-evaluating @zephyr_state
        time.sleep(0.05)
        prj_conf = self.checkout_a / "apps" / "main_app" / "prj.conf"
        app_overlay = self.checkout_a / "apps" / "main_app" / "app.overlay"
        orig_prj_conf = prj_conf.read_text(encoding="utf-8")
        orig_overlay = app_overlay.read_text(encoding="utf-8")
        try:
            prj_conf.write_text(
                orig_prj_conf.replace(
                    "CONFIG_SAMPLE_MOD_VALUE=11", "CONFIG_SAMPLE_MOD_VALUE=456"
                ),
                encoding="utf-8",
            )
            app_overlay.write_text(
                orig_overlay.replace("sample-prop = <200>;", "sample-prop = <300>;"),
                encoding="utf-8",
            )
            self._run_bazel(
                self.checkout_a,
                self.ob_a,
                [
                    "build",
                    "--platforms=//boards/vendor/custom_sim:native",
                    "//apps/main_app:main_app",
                ],
            )
            self.assertEqual(
                self._repo_eval_token(self.ob_a, "zephyr_state"),
                state_tok_0,
                "@zephyr_state should not re-evaluate on existing prj.conf/app.overlay edit",
            )
            self.assertEqual(
                self._repo_eval_token(self.ob_a, "zephyr_kconfig"),
                kconfig_tok_0,
                "@zephyr_kconfig should not re-evaluate on prj.conf/app.overlay edit",
            )
            self.assertNotEqual(
                self._repo_eval_token(self.ob_a, ZC_MAIN_CUSTOM_SIM),
                zc_tok_0,
                f"@{ZC_MAIN_CUSTOM_SIM} must re-evaluate on prj.conf/app.overlay edit",
            )
            zc_dir = self._find_repo_dir(self.ob_a, ZC_MAIN_CUSTOM_SIM)
            self.assertIn(
                "#define CONFIG_SAMPLE_MOD_VALUE 456",
                (zc_dir / "zephyr" / "autoconf.h").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "#define DT_N_S_sample_dev_P_sample_prop 300",
                (zc_dir / "zephyr" / "devicetree_generated.h").read_text(
                    encoding="utf-8"
                ),
            )
        finally:
            prj_conf.write_text(orig_prj_conf, encoding="utf-8")
            app_overlay.write_text(orig_overlay, encoding="utf-8")

        # 3. Creating and deleting boards/custom_sim_native.{conf,overlay}
        # and sysbuild/helper_app/boards/custom_sim_native.conf recovers cleanly
        app_boards_dir = self.checkout_a / "apps" / "main_app" / "boards"
        sb_boards_dir = (
            self.checkout_a
            / "apps"
            / "main_app"
            / "sysbuild"
            / "helper_app"
            / "boards"
        )
        try:
            app_boards_dir.mkdir(parents=True, exist_ok=True)
            (app_boards_dir / "custom_sim_native.conf").write_text(
                "CONFIG_SAMPLE_MOD_VALUE=789\n", encoding="utf-8"
            )
            (app_boards_dir / "custom_sim_native.overlay").write_text(
                "/ {\n    sample_dev: sample-dev {\n        sample-prop = <789>;\n    };\n};\n",
                encoding="utf-8",
            )
            sb_boards_dir.mkdir(parents=True, exist_ok=True)
            (sb_boards_dir / "custom_sim_native.conf").write_text(
                "CONFIG_SAMPLE_MOD_VALUE=321\n", encoding="utf-8"
            )

            self._run_bazel(
                self.checkout_a,
                self.ob_a,
                [
                    "build",
                    "--platforms=//boards/vendor/custom_sim:native",
                    "//apps/main_app:main_app",
                    "//apps/main_app:main_sysbuild",
                ],
            )
            zc_dir = self._find_repo_dir(self.ob_a, ZC_MAIN_CUSTOM_SIM)
            self.assertIn(
                "#define CONFIG_SAMPLE_MOD_VALUE 789",
                (zc_dir / "zephyr" / "autoconf.h").read_text(encoding="utf-8"),
            )
            # Board overlay overrides app.overlay (789 > 200)
            self.assertIn(
                "#define DT_N_S_sample_dev_P_sample_prop 789",
                (zc_dir / "zephyr" / "devicetree_generated.h").read_text(
                    encoding="utf-8"
                ),
            )
            state_dir = self._find_repo_dir(self.ob_a, "zephyr_state")
            state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
            custom_repos = state["sysbuild_metadata"]["custom_repos"]
            helper_custom_name = next(
                r["name"]
                for r in custom_repos
                if r["helper_name"] == "helper_app"
                and r["board_id"] == "custom_sim/native"
            )
            zc_helper_dir = self._find_repo_dir(self.ob_a, helper_custom_name)
            self.assertIn(
                "#define CONFIG_SAMPLE_MOD_VALUE 321",
                (zc_helper_dir / "zephyr" / "autoconf.h").read_text(encoding="utf-8"),
            )
        finally:
            shutil.rmtree(app_boards_dir, ignore_errors=True)
            shutil.rmtree(
                self.checkout_a / "apps" / "main_app" / "sysbuild",
                ignore_errors=True,
            )

        # Rebuild after deleting boards/ and sysbuild/ to verify no InconsistentFilesystemException
        self._run_bazel(
            self.checkout_a,
            self.ob_a,
            [
                "build",
                "--platforms=//boards/vendor/custom_sim:native",
                "//apps/main_app:main_app",
                "//apps/main_app:main_sysbuild",
            ],
        )
        zc_dir = self._find_repo_dir(self.ob_a, ZC_MAIN_CUSTOM_SIM)
        self.assertIn(
            "#define CONFIG_SAMPLE_MOD_VALUE 11",
            (zc_dir / "zephyr" / "autoconf.h").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "#define DT_N_S_sample_dev_P_sample_prop 200",
            (zc_dir / "zephyr" / "devicetree_generated.h").read_text(encoding="utf-8"),
        )
        self._audit_output_base(self.ob_a, self.checkout_a)

    def test_04_local_git_override_and_audit(self):
        """Verifies local git checkout override (--override_repository with .git)."""
        self._ensure_baseline_built()
        override_dir = self.checkout_a / "repository_overrides" / "zephyr"
        override_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Move the staged Zephyr tree into repository_overrides/zephyr and add a .git marker
            shutil.move(str(self.zephyr_tree), str(override_dir))
            (override_dir / ".git").write_text("gitdir: ./.git\n", encoding="utf-8")

            self._run_bazel(
                self.checkout_a,
                self.ob_a,
                [
                    "build",
                    f"--override_repository=zephyr+={override_dir}",
                    "--platforms=//boards/vendor/custom_sim:native",
                    "//apps/main_app:main_app",
                ],
            )

            entries = self._audit_output_base(self.ob_a, self.checkout_a)
            # When .git is present in repository_overrides/zephyr, @zephyr inputs
            # are tracked as main-workspace files (`@@//repository_overrides/zephyr/...`)
            # with 0 absolute paths.
            setup_entry = next(
                e
                for name, e in entries.items()
                if "zephyr_setup " in name
            )
            main_override_inputs = [
                i
                for i in setup_entry.inputs
                if i.location == "main"
                and "repository_overrides/zephyr" in (i.path or "")
            ]
            self.assertGreater(
                len(main_override_inputs),
                100,
                "Expected repository_overrides/zephyr files to be watched under main workspace",
            )
        finally:
            if override_dir.exists():
                (override_dir / ".git").unlink(missing_ok=True)
                shutil.move(str(override_dir), str(self.zephyr_tree))
            shutil.rmtree(self.checkout_a / "repository_overrides", ignore_errors=True)
            # Re-sync ob_a without --override_repository so ob_a remains usable
            # even if test methods are executed out of alphabetical order.
            self._run_bazel(
                self.checkout_a,
                self.ob_a,
                [
                    "build",
                    "--platforms=//boards/vendor/custom_sim:native",
                    "//apps/main_app:main_app",
                ],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
