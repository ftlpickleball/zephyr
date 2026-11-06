# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Location-classified input tracking for Zephyr repository rules and module extensions.

When Bazel re-verifies a repository rule or a module extension (for example after a server
restart or a lockfile change), every recorded input that lives in *another external repository*
starts a new Skyframe batch, and each batch re-checks every input recorded before it. The cost
grows quadratically with the number of such inputs. Inputs in the main repository (and absolute
paths) are batched together and verified in parallel.

deps.bzl classifies reported inputs by their realpath:

1. Fetched external repositories (no <root>/.git):
   Fetched repositories (under $OUTPUT_BASE/external/ or in --repo_contents_cache) are immutable
   and cannot change unless their definition changes.
   -> deps.bzl never watches files inside fetched repos directly. This eliminates sequential
      Skyframe restarts. Instead, immutable repos are covered by watching the pin files
      (MODULE.bazel, patches, overlays) that define them (see find_pin_files()).
2. Main workspace content:
   These are mutable and actively edited by developers.
   -> deps.bzl watches them through their workspace-relative path (@@//...), so they are verified
      in parallel in batch 0 with zero restarts.
3. External repo overrides (repo_root):
   To detect if an external repository transitions between a fetched repo and a local git checkout
   override, it watches <root>/.git once per repository.

Record inputs in this order: repository roots first (the only batch-starting inputs), then other
files, then (in a single watch_deps() call at the end) directory listings and generator-reported
files. watch_deps() watches each listed directory as a path before recording a barrier and the
listing: in Bazel, requesting the listing of a deleted directory fails the build instead of
re-running the rule, so the deletion must be noticed in an earlier batch.

Limitations:
*   Overrides must be git checkouts (or worktrees/submodules) for the probe to notice them being
    switched on or off. Switching between two different git checkouts of the same repository is
    not noticed.
*   Module extensions cannot watch paths outside the workspace, so overrides outside the
    workspace are only tracked by repository rules.
*   With `--watchfs`, Bazel does not notice changes under `.bazelignore`d directories, which
    includes `repository_overrides/`. Do not combine `--watchfs` with overrides.
"""

visibility(["//..."])

def new_tracker(ctx, workspace_root = None):
    """Creates the tracking state for one repository rule or module extension invocation.

    Args:
        ctx: The repository_ctx or module_ctx.
        workspace_root: Path of the main workspace. Defaults to `rctx.workspace_root` for
            repository rules; module extensions resolve `@@//:MODULE.bazel`, which records a
            main-repository input.

    Returns:
        A mutable dict to pass to the other functions in this file.
    """
    is_repo_rule = hasattr(ctx, "attr")
    if workspace_root == None:
        if is_repo_rule:
            workspace_root = ctx.workspace_root
        else:
            workspace_root = ctx.path(Label("@@//:MODULE.bazel")).dirname
    return {
        "ctx": ctx,
        # Paths are classified by realpath but watched through the workspace path, since Bazel
        # classifies watched paths lexically.
        "ws_path": workspace_root,
        "ws": str(workspace_root),
        "ws_real": str(workspace_root.realpath),
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
        # Realpaths of directories listed by readdir(), whose listings watch_deps() records.
        "pending_dirs": [],
        "barrier_recorded": False,
        # Only repository rules may watch paths outside the workspace.
        "watch_absolute": is_repo_rule,
    }

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
    if (real + "/").startswith(tracker["ws_real"] + "/"):
        tracker["local_roots"].append(real + "/")
    elif not git.exists:
        tracker["fetched_roots"].append(real + "/")
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

def _dirents_watch_path(tracker, real):
    """Returns the workspace path whose listing to watch for the realpath `real`, or None."""
    rel = workspace_relpath(tracker, real)
    if rel == None or (real + "/").startswith(tracker["wd_real"]):
        return None
    return tracker["ws"] + "/" + rel if rel else tracker["ws"]

def _record_barrier(tracker):
    """Records an input in another repository, so that Bazel verifies earlier inputs first.

    When re-verifying recorded inputs, Bazel requests all inputs between two inputs from other
    repositories together. Requesting the listing of a directory that no longer exists fails the
    build (InconsistentFilesystemException) instead of marking the rule outdated, so the path
    watches of listed directories must be verified in an earlier batch than their listings.
    """
    if tracker["barrier_recorded"]:
        fail("watch_deps() may only record directory listings once per invocation")
    tracker["barrier_recorded"] = True
    ctx = tracker["ctx"]
    ctx.watch(ctx.path(Label("@bazel_tools//tools:BUILD")))

def watch_deps(tracker, files = [], dirs = []):
    """Watches the inputs a generator reported, according to where they live.

    Call it once, after all other inputs were recorded. Directory listings (including those of
    readdir()) are only watched for directories inside the workspace (including in-workspace
    overrides). Each listed directory is first watched as a path, then a barrier is recorded (see
    _record_barrier()), then the listings, then the files. A missing directory is only watched as a
    path, so that creating it is noticed.

    Args:
        tracker: The dict returned by new_tracker().
        files: Realpath strings of input files, including probed candidates that do not exist.
        dirs: Realpath strings of directories whose listing affects the result.
    """
    ctx = tracker["ctx"]
    watched = tracker["watched"]
    listings = []
    for real in tracker["pending_dirs"] + dirs:
        w = _dirents_watch_path(tracker, real)
        if w == None or ("dir:" + w) in watched:
            continue
        watched["dir:" + w] = True
        p = ctx.path(w)
        if w not in watched:
            watched[w] = True
            ctx.watch(p)
        if p.is_dir:
            listings.append(p)
    tracker["pending_dirs"] = []
    if listings:
        _record_barrier(tracker)
        for p in listings:
            p.readdir(watch = "yes")
    for real in files:
        w = _file_watch_path(tracker, real)
        if w == None or w in watched:
            continue
        watched[w] = True
        ctx.watch(w)

def watch_paths(tracker, paths):
    """Like watch_deps(files = ...) for path objects that may not exist or may be symlinks.

    Args:
        tracker: The dict returned by new_tracker().
        paths: Path objects.
    """
    watch_deps(tracker, files = [realpath_of(p) for p in paths])

def readdir(tracker, path):
    """Lists a directory. Its listing is watched by the next watch_deps() call, where allowed.

    Args:
        tracker: The dict returned by new_tracker().
        path: An existing directory.

    Returns:
        The entries, as path objects under `path`.
    """
    if tracker["barrier_recorded"]:
        fail("readdir() must be called before watch_deps()")
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
        if str(p) not in watched:
            watched[str(p)] = True
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
