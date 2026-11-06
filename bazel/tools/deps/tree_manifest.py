# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Hashes the names of discovery-relevant files below directory trees.

Used by the `skyframe_warmer` and `zephyr_workspace_manifest` repository rules
in `bazel/private/deps.bzl`. Those rules `watch_tree()` the directories, so
they re-run whenever a file below them is added, removed or edited, and write
the digests computed here to small files that `zephyr_setup` and
`@zephyr_kconfig` watch. Editing an existing file (e.g. a `.c` source) leaves
the digests unchanged, so only adding or removing a relevant file invalidates
the consumers. The contents of existing files are tracked by per-file watches
in the consumers themselves.

Subcommands:

  hash --root ROOT --subdir DIR... --out-dir OUT
      Writes OUT/done (all files relevant to `zephyr_setup`: Kconfig, DTS,
      YAML, conf, CMake and Bazel files) and OUT/kconfig_done (the subset
      relevant to `@zephyr_kconfig`: Kconfig, BUILD/.bzl, board/SoC/arch/
      module metadata and devicetree bindings).

  setup-dirs --workspace-root WS
      Prints JSON describing the main-workspace directories that the root
      module's `zephyr_setup.env()` tags (apps_dirs, boards_dirs, modules)
      make `zephyr_setup` scan, plus the MODULE.bazel files read to find them.
"""

import argparse
import ast
from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import os
import sys

import find_pin_files

# Directory names never descended into (VCS metadata, Bazel convenience
# symlinks, Python caches and build output), like setup.bzl's _find_app_dirs().
_PRUNED_DIR_PREFIXES = (".", "bazel-")
_PRUNED_DIR_NAMES = frozenset({"__pycache__", "out"})

_SETUP_SUFFIXES = (
    ".yaml",
    ".yml",
    ".dts",
    ".dtsi",
    ".overlay",
    ".conf",
    "_defconfig",
    ".bzl",
    ".BUILD",
)
_SETUP_NAMES = frozenset({"CMakeLists.txt", "BUILD", "BUILD.bazel"})

_KCONFIG_NAMES = frozenset(
    {
        "BUILD",
        "BUILD.bazel",
        "board.yml",
        "board.yaml",
        "soc.yml",
        "soc.yaml",
        "archs.yml",
        "module.yml",
        "module.yaml",
    }
)
_KCONFIG_SUFFIXES = (".bzl", ".BUILD")
_BINDING_SUFFIXES = (".yaml", ".yml")

# Subdirectories of a `boards_dirs` root that Zephyr scans as a board, SoC,
# DTS and snippet root. `zephyr/dts` is probed before `dts` for bindings and
# DTS includes (kconfig_utils.generate_kconfig_dts(), kconfig_gen_values.py's
# generate_edt_pickle() and preprocess_dts()).
_BOARD_ROOT_SUBDIRS = ("boards", "dts", "soc", "snippets", "zephyr/dts")


def _is_kconfig(name: str) -> bool:
    return name == "Kconfig" or name.startswith("Kconfig.")


def is_setup_input(relpath: str) -> bool:
    """Returns whether adding/removing `relpath` can change `zephyr_setup`."""
    name = relpath.rpartition("/")[2]
    return (
        _is_kconfig(name)
        or name in _SETUP_NAMES
        or name.endswith(_SETUP_SUFFIXES)
    )


def is_kconfig_input(relpath: str) -> bool:
    """Returns whether adding/removing `relpath` can change `@zephyr_kconfig`."""
    name = relpath.rpartition("/")[2]
    if _is_kconfig(name) or name in _KCONFIG_NAMES:
        return True
    if name.endswith(_KCONFIG_SUFFIXES):
        return True
    return name.endswith(_BINDING_SUFFIXES) and (
        "/dts/bindings/" in "/" + relpath
    )


def _pruned(name: str) -> bool:
    return name.startswith(_PRUNED_DIR_PREFIXES) or name in _PRUNED_DIR_NAMES


def walk_relpaths(root: str, subdirs: Iterable[str]) -> list[str]:
    """Returns the sorted `/`-separated paths of files below `root/<subdir>`.

    Symlinked directories are not followed; pruned directories (see
    `_PRUNED_DIR_PREFIXES` and `_PRUNED_DIR_NAMES`) are skipped.

    Raises:
        OSError: if a directory cannot be listed.
    """
    relpaths = []

    def _raise(err: OSError):
        raise err

    for sub in sorted(set(subdirs)):
        top = os.path.join(root, sub) if sub else root
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top, onerror=_raise):
            dirnames[:] = sorted(d for d in dirnames if not _pruned(d))
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            for fname in filenames:
                relpaths.append(fname if rel_dir == "." else f"{rel_dir}/{fname}")
    relpaths.sort()
    return relpaths


def digest(relpaths: Iterable[str]) -> str:
    """Returns the SHA-256 of the newline-joined sorted `relpaths`."""
    h = hashlib.sha256()
    for rel in sorted(relpaths):
        h.update(rel.encode("utf-8", "surrogateescape"))
        h.update(b"\n")
    return h.hexdigest()


def manifests(root: str, subdirs: Iterable[str]) -> dict[str, str]:
    """Returns {"done": ..., "kconfig_done": ...} digests for the trees."""
    relpaths = walk_relpaths(root, subdirs)
    return {
        "done": digest(r for r in relpaths if is_setup_input(r)),
        "kconfig_done": digest(r for r in relpaths if is_kconfig_input(r)),
    }


def _string_list(
    node: ast.AST, consts: Mapping[str, list[str]]
) -> list[str] | None:
    """Evaluates a list of string literals, list variables and `+`."""
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            else:
                return None
        return out
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_list(node.left, consts)
        right = _string_list(node.right, consts)
        if left is None or right is None:
            return None
        return left + right
    return None


def _is_setup_extension(call: ast.Call) -> bool:
    """Whether `call` is `use_extension("...//bazel:setup.bzl", "zephyr_setup")`."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "use_extension"):
        return False
    if len(call.args) < 2:
        return False
    bzl, name = call.args[0], call.args[1]
    return (
        isinstance(bzl, ast.Constant)
        and isinstance(bzl.value, str)
        and bzl.value.endswith("//bazel:setup.bzl")
        and isinstance(name, ast.Constant)
        and name.value == "zephyr_setup"
    )


