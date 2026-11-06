# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Location-classified input tracking for Zephyr repository rules and module extensions.

When Bazel re-verifies a repository rule or a module extension (for example after a server
restart or a lockfile change), every recorded input that lives in *another external repository*
or is a directory listing (`DIRENTS`/`DIRTREE`) starts a new Skyframe batch, and each batch
re-checks every input recorded before it. Inputs in the main repository (`FILE:@@//...`) are
batched together and verified in parallel.

deps.bzl classifies reported inputs by their realpath:

1. Fetched external repositories (no <root>/.git):
   Fetched repositories (under $OUTPUT_BASE/external/ or in --repo_contents_cache) are immutable
   and cannot change unless their definition changes.
   -> deps.bzl never watches files inside fetched repos directly. This eliminates sequential
      Skyframe restarts. Instead, immutable repos are covered by watching the pin files
      (MODULE.bazel, patches, overlays) that define them (see find_pin_files()).
2. Main workspace content:
   These are mutable and actively edited by developers.
   -> deps.bzl watches them through their workspace-relative path (@@//...) as `FILE` inputs, so
      they are verified in parallel in batch 0 with zero extra batches.
3. External repo overrides (repo_root):
   To detect if an external repository transitions between a fetched repo and a local git checkout
   override, it watches <root>/.git once per repository.

Record inputs in this order: repository roots first (the only batch-starting inputs), then pin
files and generator-reported inputs via watch_deps(). Directories are watched as `FILE` inputs
(`DIR` or missing) rather than `DIRENTS`, avoiding per-directory Skyframe/RBE batches in Bazel 9+
and `InconsistentFilesystemException` when directories are deleted. Files added to or removed from
directories are noticed through the digests written by the skyframe_warmer and
zephyr_workspace_manifest repository rules, the only rules that record `DIRTREE` inputs.

Limitations:
*   Overrides must be git checkouts (or worktrees/submodules) for the probe to notice them being
    switched on or off. Switching between two different git checkouts of the same repository is
    not noticed.
*   Module extensions cannot watch paths outside the workspace, so overrides outside the
    workspace are only tracked by repository rules.
*   With `--watchfs`, Bazel does not notice changes under `.bazelignore`d directories, which
    includes `repository_overrides/`. Do not combine `--watchfs` with overrides.
"""

load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")

visibility(["//..."])

def new_tracker(ctx, workspace_root = None, zephyr_manifest = None):
    """Creates the tracking state for one repository rule or module extension invocation.

    Args:
        ctx: The repository_ctx or module_ctx.
        workspace_root: Path of the main workspace. Defaults to `rctx.workspace_root` for
            repository rules; module extensions resolve `@@//:MODULE.bazel`, which records a
            main-repository input.
        zephyr_manifest: Name of the digest to watch: "done" (for `zephyr_setup`), "kconfig_done"
            (for `@zephyr_kconfig`), or None to not watch one. It is read from `@skyframe_warmer`
            when @zephyr is a mutable checkout, and from `@zephyr_workspace_manifest` by
            watch_workspace_manifest() when @zephyr is not the main repository.

    Returns:
        A mutable dict to pass to the other functions in this file.
    """
    is_repo_rule = hasattr(ctx, "attr")
    if workspace_root == None:
        if is_repo_rule:
            workspace_root = ctx.workspace_root
        else:
            workspace_root = ctx.path(Label("@@//:MODULE.bazel")).dirname
    ws_real = str(workspace_root.realpath)
    zephyr_canon = Label("//:BUILD.bazel").workspace_name
    return {
        "ctx": ctx,
        # Paths are classified by realpath but watched through the workspace path, since Bazel
        # classifies watched paths lexically.
        "ws_path": workspace_root,
        "ws": str(workspace_root),
        "ws_real": ws_real,
        # Canonical repository name and realpath (with a trailing "/") of @zephyr.
        "zephyr_canon": zephyr_canon,
        "zephyr_real": (ws_real + "/") if zephyr_canon == "" else None,
        "zephyr_manifest": zephyr_manifest,
        "zephyr_prewarmed": zephyr_manifest == None,
        # Realpaths (with a trailing "/") of fetched external repositories.
        "fetched_roots": [],
        # Canonical repository name -> root path; "" is the main repository.
        "roots": {"": workspace_root},
        # Realpaths (with a trailing "/") of external repositories that resolve into the workspace.
        "local_roots": [],
        # Realpath (with a trailing "/") of the working directory, which must never be watched. It
        # may not exist yet in module extensions.
        "wd_real": realpath_of(ctx.path(".")) + "/",
        "watched": {},
        # Realpaths of directories listed by readdir(), whose paths watch_deps() records.
        "pending_dirs": [],
        # Only repository rules may watch paths outside the workspace.
        "watch_absolute": is_repo_rule,
    }

def _maybe_prewarm_zephyr(tracker):
    """Watches `@skyframe_warmer//:<zephyr_manifest>` once, when @zephyr is mutable.

    Resolving it first makes the warmer `watch_tree()` @zephyr, which computes every FileValue in
    the tree in parallel before the per-file watches of watch_deps() request them one at a time.
    """
    if tracker["zephyr_prewarmed"]:
        return
    zephyr_real = tracker["zephyr_real"]
    if zephyr_real == None or zephyr_real in tracker["fetched_roots"]:
        return
    tracker["zephyr_prewarmed"] = True
    tracker["ctx"].watch(Label("@skyframe_warmer//:" + tracker["zephyr_manifest"]))

def watch_workspace_manifest(tracker):
    """Watches `@zephyr_workspace_manifest//:<zephyr_manifest>` when @zephyr is not the main repo.

    Its content changes whenever a relevant file is added to or removed from the main-workspace
    directories named by the root module's `zephyr_setup.env()` tags (see
    zephyr_workspace_manifest), without recording a `DIRENTS` input (and Skyframe batch) per
    directory: `done` makes `zephyr_setup` notice new applications, boards and override files,
    and `kconfig_done` makes `@zephyr_kconfig` notice new Kconfig, binding, board metadata and
    `BUILD`/`.bzl` files in workspace modules and board roots.

    Args:
        tracker: The dict returned by new_tracker(), with `zephyr_manifest` set.
    """
    if tracker["zephyr_canon"] == "":
        # Zephyr is the main repository: its directories are covered by @skyframe_warmer.
        return
    manifest = tracker["zephyr_manifest"]
    if manifest == None:
        fail("watch_workspace_manifest() requires new_tracker(zephyr_manifest = ...)")
    tracker["ctx"].watch(Label("@zephyr_workspace_manifest//:" + manifest))

def repo_root(tracker, anchor):
    """Returns the root directory of the repository that contains `anchor`.

    The first call for an external repository resolves it (fetching it if needed) and records the
    `<root>/.git` probe. Later calls are free. The main repository needs no probe.

    Args:
        tracker: The dict returned by new_tracker().
        anchor: A Label, or a canonical label string, in that repository. Labels in the root
            package resolve through the probe itself; others are resolved directly (which also
            watches them) because their repository may not have a root package.

    Returns:
        The path of the repository root, as seen from the output base.
    """
    if type(anchor) == "string":
        anchor = Label(anchor)
    canon = anchor.workspace_name
    roots = tracker["roots"]
    root = roots.get(canon)
    if root != None:
        if canon == tracker["zephyr_canon"]:
            _maybe_prewarm_zephyr(tracker)
        return root

    ctx = tracker["ctx"]
    if anchor.package:
        root = ctx.path(anchor)
        for _ in (anchor.package + "/" + anchor.name).split("/"):
            root = root.dirname
    else:
        root = ctx.path(Label("@@%s//:.git" % canon)).dirname

    git = root.get_child(".git")
    # A no-op when resolving the label above already recorded it implicitly.
    ctx.watch(git)
    roots[canon] = root

    real = str(root.realpath)
    if canon == tracker["zephyr_canon"]:
        tracker["zephyr_real"] = real + "/"
    if (real + "/").startswith(tracker["ws_real"] + "/"):
        tracker["local_roots"].append(real + "/")
    elif not git.exists:
        tracker["fetched_roots"].append(real + "/")
    if canon == tracker["zephyr_canon"]:
        _maybe_prewarm_zephyr(tracker)
    return root

def label_path(tracker, label):
    """Returns the path of `label` like `ctx.path(label)`, but without watching it.

    Args:
        tracker: The dict returned by new_tracker().
        label: A Label or canonical label string.

    Returns:
        The path of the file or directory the label refers to (which may not exist).
    """
    if type(label) == "string":
        label = Label(label)
    root = repo_root(tracker, label)
    if label.package:
        return root.get_child(label.package + "/" + label.name)
    return root.get_child(label.name)

def realpath_of(path):
    """Returns `os.path.realpath()` of a path object that may not exist.

    Args:
        path: A path object.

    Returns:
        The realpath string. Missing trailing components are kept as they are.
    """
    suffix = ""
    p = path
    for _ in range(256):
        if p.exists:
            return str(p.realpath) + suffix
        parent = p.dirname
        if parent == None:
            break
        suffix = "/" + p.basename + suffix
        p = parent
    return str(path)

def workspace_relpath(tracker, real):
    """Returns `real` relative to the workspace root, or None if it is outside the workspace.

    Args:
        tracker: The dict returned by new_tracker().
        real: A realpath string.

    Returns:
        The relative path string ("" for the workspace root itself) or None.
    """
    ws_real = tracker["ws_real"]
    if real == ws_real:
        return ""
    if real.startswith(ws_real + "/"):
        return real[len(ws_real) + 1:]
    return None

def _file_watch_path(tracker, real):
    """Returns the path to watch for the realpath `real`, or None if it must not be watched."""
    if (real + "/").startswith(tracker["wd_real"]):
        return None
    rel = workspace_relpath(tracker, real)
    if rel != None:
        return tracker["ws"] + "/" + rel if rel else tracker["ws"]
    for fetched in tracker["fetched_roots"]:
        if (real + "/").startswith(fetched):
            # Immutable fetched content, covered by the pin files and the .git probes.
            return None
    if tracker["watch_absolute"]:
        return real
    return None

def _dir_watch_path(tracker, real):
    """Returns the workspace path to watch (as a `FILE` input) for the directory `real`, or None."""
    rel = workspace_relpath(tracker, real)
    if rel == None or (real + "/").startswith(tracker["wd_real"]):
        return None
    return tracker["ws"] + "/" + rel if rel else tracker["ws"]

def watch_deps(tracker, files = [], dirs = [], priority_files = []):
    """Watches the inputs a generator reported, according to where they live.

    Call it once, after all other inputs were recorded. Directories (including those of readdir())
    and files are watched via ctx.watch() as FILE inputs rather than DIRENTS: in Bazel 9+, every
    DIRENTS input starts a new Skyframe/RBE batch, and requesting the listing of a deleted
    directory fails with InconsistentFilesystemException. Watching directories as FILE inputs
    records their existence (DIR vs missing) in batch 0 with zero extra batches.

    Inside @zephyr, existing directory paths and speculative missing-file probes in `files` are
    skipped (watching an existing directory via ctx.watch() only records `DIR`, which never changes
    when entries inside are modified, while speculative per-board/per-app missing-file probes
    account for ~14,000 non-existent paths across the upstream tree). Out-of-tree workspace files
    and directories, existing @zephyr files, and all `priority_files` (including missing optional
    files for the active app/board) are watched in full.

    Args:
        tracker: The dict returned by new_tracker().
        files: Realpath strings of input files, including probed candidates that do not exist.
        dirs: Realpath strings of directories whose existence affects the result.
        priority_files: Realpath strings of high-priority input files (e.g. per-board/per-app
            DTS, binding, header, and conf inputs) that are always watched, including missing
            optional candidate paths.
    """
    ctx = tracker["ctx"]
    watched = tracker["watched"]
    zephyr_real = tracker["zephyr_real"]
    for real in priority_files:
        w = _file_watch_path(tracker, real)
        if w == None or w in watched:
            continue
        watched[w] = True
        ctx.watch(w)
    for real in files:
        w = _file_watch_path(tracker, real)
        if w == None or w in watched:
            continue
        if zephyr_real != None and (real + "/").startswith(zephyr_real):
            if not ctx.path(w).exists:
                watched[w] = False
                continue
        watched[w] = True
        ctx.watch(w)
    for real in tracker["pending_dirs"] + dirs:
        if zephyr_real != None and (real + "/").startswith(zephyr_real):
            continue
        w = _dir_watch_path(tracker, real)
        if w == None or w in watched:
            continue
        watched[w] = True
        ctx.watch(w)
    tracker["pending_dirs"] = []

def watch_paths(tracker, paths):
    """Like watch_deps(files = ...) for path objects that may not exist or may be symlinks.

    Args:
        tracker: The dict returned by new_tracker().
        paths: Path objects.
    """
    watch_deps(tracker, files = [realpath_of(p) for p in paths])

def readdir(tracker, path):
    """Lists a directory. Its path is watched by the next watch_deps() call, where allowed.

    Args:
        tracker: The dict returned by new_tracker().
        path: An existing directory.

    Returns:
        The entries, as path objects under `path`.
    """
    tracker["pending_dirs"].append(str(path.realpath))
    return path.readdir(watch = "no")

def watch_pins(tracker, pin_files):
    """Watches the pin files. They are main-repository inputs, so the order does not matter.

    Args:
        tracker: The dict returned by new_tracker().
        pin_files: Workspace-relative paths, as returned by find_pin_files().
    """
    ctx = tracker["ctx"]
    ws = tracker["ws_path"]
    watched = tracker["watched"]
    for rel in pin_files:
        p = ws.get_child(rel)
        w = str(p)
        if w not in watched:
            watched[w] = True
            ctx.watch(p)

def read_path_list(ctx, path):
    """Reads a file with one path per line, as written by the generators.

    Args:
        ctx: The repository_ctx or module_ctx.
        path: The path of the list file, normally in the working directory (so it isn't watched).

    Returns:
        The list of non-empty lines, or None if the file does not exist.
    """
    if not path.exists:
        return None
    return [line for line in ctx.read(path).splitlines() if line.strip()]

def find_pin_files(tracker, python, repo_relpaths = [""], extra_relpaths = []):
    """Returns the workspace files that pin fetched content.

    Runs `//bazel/tools/deps:find_pin_files.py`, which parses the Starlark AST of the
    `MODULE.bazel` of each given repository for labels of local files: patches, BUILD overlays,
    lock files, included `*.MODULE.bazel` files, and (in the main repository) `.bzl` files, which
    are scanned in turn. `@name//` labels are followed when `name` is the module name of the main
    repository or one of the given in-workspace overrides. Pass the returned list to `watch_pins()`
    to watch them as main-repository inputs.

    A label is a pin if it names an existing file, or has an explicit target name with an
    extension (so that a missing patch is watched too).

    Args:
        tracker: The dict returned by new_tracker().
        python: The Python runner struct returned by get_python().
        repo_relpaths: Workspace-relative roots of the repositories to scan: "" for the main
            repository, plus in-workspace overrides (whose MODULE.bazel may pin other repos).
        extra_relpaths: Additional workspace-relative pin files.

    Returns:
        A sorted list of workspace-relative paths.
    """
    script = label_path(tracker, Label("//bazel/tools/deps:find_pin_files.py"))
    script_rel = workspace_relpath(tracker, realpath_of(script))
    extras = list(extra_relpaths)
    if script_rel != None and script_rel not in extras:
        extras.append(script_rel)
    res = python.execute([
        str(script),
        "--workspace-root",
        tracker["ws"],
        "--repo-relpaths-json",
        json.encode(repo_relpaths),
        "--extra-relpaths-json",
        json.encode(extras),
    ])
    if res.return_code != 0:
        fail("Failed to find pin files:\n" + res.stderr)
    return json.decode(res.stdout)

# Top-level @zephyr directories that skyframe_warmer watches with `watch_tree()`. Each one is a
# `DIRTREE` input, which starts its own Skyframe batch (RepoRecordedInput.DirTree is never
# requested unconditionally), so the list is capped to keep @skyframe_warmer within the 20 batches
# that audit_recorded_inputs.py allows (16 trees + the @zephyr root probe + 2 inputs of
# get_python()). Directories left out (doc, kernel, misc, platforms, share, constraints,
# submanifests) hold no wildcard-sourced Kconfig files, bindings, boards or applications: their
# Kconfig files are sourced by name from watched files, so a new one is noticed through the edit
# that sources it.
_ZEPHYR_WARMER_SUBDIRS = [
    "arch",
    "bazel",
    "boards",
    "cmake",
    "drivers",
    "dts",
    "include",
    "lib",
    "modules",
    "samples",
    "scripts",
    "snippets",
    "soc",
    "subsys",
    "tests",
    "toolchain",
]

_MANIFEST_SCRIPT = "bazel/tools/deps/tree_manifest.py"

def _write_manifests(rctx, python, script, root, subdirs, outputs):
    """Runs tree_manifest.py to hash the discovery-relevant file names below `root/<subdirs>`."""
    args = [str(script), "hash", "--root", root, "--out-dir", str(rctx.path("."))]
    for sub in subdirs:
        args.extend(["--subdir", sub])
    res = python.execute(args)
    if res.return_code != 0:
        fail("%s failed (%d):\n%s" % (_MANIFEST_SCRIPT, res.return_code, res.stderr))
    for name in ["done", "kconfig_done"]:
        if name not in outputs:
            rctx.delete(name)
    rctx.file("BUILD.bazel", "exports_files(%s)\n" % json.encode(outputs))

def _skyframe_warmer_impl(rctx):
    tracker = new_tracker(rctx)
    zephyr_canon = tracker["zephyr_canon"]
    if zephyr_canon == "":
        zephyr_root = tracker["ws_path"]
    else:
        zephyr_root = rctx.path(Label("@@%s//:.git" % zephyr_canon)).dirname
    zephyr_real = str(zephyr_root.realpath)
    watch_root_str = _file_watch_path(tracker, zephyr_real)
    watch_root = rctx.path(watch_root_str) if watch_root_str != None else zephyr_root
    python = get_python(rctx)

    existing_subdirs = []
    for sub in _ZEPHYR_WARMER_SUBDIRS:
        d = watch_root.get_child(sub)
        if d.is_dir:
            rctx.watch_tree(d)
            existing_subdirs.append(sub)

    # The script itself lives under bazel/, which is watched above.
    _write_manifests(
        rctx,
        python,
        zephyr_root.get_child(_MANIFEST_SCRIPT),
        zephyr_real,
        existing_subdirs,
        ["done", "kconfig_done"],
    )

    # Not reproducible: the result depends on where @zephyr lives (e.g. different
    # --override_repository paths), which is not an attribute, and the rule is cheap to re-run.
    return None

skyframe_warmer = repository_rule(
    implementation = _skyframe_warmer_impl,
    attrs = COMMON_PY_REPO_RULE_ATTRS,
    doc = """Pre-warms Skyframe FileValues and tracks file additions and removals in @zephyr.

Only used when @zephyr is a mutable checkout (the main repository or a local git checkout
override), through new_tracker(zephyr_manifest = ...). It calls `watch_tree()` on the top-level
directories of @zephyr, so Bazel's DirectoryTreeDigestFunction computes all their FileValues in
parallel before the consumers watch thousands of files one at a time, and so this rule re-runs
whenever a file below them is added, removed or edited. It writes two digests of sorted relative
file names (see tree_manifest.py):

*   `done`: Kconfig, DTS, YAML, conf, CMake and Bazel files, watched by `zephyr_setup`.
*   `kconfig_done`: Kconfig, BUILD/.bzl, board/SoC/arch/module metadata and binding files, watched
    by `@zephyr_kconfig`.

Editing an existing file (e.g. a `.c` source) re-runs this rule but leaves both digests unchanged,
so the consumers are not re-run. `@zc_*` repositories do not watch it: they watch
`@zephyr_kconfig//:Kconfig.dts`, which embeds a digest of all Kconfig file paths and contents.
""",
)

def _zephyr_workspace_manifest_impl(rctx):
    ws = rctx.workspace_root
    python = get_python(rctx)
    script = rctx.path(Label("//bazel/tools/deps:tree_manifest.py"))
    res = python.execute([str(script), "setup-dirs", "--workspace-root", str(ws)])
    if res.return_code != 0:
        fail("%s setup-dirs failed (%d):\n%s" % (_MANIFEST_SCRIPT, res.return_code, res.stderr))
    info = json.decode(res.stdout)
    for warning in info["warnings"]:
        # buildifier: disable=print
        print("WARNING: zephyr_workspace_manifest: " + warning)
    for rel in info["module_files"]:
        rctx.watch(ws.get_child(rel))

    existing = []
    for rel in info["dirs"]:
        d = ws.get_child(rel)
        if d.is_dir:
            rctx.watch_tree(d)
            existing.append(rel)
        else:
            # Recorded as a (missing) path, so that creating the directory is noticed.
            rctx.watch(d)

    _write_manifests(rctx, python, script, str(ws.realpath), existing, ["done", "kconfig_done"])
    return None

zephyr_workspace_manifest = repository_rule(
    implementation = _zephyr_workspace_manifest_impl,
    attrs = COMMON_PY_REPO_RULE_ATTRS,
    doc = """Tracks file additions and removals in the main-workspace directories of zephyr_setup.

Module extensions cannot watch directory trees, and every `DIRENTS` input starts its own Skyframe
batch, so `zephyr_setup` and `@zephyr_kconfig` watch digests written by this rule instead (see
watch_workspace_manifest()). This rule parses the root module's MODULE.bazel (and its includes)
for `zephyr_setup.env()` tags, calls `watch_tree()` on the main-workspace directories they name
(apps_dirs trees, the boards/, dts/, soc/, snippets/ and zephyr/dts/ trees of boards_dirs, and
modules trees), and writes digests of the sorted names of the relevant files below them (see
tree_manifest.py), like skyframe_warmer:

*   `done`, watched by `zephyr_setup`: adding an application, a board, or an app
    `boards/<board>.conf` override re-runs it.
*   `kconfig_done`, watched by `@zephyr_kconfig`: adding or removing a Kconfig, binding, board/SoC
    metadata or `BUILD`/`.bzl` file in a workspace module or board root re-runs it (and, through
    `Kconfig.dts`, the `zc_*` repositories).

Editing existing files leaves both digests unchanged.

Only literal labels in the root module are understood; directories named by non-root modules
that are checked out inside the workspace are not tracked.
""",
)
