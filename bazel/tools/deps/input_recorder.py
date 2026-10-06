# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Records the filesystem inputs of the zephyr_setup and Kconfig scripts.

The scripts write them to `deps.txt` and `dep_dirs.txt` (or to the files given
by `--deps-out` and `--dirs-out`), so that the module extension or repository
rule that runs them can watch what affects their output.
"""

import os
import sys

DEPS_FILE = "deps.txt"
DEP_DIRS_FILE = "dep_dirs.txt"


def add_arguments(parser):
    """Adds the optional --deps-out and --dirs-out arguments to `parser`."""
    parser.add_argument(
        "--deps-out",
        help="Optional file to write the input files that can affect the "
        "output to (including probed candidates that do not exist), one "
        "realpath per line",
    )
    parser.add_argument(
        "--dirs-out",
        help="Optional file to write the directories whose listing can affect "
        "the output to, one realpath per line",
    )


class InputRecorder:
    """Records the filesystem inputs that can affect the output.

    `files` are files whose content matters, plus probed paths that do not
    exist but whose creation would change the output. `dirs` are directories
    whose listing (the set of entry names) matters.
    """

    def __init__(self, *sources):
        """Initializes a recorder for script inputs.

        `sources` are optional files of the calling script. When provided, they
        and this module are recorded, since their code decides the output.
        """
        self.files = set()
        self.dirs = set()
        self._realpaths = {}
        self._walked_trees = set()
        if sources:
            self.add(*sources, __file__)

    def add(self, *paths):
        """Records input files or probed candidate paths (existing or not)."""
        for p in paths:
            if p:
                self.files.add(self.realpath(str(p)))

    add_file = add

    def add_dir(self, *paths):
        """Records directories whose listing affects the outputs."""
        for p in paths:
            if p:
                self.dirs.add(self.realpath(str(p)))

    def add_tree(self, top, suffixes):
        """Records the os.walk() of `top`: every directory, and the files ending
        in `suffixes` (e.g. bindings YAML files loaded from a bindings dir)."""
        top_real = self.realpath(str(top))
        if top_real in self._walked_trees:
            return
        self._walked_trees.add(top_real)
        for root, _, filenames in os.walk(top):
            self.add_dir(root)
            self.add(*(os.path.join(root, f) for f in filenames if f.endswith(suffixes)))

    def add_python_modules(self, *roots):
        """Records the source file of every imported module located under `roots`.

        A module counts if its file is under a root either as given or with
        symlinks resolved (runfiles trees, for instance, symlink single files).
        """
        prefixes = tuple({
            p.rstrip(os.sep) + os.sep
            for r in roots if r
            for p in (os.path.abspath(r), self.realpath(str(r)))
        })
        for module in list(sys.modules.values()):
            path = getattr(module, "__file__", None)
            if isinstance(path, str) and path:
                resolved = self.realpath(path)
                if resolved.startswith(prefixes) or os.path.abspath(path).startswith(prefixes):
                    self.files.add(resolved)

    def add_kconfig_sources(self, kconfig_list_file):
        """Reads kconfig_list.txt and records every listed file path."""
        if not os.path.exists(kconfig_list_file):
            return
        with open(kconfig_list_file, "r", encoding="utf-8") as f:
            for line in f:
                path = line.strip()
                if path:
                    self.add(path)

    def snapshot(self):
        """Returns picklable (files, dirs) sets, e.g. to return from a worker process."""
        return set(self.files), set(self.dirs)

    def update(self, snapshot):
        """Merges a snapshot() taken from another recorder."""
        files, dirs = snapshot
        self.files.update(files)
        self.dirs.update(dirs)

    def realpath(self, path):
        """Same as os.path.realpath(), but memoized per ancestor directory."""
        if path and not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        result = self._realpaths.get(path)
        if result is None:
            parent, base = os.path.split(path)
            if parent and base not in ("", ".", ".."):
                result = os.path.join(self.realpath(parent), base)
                if os.path.islink(result):
                    result = os.path.realpath(result)
            else:
                result = os.path.realpath(path)
            self._realpaths[path] = result
        return result

    def write(self, deps_out=None, dirs_out=None, *, output_dir=None, exclude_dirs=()):
        """Writes sorted, unique realpaths, one per line.

        Pass either `deps_out` / `dirs_out` file paths (from `--deps-out` and
        `--dirs-out`), or `output_dir` to write `deps.txt` and `dep_dirs.txt`
        inside that directory while excluding paths under `output_dir` and any
        `exclude_dirs`.
        """
        if output_dir is not None:
            if deps_out is not None or dirs_out is not None:
                raise ValueError("Cannot specify both output_dir and deps_out/dirs_out")
            output_dir = str(output_dir)
            exclude_dirs = (output_dir, *exclude_dirs)
            deps_out = os.path.join(output_dir, DEPS_FILE)
            dirs_out = os.path.join(output_dir, DEP_DIRS_FILE)

        excluded = [self.realpath(str(d)) for d in exclude_dirs]

        def keep(p):
            if "\n" in p:
                return False
            return not any(p == e or p.startswith(e + os.sep) for e in excluded)

        for out, paths in ((deps_out, self.files), (dirs_out, self.dirs)):
            if out:
                lines = sorted({self.realpath(p) for p in paths if keep(self.realpath(p))})
                with open(
                    out, "w", encoding="utf-8", errors="surrogateescape", newline="\n"
                ) as f:
                    f.write("".join(line + "\n" for line in lines))
