# SPDX-License-Identifier: Apache-2.0
"""Pin vendor SDKs in MODULE.bazel: Nordic nrfxlib, sdk-nrf, sdk-edge-ai (Axon); ST lsm6dsk320x PID.

From the fork root:
  bazel run //scripts/ftlp:vendor_sync -- sync --ncs-tag v3.4.2
  bazel run //scripts/ftlp:vendor_sync -- sync --latest
  bazel run //scripts/ftlp:vendor_sync -- check

`sync` refuses an NCS tag whose sdk-zephyr VERSION major.minor differs from
this tree: the SoftDevice Controller is only tested against that Zephyr. sdk-edge-ai
must be a release built on the same NCS major.minor.
Both commands fail when a file a vendor BUILD names is gone upstream.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import urllib.request

import yaml

BEGIN = "# BEGIN vendor_sdk (managed by scripts/ftlp/vendor_sync.py; do not hand-edit)"
END = "# END vendor_sdk"

GITHUB = "https://github.com"
RAW = "https://raw.githubusercontent.com"
NCS_ORG = "nrfconnect"
ST_PID_REPO = "STMicroelectronics/lsm6dsk320x-pid"

_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_VERSION_LINE = re.compile(r"^\s*(VERSION_MAJOR|VERSION_MINOR|PATCHLEVEL)\s*=\s*(\d+)\s*$")
_BUILD_PATH = re.compile(r'"([A-Za-z0-9_./,-]+\.(?:c|h|yaml))"')
_ARCHIVE_URL = re.compile(rf"^{GITHUB}/([^/]+/[^/]+)/archive/(?:refs/tags/)?(.+)\.tar\.gz$")


@dataclasses.dataclass(frozen=True)
class Archive:
    """One managed http_archive."""

    name: str
    repo: str  # owner/name on GitHub
    rev: str  # tag or 40-hex commit
    build_file: str
    sha256: str = ""
    patch: str = ""

    @property
    def url(self) -> str:
        ref = self.rev if _SHA.match(self.rev) else f"refs/tags/{self.rev}"
        return f"{GITHUB}/{self.repo}/archive/{ref}.tar.gz"

    @property
    def strip_prefix(self) -> str:
        # GitHub drops a tag's leading "v" in the archive's top-level dir.
        rev = self.rev
        if not _SHA.match(rev) and rev.startswith("v"):
            rev = rev[1:]
        return f"{self.repo.split('/')[1]}-{rev}"


def latest_release_tag(tags: list[str]) -> str:
    """Highest vX.Y.Z; rc, preview and custom tags are skipped."""
    versions = {}
    for t in tags:
        m = _RELEASE_TAG.match(t)
        if m:
            versions[t] = tuple(int(p) for p in m.groups())
    if not versions:
        raise ValueError("no vX.Y.Z release tags")
    return max(versions, key=lambda t: versions[t])


def parse_ls_remote_tags(output: str) -> list[str]:
    tags = []
    for line in output.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith("refs/tags/") and not ref.endswith("^{}"):
            tags.append(ref.removeprefix("refs/tags/"))
    return tags


def parse_west(text: str) -> dict[str, str]:
    """West project name -> revision."""
    projects = yaml.safe_load(text)["manifest"]["projects"]
    return {p["name"]: str(p["revision"]) for p in projects if "revision" in p}


def parse_version(text: str) -> tuple[int, int, int]:
    fields = {}
    for line in text.splitlines():
        m = _VERSION_LINE.match(line)
        if m:
            fields[m.group(1)] = int(m.group(2))
    return fields["VERSION_MAJOR"], fields["VERSION_MINOR"], fields["PATCHLEVEL"]


def check_lockstep(ncs_zephyr: tuple[int, int, int], tree: tuple[int, int, int]) -> None:
    if ncs_zephyr[:2] != tree[:2]:
        raise SystemExit(
            f"refusing: NCS sdk-zephyr is {_dotted(ncs_zephyr)}, this tree is "
            f"{_dotted(tree)}; major.minor must match"
        )


def render_block(archives: list[Archive], comment: str) -> str:
    lines = [BEGIN, f"# {comment}"]
    for a in archives:
        lines += ["http_archive(", f'    name = "{a.name}",', f'    build_file = "{a.build_file}",']
        if a.patch:
            lines += ['    patch_args = ["-p1"],', f'    patches = ["{a.patch}"],']
        lines += [
            f'    sha256 = "{a.sha256}",',
            f'    strip_prefix = "{a.strip_prefix}",',
            f'    urls = ["{a.url}"],',
            ")",
            "",
        ]
    lines[-1] = END
    return "\n".join(lines)


def replace_block(module_text: str, block: str) -> str:
    start, end = module_text.find(BEGIN), module_text.find(END)
    if start < 0 or end < start:
        raise ValueError("MODULE.bazel has no managed vendor_sdk block")
    return module_text[:start] + block + module_text[end + len(END) :]


def parse_block(module_text: str) -> list[Archive]:
    """Managed archives currently pinned in MODULE.bazel."""
    start, end = module_text.find(BEGIN), module_text.find(END)
    out = []
    for chunk in module_text[start:end].split("http_archive(")[1:]:
        field = dict(re.findall(r'(\w+) = "([^"]+)"', chunk))
        url = re.search(r'urls = \["([^"]+)"\]', chunk)
        m = _ARCHIVE_URL.match(url.group(1)) if url else None
        if not m:
            raise ValueError(f"unparseable archive url in block: {chunk[:60]!r}")
        out.append(Archive(field["name"], m.group(1), m.group(2), field["build_file"], field["sha256"]))
    return out


def build_file_paths(build_text: str) -> list[str]:
    """Source paths a BUILD file names literally (glob patterns are skipped)."""
    return sorted({p for p in _BUILD_PATH.findall(build_text) if "*" not in p})


def missing_paths(names: list[str], wanted: list[str], prefix: str) -> list[str]:
    have = {n.removeprefix(prefix + "/") for n in names}
    return [w for w in wanted if w not in have]


def _dotted(v: tuple[int, int, int]) -> str:
    return ".".join(map(str, v))


# --- I/O ---------------------------------------------------------------------


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as resp:  # noqa: S310 (fixed https hosts)
        return resp.read()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd()))


def _download(a: Archive) -> tuple[str, list[str]]:
    """sha256 of the archive and its member names."""
    data = _fetch(a.url)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = tar.getnames()
    return hashlib.sha256(data).hexdigest(), names


def _report_missing(root: pathlib.Path, a: Archive, names: list[str]) -> int:
    build = root / a.build_file.removeprefix("//").replace(":", "/")
    missing = missing_paths(names, build_file_paths(build.read_text()), a.strip_prefix)
    for m in missing:
        print(f"MISSING in {a.repo}@{a.rev}: {m} (named by {a.build_file})", file=sys.stderr)
    return len(missing)


def wanted_archives(ncs_tag: str, nrfxlib_rev: str, edge_ai_tag: str, st_rev: str) -> list[Archive]:
    return [
        Archive(
            "nrfxlib",
            f"{NCS_ORG}/sdk-nrfxlib",
            nrfxlib_rev,
            "//modules/nordic_sdk:nrfxlib.BUILD",
            patch="//modules/nordic_sdk:nrfxlib.patch",
        ),
        Archive(
            "sdk_nrf",
            f"{NCS_ORG}/sdk-nrf",
            ncs_tag,
            "//modules/nordic_sdk:sdk_nrf.BUILD",
            patch="//modules/nordic_sdk:sdk_nrf.patch",
        ),
        Archive(
            "sdk_edge_ai",
            f"{NCS_ORG}/sdk-edge-ai",
            edge_ai_tag,
            "//modules/nordic_sdk:sdk_edge_ai.BUILD",
            patch="//modules/nordic_sdk:sdk_edge_ai.patch",
        ),
        Archive("lsm6dsk320x_pid", ST_PID_REPO, st_rev, "//modules/st_pid:lsm6dsk320x_pid.BUILD"),
    ]


def matching_release(nrf_rev_by_tag: dict[str, str], ncs_tag: str) -> str:
    """Highest release tag whose pinned sdk-nrf shares ncs_tag's major.minor."""
    want = _RELEASE_TAG.match(ncs_tag)
    if not want:
        raise ValueError(f"not a release tag: {ncs_tag}")
    hits = []
    for tag, nrf_rev in nrf_rev_by_tag.items():
        m, t = _RELEASE_TAG.match(nrf_rev), _RELEASE_TAG.match(tag)
        if m and t and m.groups()[:2] == want.groups()[:2]:
            hits.append(tag)
    if not hits:
        raise SystemExit(f"refusing: no sdk-edge-ai release targets NCS v{'.'.join(want.groups()[:2])}.x")
    return latest_release_tag(hits)


