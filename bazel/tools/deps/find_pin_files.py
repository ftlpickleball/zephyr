# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0
"""Finds workspace files that pin fetched repository content via Starlark AST."""

import argparse
import ast
import collections
from collections.abc import Iterator, Mapping, Sequence
import dataclasses
import json
import os
import sys

_INVALID_LABEL_SUBSTRINGS = (
    " ",
    "\t",
    "\n",
    "\r",
    "%",
    "{",
    "}",
    "$",
    "*",
    "\\",
    "..",
    "//",
)


@dataclasses.dataclass(frozen=True)
class PinLabel:
    """Resolved workspace-relative path of a local file label literal."""

    relpath: str
    explicit_name: bool
    repo_relpath: str


def _parse_ast(source: str | ast.Module) -> ast.Module | None:
    """Returns a parsed `ast.Module`, or `None` if `source` has syntax errors."""
    if isinstance(source, ast.Module):
        return source
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def module_name(content: str | ast.Module) -> str | None:
    """Returns the `name` of the `module()` call in `MODULE.bazel` content.

    Args:
        content: The contents or parsed AST of a `MODULE.bazel` file.

    Returns:
        The module name string, or `None` if there is no top-level `module()`
        call with a string literal name or if `content` has a syntax error.
    """
    tree = _parse_ast(content)
    if tree is None:
        return None
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
            continue
        call = stmt.value
        if not (isinstance(call.func, ast.Name) and call.func.id == "module"):
            continue
        for kw in call.keywords:
            if (
                kw.arg == "name"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
        if (
            call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        ):
            return call.args[0].value
    return None


def _iter_string_literals(node: ast.AST) -> Iterator[str]:
    """Yields string literals from an AST subtree, skipping docstrings/prints."""
    if (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ):
        # Standalone string expression statements are module/function docstrings.
        return
    if isinstance(node, ast.JoinedStr):
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("fail", "print"):
            return
        if node.func.id == "load":
            # In Starlark load("//pkg:file.bzl", "sym1", alias = "sym2"), only the
            # first positional argument is a file label; remaining arguments are
            # imported symbol names.
            if node.args:
                yield from _iter_string_literals(node.args[0])
            return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
        return
    for child in ast.iter_child_nodes(node):
        yield from _iter_string_literals(child)


def string_literals(content: str | ast.Module) -> list[str]:
    """Returns string literals in Starlark source parsed via Python's `ast`.

    Ignores comments, module/function docstrings, `fail()`/`print()` arguments,
    and imported symbol names in `load()` calls.

    Args:
        content: Starlark source code or a parsed `ast.Module`, e.g. from a
            `MODULE.bazel` or `.bzl` file.

    Returns:
        A list of decoded string literal values, or `[]` if `content` cannot be
        parsed.
    """
    tree = _parse_ast(content)
    if tree is None:
        return []
    return list(_iter_string_literals(tree))


def label_literal_to_relpath(
    literal: str,
    repo_relpath: str,
    repo_relpaths_by_name: Mapping[str, str] | None = None,
) -> PinLabel | None:
    """Maps a label literal from a `MODULE.bazel` or `.bzl` file to a relpath.

    Args:
        literal: The string literal, e.g. `"//patches/openair:0001-fix.patch"`.
        repo_relpath: Workspace-relative path of the repository the literal
            appears in (`""` for the main repository). `//` labels are relative
            to it; `@//` and `@@//` labels always refer to the main repository.
        repo_relpaths_by_name: Module name -> workspace-relative root of the
            main repository and in-workspace overrides, for `@name//` labels.

    Returns:
        A `PinLabel(relpath, explicit_name, repo_relpath)` or `None` if the
        literal is not a valid label of a local file.
    """
    if repo_relpaths_by_name is None:
        repo_relpaths_by_name = {}
    if literal.startswith("@@//"):
        rest, base = literal[4:], ""
    elif literal.startswith("@//"):
        rest, base = literal[3:], ""
    elif literal.startswith("//"):
        rest, base = literal[2:], repo_relpath
    elif (
        literal.startswith("@")
        and not literal.startswith("@@")
        and "//" in literal
    ):
        name, _, rest = literal[1:].partition("//")
        if name not in repo_relpaths_by_name:
            return None
        base = repo_relpaths_by_name[name]
    else:
        return None
    if any(bad in rest for bad in _INVALID_LABEL_SUBSTRINGS):
        return None
    explicit_name = ":" in rest
    if explicit_name:
        pkg, name = rest.split(":", 1)
    else:
        pkg, name = rest, rest.rpartition("/")[2]
    if not name or name.startswith("/") or name.endswith("/"):
        return None
    parts = [p for p in (base, pkg, name) if p]
    return PinLabel(
        relpath="/".join(parts),
        explicit_name=explicit_name,
        repo_relpath=base,
    )


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def find_pin_files(
    workspace_root: str,
    repo_relpaths: Sequence[str] = ("",),
    extra_relpaths: Sequence[str] = (),
) -> list[str]:
    """Returns the workspace files that pin fetched content.

    Scans the `MODULE.bazel` of each given repository for labels of local files:
    patches, BUILD overlays, lock files, included `*.MODULE.bazel` files, and
    (in the main repository) `.bzl` files, which are scanned in turn. `@name//`
    labels are followed when `name` is the module name of the main repository or
    one of the given in-workspace overrides.

    A label is a pin if it names an existing file, or has an explicit target
    name with an extension (so that a missing patch is watched too).

    Args:
        workspace_root: Path to the main Bazel workspace root directory.
        repo_relpaths: Workspace-relative roots of the repositories to scan:
            `""` for the main repository, plus in-workspace overrides (whose
            `MODULE.bazel` may pin other repos).
        extra_relpaths: Additional workspace-relative pin files.

    Returns:
        A sorted list of workspace-relative paths.
    """
    pins: set[str] = set(extra_relpaths)
    queue: collections.deque[tuple[str, str]] = collections.deque()
    by_name: dict[str, str] = {}
    parsed_trees: dict[str, ast.Module | None] = {}

    for repo_rel in repo_relpaths:
        module_rel = f"{repo_rel}/MODULE.bazel" if repo_rel else "MODULE.bazel"
        queue.append((module_rel, repo_rel))
        module_path = os.path.join(workspace_root, module_rel)
        if os.path.isfile(module_path):
            tree = _parse_ast(_read_text(module_path))
            parsed_trees[module_rel] = tree
            if tree is not None:
                name = module_name(tree)
                if name:
                    by_name[name] = repo_rel

    scanned: set[str] = set()
    while queue:
        rel, repo_rel = queue.popleft()
        if rel in scanned:
            continue
        scanned.add(rel)
        pins.add(rel)
        if rel in parsed_trees:
            source: str | ast.Module | None = parsed_trees.pop(rel)
            if source is None:
                continue
        else:
            file_path = os.path.join(workspace_root, rel)
            if not os.path.isfile(file_path):
                continue
            source = _read_text(file_path)
        for literal in string_literals(source):
            pin = label_literal_to_relpath(literal, repo_rel, by_name)
            if pin is None:
                continue
            pin_path = os.path.join(workspace_root, pin.relpath)
            is_file = os.path.isfile(pin_path)
            if not is_file and not (
                pin.explicit_name and "." in pin.relpath.rpartition("/")[2]
            ):
                continue
            pins.add(pin.relpath)
            if not is_file:
                continue
            if pin.relpath.endswith(".MODULE.bazel") or (
                pin.relpath.endswith(".bzl") and pin.repo_relpath == ""
            ):
                queue.append((pin.relpath, pin.repo_relpath))

    return sorted(pins)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `find_pin_files.py`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        required=True,
        help="Path to the main workspace root directory.",
    )
    parser.add_argument(
        "--repo-relpaths-json",
        default='[""]',
        help="JSON list of workspace-relative repository root paths.",
    )
    parser.add_argument(
        "--extra-relpaths-json",
        default="[]",
        help="JSON list of additional workspace-relative pin file paths.",
    )
    args = parser.parse_args(argv)
    pins = find_pin_files(
        workspace_root=args.workspace_root,
        repo_relpaths=json.loads(args.repo_relpaths_json),
        extra_relpaths=json.loads(args.extra_relpaths_json),
    )
    json.dump(pins, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
