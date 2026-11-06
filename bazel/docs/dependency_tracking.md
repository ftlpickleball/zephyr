# Dependency tracking in the Zephyr Bazel integration

The Zephyr configuration is computed while Bazel loads the build, not by build actions:

| Where | What it computes | What it reads |
|---|---|---|
| `zephyr_setup` module extension ([setup.bzl](../setup.bzl)) | Modules, boards, applications and sysbuild metadata; declares `@zephyr_state`, `@zephyr_index` (`index.bzl` and `:local_modules` in [zephyr_state.bzl](../private/zephyr_state.bzl)), `@zephyr_kconfig` | `module.yml`/BUILD files, `board.yml`, `prj.conf`, `sample.yaml`/`testcase.yaml`, `sysbuild.*`, app `boards/` dirs |
| `zephyr_setup_apps` module extension | One `zc_*` repository per application and board | `@zephyr_state//:state.json` |
| `@zephyr_kconfig` ([zephyr_kconfig_gen_symbols.bzl](../private/zephyr_kconfig_gen_symbols.bzl)) | The Kconfig schema of all boards (`BUILD.bazel`, `symbols.txt`, and `Kconfig.dts`, with flags filtered to `CONFIG_*` symbols referenced in `BUILD`/`.bzl` files) | Every Kconfig file, board/SoC metadata, `dts/bindings/*.yaml` files, and the module/app `BUILD`/`.bzl` files (`app_build_files`) scanned for referenced `CONFIG_*` symbols |
| `zc_*` ([zephyr_kconfig_gen_values.bzl](../private/zephyr_kconfig_gen_values.bzl)) | `.config`, devicetree and headers of one application and board | `@zephyr_kconfig//:symbols.txt` and `Kconfig.dts`, Kconfig files, config fragments, DTS files and their includes, bindings, generator scripts |

Bazel caches their results and re-runs them only when a *recorded input* changes. Every input
must be recorded for the results to be correct. How the inputs are recorded matters for speed,
because Bazel re-verifies them after every server restart and whenever the lockfile or marker file
is re-read.

## The cost model

Bazel re-verifies recorded inputs in order, in batches
(`RepoRecordedInput.WithValue.splitIntoBatches`). Each input that lives in
*another external repository* (`!canBeRequestedUnconditionally()`) or is a
directory listing (`DIRENTS`/`DIRTREE` in Bazel 9+) starts a new batch, and
each batch costs a Skyframe restart (and a synchronous remote cache round-trip
when `--experimental_remote_repo_contents_cache` is enabled). `FILE` inputs in
the main repository (`FILE:@@//...`) join the current batch and are checked in
parallel. However, on a cold `--output_base`, watching tens of thousands of
uncached `FileValue`s sequentially via `ctx.watch()` triggers $O(N^2)$
`SkyFunctionEnvironment.batchPrefetch()` restarts on the Starlark worker thread.
`DIRTREE` (`watch_tree`) inputs hash whole trees on every check.

## How inputs are classified

All the rules use the helpers in [deps.bzl](../private/deps.bzl). Generators and discovery scripts
report what they read as realpaths, and each path is classified and watched according to where it
really lives:

1. **Fetched content under `$OUTPUT_BASE/external/`:**
   Fetched repositories are immutable. Their contents cannot change unless their definition changes.
   `deps.bzl` never watches files inside external repos directly. This single rule is what eliminates
   sequential Skyframe restarts. Immutable repos are covered by watching the pin files
   (`MODULE.bazel`, patches, overlays) that define them (see `find_pin_files()`).