def _label_dir(
    workspace_root: str, literal: str, by_name: Mapping[str, str]
) -> str | None:
    """Mirrors setup.bzl's get_dir_from_label() for main-repository labels.

    Returns the workspace-relative directory ("" for the root) or None if the
    label is not in the main repository.
    """
    if literal.startswith(":"):
        literal = "//" + literal
    elif "//" not in literal and not literal.startswith("@"):
        literal = "//:" + literal
    pin = find_pin_files.label_literal_to_relpath(literal, "", by_name)
    if pin is None:
        return None
    path = os.path.join(workspace_root, pin.relpath)
    if os.path.isdir(path):
        return pin.relpath
    return pin.relpath.rpartition("/")[0]


def _child_dirs(workspace_root: str, rel: str) -> list[str]:
    top = os.path.join(workspace_root, rel) if rel else workspace_root
    try:
        names = sorted(os.listdir(top))
    except OSError:
        return []
    return [
        f"{rel}/{n}" if rel else n
        for n in names
        if not _pruned(n) and os.path.isdir(os.path.join(top, n))
        and not os.path.islink(os.path.join(top, n))
    ]


def zephyr_setup_dirs(workspace_root: str) -> dict[str, list[str]]:
    """Finds the main-workspace directories scanned by `zephyr_setup`.

    Parses the root `MODULE.bazel` (and the files it `include()`s) for
    `zephyr_setup.env()` tags and maps their main-repository labels to
    directories:

      * `apps_dirs`: the directory tree itself;
      * `boards_dirs`: its `boards/`, `dts/`, `soc/`, `snippets/` and
        `zephyr/dts/` trees;
      * `modules`: the module's directory tree.

    A label naming the workspace root is replaced by its top-level child
    directories, so that Bazel's convenience symlinks are never watched.

    Returns:
        {"module_files": [...], "dirs": [...], "warnings": [...]}, with
        workspace-relative paths. `dirs` may name missing directories (so that
        creating them is noticed) and never contains nested entries.
    """
    module_files: list[str] = []
    warnings: list[str] = []
    by_name: dict[str, str] = {}
    queue = ["MODULE.bazel"]
    labels: dict[str, list[str]] = {"apps_dirs": [], "boards_dirs": [], "modules": []}
    while queue:
        rel = queue.pop(0)
        if rel in module_files:
            continue
        module_files.append(rel)
        path = os.path.join(workspace_root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="surrogateescape") as f:
            tree = find_pin_files._parse_ast(f.read())  # pylint: disable=protected-access
        if tree is None:
            warnings.append(f"{rel}: cannot parse")
            continue
        if rel == "MODULE.bazel":
            name = find_pin_files.module_name(tree)
            if name:
                by_name[name] = ""
        proxies: set[str] = set()
        consts: dict[str, list[str]] = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                if isinstance(stmt.value, ast.Call) and _is_setup_extension(stmt.value):
                    proxies.add(target.id)
                    continue
                values = _string_list(stmt.value, consts)
                if values is not None:
                    consts[target.id] = values
                continue
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
                continue
            call = stmt.value
            if (
                isinstance(call.func, ast.Name)
                and call.func.id == "include"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
            ):
                pin = find_pin_files.label_literal_to_relpath(
                    call.args[0].value, "", by_name
                )
                if pin is not None:
                    queue.append(pin.relpath)
                continue
            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "env"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id in proxies
            ):
                continue
            for kw in call.keywords:
                if kw.arg not in labels:
                    continue
                values = _string_list(kw.value, consts)
                if values is None:
                    warnings.append(
                        f"{rel}:{kw.value.lineno}: zephyr_setup.env({kw.arg}) is not a "
                        "list of string literals; new files below it are not noticed"
                    )
                    continue
                labels[kw.arg].extend(values)

    dirs: list[str] = []

    def _add_tree(d: str):
        if d:
            dirs.append(d)
        else:
            dirs.extend(_child_dirs(workspace_root, d))

    for literal in labels["apps_dirs"]:
        d = _label_dir(workspace_root, literal, by_name)
        if d is not None:
            _add_tree(d)
    for literal in labels["boards_dirs"]:
        d = _label_dir(workspace_root, literal, by_name)
        if d is not None:
            dirs.extend(f"{d}/{s}" if d else s for s in _BOARD_ROOT_SUBDIRS)
    for literal in labels["modules"]:
        d = _label_dir(workspace_root, literal, by_name)
        if d is None:
            continue
        # Like setup.bzl, `<root>/zephyr/module.yml` names the module `<root>`,
        # including the workspace root itself (`//zephyr:module.yml`).
        if (d == "zephyr" or d.endswith("/zephyr")) and literal.endswith("module.yml"):
            d = d.rpartition("/")[0]
        _add_tree(d)

    # Drop duplicates and directories nested in another listed directory.
    unique: list[str] = []
    for d in sorted(set(dirs)):
        if not any(d.startswith(u + "/") for u in unique):
            unique.append(d)
    return {"module_files": module_files, "dirs": unique, "warnings": warnings}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    hash_p = sub.add_parser("hash")
    hash_p.add_argument("--root", required=True)
    hash_p.add_argument("--subdir", action="append", default=[])
    hash_p.add_argument("--out-dir", required=True)
    dirs_p = sub.add_parser("setup-dirs")
    dirs_p.add_argument("--workspace-root", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "hash":
        for name, value in manifests(args.root, args.subdir).items():
            with open(os.path.join(args.out_dir, name), "w", encoding="utf-8") as f:
                f.write(value + "\n")
        return 0
    json.dump(zephyr_setup_dirs(args.workspace_root), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
