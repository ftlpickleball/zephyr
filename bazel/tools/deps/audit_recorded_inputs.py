# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Audits the inputs Bazel recorded for repository rules and module extensions.

When Bazel re-verifies a fetched repository or an evaluated module extension (for example after a
server restart), it checks the recorded inputs in batches
(RepoRecordedInput.WithValue.splitIntoBatches): every FILE, DIRENTS or DIRTREE input that lives in
another external repository starts a new batch, and every batch costs a Skyframe restart. See
bazel/private/deps.bzl for how the Zephyr rules keep that number small.

This tool reads repository marker files ($OUTPUT_BASE/external/@<repo>.marker or
<realpath(external/<repo>)>.recorded_inputs in --repo_contents_cache) and the module extension
entries of lockfiles (by default the hidden lockfile $OUTPUT_BASE/MODULE.bazel.lock),
prints what was recorded where, and checks that:

  * there are no DIRTREE inputs (they hash whole directory trees);
  * there are no external DIRENTS inputs (directory listings are only watched in the main workspace);
  * no entry needs more than --max-batches batches;
  * every DIRENTS input follows a FILE input on the same path in an earlier batch. Bazel fails
    the build (instead of re-running the rule) when a listed directory was deleted, unless the
    deletion is noticed through such a FILE input first.

Usage:
  audit_recorded_inputs.py [--filter SUBSTRING]... [--max-batches N] [--verbose]
      OUTPUT_BASE [LOCKFILE]...

The exit status is 1 if a check failed.
"""

import argparse
import collections
import dataclasses
import json
import os
import sys

# Kinds of inputs that start a new batch when they live in another external repository.
_REPO_PATH_KINDS = ("FILE", "DIRENTS", "DIRTREE")


@dataclasses.dataclass(frozen=True)
class Input:
    """One recorded input."""

    kind: str
    path: str
    value: str

    @property
    def location(self):
        """Returns 'main', 'absolute' or 'external' for path inputs, else ''."""
        if self.kind not in _REPO_PATH_KINDS:
            return ""
        if not self.path.startswith("@"):
            return "absolute"
        return "external" if repo_name(self.path) else "main"

    @property
    def starts_batch(self):
        # Models Bazel 8's canBeRequestedUnconditionally(), where only external-repo inputs start a
        # new batch. Newer Bazel (9+) also starts a batch on every DIRENTS/DIRTREE input, so
        # enforcing the stricter Bazel 8 batching guarantees that an explicit external-repo barrier
        # (@bazel_tools//tools:BUILD) separates directory FILE watches from DIRENTS on both Bazel 8
        # and Bazel 9+.
        return self.location == "external"


@dataclasses.dataclass
class Entry:
    """The recorded inputs of one repository or module extension."""

    name: str
    inputs: list
    ordered: bool = True


def unescape(s):
    """Reverses RepoRecordedInput.escape() of Bazel."""
    if s == "\\0":
        return None
    out = []
    escaped = False
    for c in s:
        if escaped:
            out.append("\n" if c == "n" else " " if c == "s" else c)
            escaped = False
        elif c == "\\":
            escaped = True
        else:
            out.append(c)
    return "".join(out)


def parse_input(line):
    """Parses one 'KIND:path value' line of a marker file or lockfile, or returns None."""
    line = line.rstrip("\n")
    key, sep, value = line.partition(" ")
    if not sep:
        return None
    key = unescape(key)
    kind, sep, path = key.partition(":")
    if not sep or not kind.isupper():
        return None
    return Input(kind=kind, path=path, value=unescape(value))


def repo_name(path):
    """Returns the canonical repository name of a '@@name//path' input path ('' if main)."""
    return path.lstrip("@").split("//", 1)[0]


def split_into_batches(inputs):
    """Groups inputs like Bazel's RepoRecordedInput.WithValue.splitIntoBatches()."""
    batches = []
    current = []
    for i in inputs:
        if i.starts_batch and current:
            batches.append(current)
            current = []
        current.append(i)
    if current:
        batches.append(current)
    return batches


def check_entry(entry, max_batches):
    """Returns a list of problems found in 'entry'."""
    problems = []
    dirtrees = [i.path for i in entry.inputs if i.kind == "DIRTREE"]
    if dirtrees:
        problems.append("%d DIRTREE input(s), e.g. %s" % (len(dirtrees), dirtrees[0]))
    ext_dirents = [i.path for i in entry.inputs if i.kind == "DIRENTS" and i.location == "external"]
    if ext_dirents:
        problems.append(
            "%d external DIRENTS input(s), e.g. %s" % (len(ext_dirents), ext_dirents[0])
        )
    batches = split_into_batches(entry.inputs)
    if len(batches) > max_batches:
        problems.append("%d batches (max %d)" % (len(batches), max_batches))
    if not entry.ordered:
        return problems
    watched_before = set()
    unsafe = []
    for batch in batches:
        for i in batch:
            if i.kind == "DIRENTS" and i.path not in watched_before:
                unsafe.append(i.path)
        watched_before.update(i.path for i in batch if i.kind == "FILE")
    if unsafe:
        problems.append(
            "%d DIRENTS input(s) without a FILE input on the same path in an earlier batch, "
            "e.g. %s" % (len(unsafe), unsafe[0])
        )
    return problems