def _edge_ai_tag(ncs_tag: str) -> str:
    repo = f"{NCS_ORG}/sdk-edge-ai"
    tags = [t for t in parse_ls_remote_tags(_git("ls-remote", "--tags", f"{GITHUB}/{repo}.git")) if _RELEASE_TAG.match(t)]
    nrf_revs = {t: parse_west(_fetch(f"{RAW}/{repo}/{t}/west.yml").decode()).get("nrf", "") for t in tags}
    return matching_release(nrf_revs, ncs_tag)


def cmd_sync(args: argparse.Namespace) -> int:
    root = _root()
    ncs_tag = args.ncs_tag or latest_release_tag(
        parse_ls_remote_tags(_git("ls-remote", "--tags", f"{GITHUB}/{NCS_ORG}/sdk-nrf.git"))
    )
    west = parse_west(_fetch(f"{RAW}/{NCS_ORG}/sdk-nrf/{ncs_tag}/west.yml").decode())
    ncs_zephyr = parse_version(_fetch(f"{RAW}/{NCS_ORG}/sdk-zephyr/{west['zephyr']}/VERSION").decode())
    check_lockstep(ncs_zephyr, parse_version((root / "VERSION").read_text()))
    st_rev = args.st_rev or _git("ls-remote", f"{GITHUB}/{ST_PID_REPO}.git", "HEAD").split()[0]
    edge_ai_tag = args.edge_ai_tag or _edge_ai_tag(ncs_tag)

    archives, missing = [], 0
    for a in wanted_archives(ncs_tag, west["nrfxlib"], edge_ai_tag, st_rev):
        sha256, names = _download(a)
        missing += _report_missing(root, a, names)
        archives.append(dataclasses.replace(a, sha256=sha256))

    module = root / "MODULE.bazel"
    old = module.read_text()
    comment = f"NCS {ncs_tag}: sdk-zephyr VERSION {_dotted(ncs_zephyr)} matches this tree."
    new = replace_block(old, render_block(archives, comment))
    if new != old:
        module.write_text(new)
    print(
        f"{'pinned' if new != old else 'up to date'}: NCS {ncs_tag}, sdk-edge-ai {edge_ai_tag}, "
        f"{ST_PID_REPO}@{st_rev[:12]}"
    )
    return 1 if missing else 0


def cmd_check(_: argparse.Namespace) -> int:
    root = _root()
    missing = 0
    for a in parse_block((root / "MODULE.bazel").read_text()):
        sha256, names = _download(a)
        if sha256 != a.sha256:
            print(f"SHA256 MISMATCH {a.name}: pinned {a.sha256}, got {sha256}", file=sys.stderr)
            missing += 1
        missing += _report_missing(root, a, names)
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sync = sub.add_parser("sync", help="re-pin nrfxlib, sdk-nrf, sdk-edge-ai and the ST PID")
    which = sync.add_mutually_exclusive_group(required=True)
    which.add_argument("--ncs-tag", help="sdk-nrf release tag, e.g. v3.4.2")
    which.add_argument("--latest", action="store_true", help="highest sdk-nrf vX.Y.Z tag")
    sync.add_argument("--edge-ai-tag", help="sdk-edge-ai tag (default: newest built on the same NCS minor)")
    sync.add_argument("--st-rev", help="lsm6dsk320x-pid commit (default: HEAD)")
    sync.set_defaults(func=cmd_sync)
    sub.add_parser("check", help="verify pins: sha256 and BUILD-named files").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