2. **Main workspace content:**
   These are mutable and actively edited by developers. `deps.bzl` watches them
   through their workspace-relative path (`@@//...`) as `FILE` inputs, so they
   are verified in parallel in batch 0 with zero extra batches. Additions and
   removals inside directories are tracked by the directory-tree trackers
   described [below](#directory-trees), not by `DIRENTS` inputs.
3. **External repo overrides (`repo_root`):**
   To detect if an external repository transitions between a fetched repo and a local git checkout
   override, it watches `<root>/.git` once per repository.

| Realpath is in | Watched how | Why |
|---|---|---|
| The main workspace | One `FILE` input per file, through its workspace path | Mutable; cheap to verify |
| A workspace directory whose listing matters (application trees, app `boards/` dirs, `snippets/` dirs, OOT board roots, OOT bindings directories) | One `FILE` input on the directory (`DIR` or missing); its listing is covered by a [directory-tree tracker](#directory-trees) | Creating or deleting the directory re-runs discovery without one `DIRENTS` batch per directory |
| A fetched external repository (`fetched_roots`: no `<root>/.git`, under `$OUTPUT_BASE/external/` or `--repo_contents_cache`) | Not watched per file | Immutable; covered by the pin files and `.git` probes |
| Anywhere else (repository rules only) | One `FILE` input per file | Module extensions cannot watch such paths |

**Pin files.** Fetched content only changes when its definition changes. `find_pin_files()`
([find_pin_files.py](../tools/deps/find_pin_files.py)) parses the Starlark AST to collect the files
that define it: `MODULE.bazel`, the `*.MODULE.bazel` files it includes, and the patches, BUILD
overlays and lock files they reference (also `@zephyr//` labels when `@zephyr` is the main
workspace or overridden inside the workspace). The extension and every generated repository watch
them, so bumping a `git_override` commit or editing a patch re-runs everything once. Extra files
can be added with `zephyr_setup.env(pin_files = [...])`.

**Override probes.** `repo_root()` resolves each external repository once and watches
`<root>/.git`: it doesn't exist in fetched repositories and exists in git checkouts used as
overrides. Switching an override on or off therefore re-runs the rules.

**Generator contract.** `kconfig_gen_values.py` and `kconfig_gen_symbols.py` write `deps.txt` and
`dep_dirs.txt` into their output directory. The discovery scripts in `bazel/tools/metadata` write
the same lists when passed `--deps-out FILE --dirs-out FILE`. Both lists hold absolute realpaths,
sorted and unique, one per line:

* `deps.txt`: every file read, and every candidate path that was probed but does not exist when
  creating it would change the result (for example `boards/<board>.overlay` in an application).
* `dep_dirs.txt`: every directory whose listing affects the result (walked trees, globbed
  directories, bindings directories).

When a script reads a new kind of input, it must add it to these lists.

## Directory trees

Module extensions cannot watch directory trees, and every `DIRENTS` or
`DIRTREE` input starts its own batch, so neither is recorded by `zephyr_setup`,
`@zephyr_kconfig` or `zc_*`. Instead, two small repository rules in
[deps.bzl](../private/deps.bzl) call `watch_tree()` on the relevant trees and
write SHA-256 digests of the sorted names of the discovery-relevant files below
them ([tree_manifest.py](../tools/deps/tree_manifest.py)). The consumers watch
those digest files. Editing an existing file re-runs the tracker but leaves the
digests unchanged, so only adding or removing a relevant file re-runs the
consumers; edits to existing files are noticed through per-file watches.

* **`@skyframe_warmer`**, used only when `@zephyr` is a mutable checkout (the
  main workspace or a local git checkout override). It watches 16 top-level
  directories of `@zephyr` (`arch`, `bazel`, `boards`, `cmake`, `drivers`,
  `dts`, `include`, `lib`, `modules`, `samples`, `scripts`, `snippets`, `soc`,
  `subsys`, `tests` and `toolchain`), which also makes Bazel's
  `DirectoryTreeDigestFunction` compute all their `FileValue`s in parallel
  before the consumers watch ~3,000 files in `zephyr_setup` and ~16,000 files
  in `@zephyr_kconfig` one at a time. It writes:
  * `done`, over Kconfig, DTS, YAML, conf, CMake and Bazel files, watched by
    `zephyr_setup` (`new_tracker(zephyr_manifest = "done")`);
  * `kconfig_done`, over Kconfig, `BUILD`/`.bzl`, board/SoC/arch/module
    metadata and binding files, watched by `@zephyr_kconfig`
    (`new_tracker(zephyr_manifest = "kconfig_done")`).

  `zc_*` repositories do not watch it. `kconfig_gen_symbols.py` appends
  `# kconfig_inputs_sha256: <sha256>` over the paths and contents of every
  Kconfig file it read and every binding it scanned for `Kconfig.dts` to
  `@zephyr_kconfig//:Kconfig.dts`, which every `zc_*` watches. Editing, adding
  or removing a global Kconfig file or a binding therefore re-runs `zc_*`, even
  when the generated `DT_COMPAT_*` symbols stay the same (a bus variant of an
  existing compatible, an out-of-tree binding overriding an in-tree compatible,
  or a shared base binding without `compatible:`), while adding an unrelated
  `testcase.yaml` does not. Other `@zephyr` inputs of a `zc_*` repository are
  watched per file only when `filter_zc_deps()` in
  [zephyr_kconfig_gen_values.bzl](../private/zephyr_kconfig_gen_values.bzl)
  keeps them: files of the application and board directories, DTS, conf,
  header and Python files, hardware and module metadata, matched bindings,
  `version.h.in`, and the sysbuild Kconfig files (`share/sysbuild/` and
  `Kconfig.sysbuild`), which `kconfig_inputs_sha256` does not cover.
* **`@zephyr_workspace_manifest`**, used when `@zephyr` is not the main
  repository (`watch_workspace_manifest()`). It parses the root `MODULE.bazel`
  and the files it includes for `zephyr_setup.env()` tags and watches the
  main-workspace trees they name: `apps_dirs`, the `boards/`, `dts/`, `soc/`,
  `snippets/` and `zephyr/dts/` subdirectories of `boards_dirs`, and
  `modules`. Like `@skyframe_warmer`, it writes:
  * `done`, watched by `zephyr_setup`, which changes when an application, a
    board, or an app `boards/<board>.conf`/`.overlay` override is added or
    removed;
  * `kconfig_done`, watched by `@zephyr_kconfig`, which changes when a
    Kconfig, binding, board/SoC metadata or `BUILD`/`.bzl` file is added to or
    removed from a workspace module or board root. `zephyr_setup` re-running
    does not change the attributes of `@zephyr_kconfig` in that case, so
    without this digest it would not re-run.

Both trackers are not `reproducible`: their results depend on where the trees
live, which is not an attribute. `audit_recorded_inputs.py` allows `DIRTREE`
inputs only in them. Both are declared in `@zephyr`'s own `MODULE.bazel` and
referenced through its repo mapping, so downstream modules do not declare or
configure them.

## Ordering, and deleted directories

Bazel fails the build, and keeps failing it (also after a restart), when a directory whose
listing was recorded (`DIRENTS`) is deleted:

```
Inconsistent filesystem operations. ... is no longer an existing directory
```

`DirectoryListingFunction` throws instead of reporting the input as changed, and
in Bazel 9+ every `DIRENTS` input starts a separate Skyframe/RBE batch
(`RepoRecordedInput.Dirents.canBeRequestedUnconditionally()` returns `false`).
`watch_deps()` therefore watches reported directories via `ctx.watch()` as
`FILE` inputs (`DIR` when present, missing when absent) rather than recording
`DIRENTS`. Creating or deleting a directory transitions its `FILE` input in
batch 0 without throwing `InconsistentFilesystemException` or multiplying
batches.

Record repository roots and pin files first and call `watch_deps()` once, at the
end. `readdir()` lists a directory with `watch = "no"` and queues its path for
`watch_deps()`.

## What is noticed

| Change | Noticed |
|---|---|
| Edit an application's `prj.conf`, overlay, `Kconfig`, `sample.yaml`/`testcase.yaml`, `sysbuild.*` | Yes |
| Add an application, or a `boards/<board>.conf/.overlay` file | Yes (`@zephyr_workspace_manifest` or `@skyframe_warmer`) |
| Edit or add OOT board, DTS or binding files in the workspace | Yes (additions: `@zephyr_workspace_manifest`) |
| Edit a file of an in-workspace override: Kconfig, bindings, DTS, scripts | Yes |
| Add a Kconfig, binding, board, `BUILD` or application file to an in-workspace override | Yes (`@skyframe_warmer`, except in `doc`, `kernel`, `misc`, `platforms`, `share`) |
| Bump a `git_override`/`archive_override`, edit a patch or BUILD overlay | Yes (pin files) |
| Turn an override on or off | Yes (`.git` probes) |

## Limitations and hazards

* Adding or removing a Kconfig, DTS, YAML, conf, CMake or Bazel file below the
  `apps_dirs` trees (which may include all of `//src`) re-runs the
  `zephyr_setup` extension on the next build (about 2.5 s). Other files, and
  `out`, `bazel-*`, `__pycache__` and dot directories, are ignored. The `zc_*`
  repositories and `zephyr_setup_apps` only re-run if the result changes.
* `@zephyr_workspace_manifest` only understands string-literal labels (or list
  variables of them) in the root module's `zephyr_setup.env()` tags; it prints
  a warning for anything else. Directories named by non-root modules checked
  out inside the workspace are not tracked for additions. Each watched tree is
  one `DIRTREE` input and batch; an `apps_dirs` label naming the workspace root
  is expanded to its top-level directories, which can exceed `--max-batches`
  in a large workspace. Prefer specific `apps_dirs`.
* `@skyframe_warmer` does not watch `doc`, `kernel`, `misc`, `platforms`,
  `share` or other top-level `@zephyr` directories (each watched tree costs a
  batch). Their Kconfig files are sourced by name, so a new one is noticed
  through the edit that sources it, but a new `BUILD` file there is not.
* Overrides must be git checkouts (or worktrees/submodules) for the probe to
  notice them being switched on or off. Switching between two checkouts of the
  same repository is not noticed.
* Overrides outside the workspace are only tracked by repository rules; module
  extensions cannot watch paths outside the workspace.
* Retargeting a symlink is only noticed if the realpath of an input changes
  content too.
* With `--watchfs`, Bazel does not notice changes under `.bazelignore`d
  directories, which include `repository_overrides/`. Do not combine `--watchfs`
  with overrides.

## Auditing

[audit_recorded_inputs.py](../tools/deps/audit_recorded_inputs.py) reads
repository marker files (`$OUTPUT_BASE/external/@<repo>.marker` or
`<realpath(external/<repo>)>.recorded_inputs` in `--repo_contents_cache`) and
lockfile module extension entries, prints what was recorded for each Zephyr
repository and module extension, and fails on `DIRTREE` inputs (outside the
[directory-tree trackers](#directory-trees)), too many inputs (`--max-inputs`,
default 25,000) or batches (`--max-batches`), or unguarded `DIRENTS` inputs:

```
bazel run @zephyr//bazel/tools/deps:audit_recorded_inputs -- $(bazel info output_base)
```