def read_marker(path):
    """Reads the inputs of a repository marker file."""
    inputs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            i = parse_input(line)
            if i is not None:
                inputs.append(i)
    return inputs


def read_lockfile_entries(path, filters):
    """Returns the Entry of each module extension in a lockfile whose ID matches a filter."""
    with open(path, encoding="utf-8") as f:
        lockfile = json.load(f)
    entries = []
    for ext_id, by_platform in sorted(lockfile.get("moduleExtensions", {}).items()):
        if not _matches(ext_id, filters):
            continue
        for platform, ext in sorted(by_platform.items()):
            name = "%s [%s] (%s)" % (ext_id, platform, os.path.basename(path))
            recorded = ext.get("recordedInputs")
            if isinstance(recorded, list):
                inputs = [i for i in map(parse_input, recorded) if i is not None]
                entries.append(Entry(name, inputs))
                continue
            # Older lockfiles store unordered maps of inputs to values.
            inputs = []
            for field, kind in (
                ("recordedFileInputs", "FILE"),
                ("recordedDirentsInputs", "DIRENTS"),
                ("envVariables", "ENV"),
            ):
                for key, value in sorted(ext.get(field, {}).items()):
                    inputs.append(Input(kind=kind, path=key, value=value))
            entries.append(Entry(name, inputs, ordered=False))
    return entries


def _matches(name, filters):
    return not filters or any(f in name for f in filters)


def collect_entries(output_base, lockfiles, filters):
    """Collects the entries of matching marker files and lockfile module extensions."""
    entries = []
    external = os.path.join(output_base, "external")
    if os.path.isdir(external):
        names = set(os.listdir(external))
        for name in sorted(names):
            if name.endswith(".marker") and _matches(name, filters):
                inputs = read_marker(os.path.join(external, name))
                entries.append(Entry(name[: -len(".marker")], inputs))
            elif (
                not name.startswith("@")
                and ("@" + name + ".marker") not in names
                and _matches("@" + name, filters)
            ):
                entry_path = os.path.join(external, name)
                if os.path.islink(entry_path):
                    recorded = os.path.realpath(entry_path) + ".recorded_inputs"
                    if os.path.isfile(recorded):
                        inputs = read_marker(recorded)
                        entries.append(Entry("@" + name, inputs))
    hidden = os.path.join(output_base, "MODULE.bazel.lock")
    for lockfile in ([hidden] if os.path.isfile(hidden) else []) + list(lockfiles):
        entries.extend(read_lockfile_entries(lockfile, filters))
    return entries


def format_entry(entry, problems, verbose):
    """Returns the report lines for one entry."""
    counts = collections.Counter()
    external_repos = collections.Counter()
    for i in entry.inputs:
        counts[i.location or i.kind] += 1
        if i.kind == "DIRENTS":
            counts["dirents"] += 1
        if i.location == "external":
            external_repos[repo_name(i.path)] += 1
    batches = len(split_into_batches(entry.inputs))
    lines = [
        "%s %s" % ("FAIL" if problems else "ok  ", entry.name),
        "     inputs=%d main=%d absolute=%d external=%d dirents=%d batches=%d%s"
        % (
            len(entry.inputs),
            counts["main"],
            counts["absolute"],
            counts["external"],
            counts["dirents"],
            batches,
            "" if entry.ordered else " (unordered lockfile format)",
        ),
    ]
    lines.extend("     problem: " + p for p in problems)
    if verbose:
        for repo, n in external_repos.most_common():
            lines.append("     %5d @@%s" % (n, repo))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("output_base", help="Output of `bazel info output_base`.")
    parser.add_argument(
        "lockfiles",
        nargs="*",
        help="Additional lockfiles to audit, e.g. the workspace's MODULE.bazel.lock.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Only audit repositories and extensions whose name contains this substring "
        "(repeatable; default: zephyr).",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=64,
        help="Maximum number of verification batches per entry (default: %(default)s).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also list the external repositories of batch-starting inputs.",
    )
    args = parser.parse_args(argv)

    entries = collect_entries(args.output_base, args.lockfiles, args.filter or ["zephyr"])
    if not entries:
        print("No matching marker files or module extensions found.", file=sys.stderr)
        return 1
    failed = 0
    for entry in entries:
        problems = check_entry(entry, args.max_batches)
        failed += bool(problems)
        print("\n".join(format_entry(entry, problems, args.verbose)))
    print("%d entries audited, %d failed." % (len(entries), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
