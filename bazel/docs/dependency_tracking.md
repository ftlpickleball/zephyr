# Dependency tracking in the Zephyr Bazel integration

The Zephyr configuration is computed while Bazel loads the build, not by build actions:

| Where | What it computes | What it reads |
|---|---|---|
| `zephyr_setup` module extension ([setup.bzl](../setup.bzl)) | Modules, boards, applications and sysbuild metadata; declares `@zephyr_state`, `@zephyr_index`, `@zephyr_kconfig` | `module.yml`/BUILD files, `board.yml`, `prj.conf`, `sample.yaml`/`testcase.yaml`, `sysbuild.*`, app `boards/` dirs |
| `zephyr_setup_apps` module extension | One `zc_*` repository per application and board | `@zephyr_state//:state.json` |
| `@zephyr_kconfig` ([zephyr_kconfig_gen_symbols.bzl](../private/zephyr_kconfig_gen_symbols.bzl)) | The Kconfig schema of all boards | Every Kconfig file, board/SoC metadata, the BUILD/.bzl files scanned for symbols |
| `zc_*` ([zephyr_kconfig_gen_values.bzl](../private/zephyr_kconfig_gen_values.bzl)) | `.config`, devicetree and headers of one application and board | Kconfig files, config fragments, DTS files and their includes, bindings, generator scripts |

Bazel caches their results and re-runs them only when a *recorded input* changes. Every input
must be recorded for the results to be correct. How the inputs are recorded matters for speed,
because Bazel re-verifies them after every server restart and whenever the lockfile or marker file
is re-read.

## The cost model

Bazel re-verifies recorded inputs in order, in batches
(`RepoRecordedInput.WithValue.splitIntoBatches`). Each `FILE`, `DIRENTS` or `DIRTREE` input that
lives in *another external repository* starts a new batch, and each batch costs a Skyframe restart.
Inputs in the main repository and absolute paths join the current batch and are checked in
parallel. So 10,000 workspace files are cheap to re-verify, but 200 files spread over external
repositories take 200 sequential restarts. `DIRTREE` (`watch_tree`) inputs hash whole trees on
every check.

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
   These are mutable and actively edited by developers.
   `deps.bzl` watches them through their workspace-relative path (`@@//...`), so they are verified
   in parallel in batch 0 with zero restarts.
3. **External repo overrides (`repo_root`):**
   To detect if an external repository transitions between a fetched repo and a local git checkout
   override, it watches `<root>/.git` once per repository.

| Realpath is in | Watched how | Why |
|---|---|---|
| The main workspace | One `FILE` input per file, through its workspace path | Mutable; cheap to verify |
| A workspace directory whose listing matters (application trees, app `boards/` dirs, OOT board roots, OOT bindings directories) | `FILE` on the directory, then `DIRENTS` (see below) | Adding a file must re-run discovery |
| Fetched content under `$OUTPUT_BASE/external` | Not watched per file | Immutable; covered by the pin files |
| Anywhere else (repository rules only) | One `FILE` input per file | Module extensions cannot watch such paths |

**Pin files.** Fetched content only changes when its definition changes. `find_pin_files()`
collects the files that define it: `MODULE.bazel`, the `*.MODULE.bazel` files it includes, and the
patches, BUILD overlays and lock files they reference (also `@zephyr//` labels when `@zephyr` is
overridden inside the workspace). The extension and every generated repository watch them, so
bumping a `git_override` commit or editing a patch re-runs everything once. Extra files can be
added with `zephyr_setup.env(pin_files = [...])`.

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

## Ordering, and deleted directories

Bazel fails the build, and keeps failing it (also after a restart), when a directory whose
listing was recorded (`DIRENTS`) is deleted:

```
Inconsistent filesystem operations. ... is no longer an existing directory
```

`DirectoryListingFunction` throws instead of reporting the input as changed. The failure is avoided
when a `FILE` input on the same directory is verified in an *earlier batch*: its change marks the
rule outdated before the listing is requested. `watch_deps()` therefore records, in this order:

1. a `FILE` input for each directory whose listing is watched;
2. a barrier: one input in another repository (`@bazel_tools//tools:BUILD`), which starts a new
   batch;
3. the `DIRENTS` inputs, for directories that exist;
4. the `FILE` inputs of the reported files.

Record other inputs first and call `watch_deps()` once, at the end. `readdir()` lists a directory
without watching it and queues its listing for `watch_deps()`.

## What is noticed

| Change | Noticed |
|---|---|
| Edit an application's `prj.conf`, overlay, `Kconfig`, `sample.yaml`, `sysbuild.*` | Yes |
| Add an application, or a `boards/<board>.conf/.overlay` file | Yes (listings of workspace dirs) |
| Edit or add OOT board, DTS or binding files in the workspace | Yes |
| Edit a file of an in-workspace override: Kconfig, bindings, DTS, scripts | Yes |
| Add a file to a directory of an in-workspace override | Yes |
| Bump a `git_override`/`archive_override`, edit a patch or BUILD overlay | Yes (pin files) |
| Turn an override on or off | Yes (`.git` probes) |

## Limitations and hazards

* Adding or removing any file below the `apps_dirs` trees (which may include all of `//src`)
  re-runs the `zephyr_setup` extension on the next build (about 2.5 s), including temporary files
  created by editors. `out`, `bazel-*`, `__pycache__` and dot directories are not walked. The
  `zc_*` repositories and `zephyr_setup_apps` only re-run if the result changes.
* Overrides must be git checkouts (or worktrees/submodules) for the probe to notice them being
  switched on or off. Switching between two checkouts of the same repository is not noticed.
* Overrides outside the workspace are only tracked by repository rules; module extensions cannot
  watch paths outside the workspace.
* Retargeting a symlink is only noticed if the realpath of an input changes content too.
* With `--watchfs`, Bazel does not notice changes under `.bazelignore`d directories, which include
  `repository_overrides/`. Do not combine `--watchfs` with overrides.

## Auditing

[audit_recorded_inputs.py](../tools/deps/audit_recorded_inputs.py) prints what was recorded for
each Zephyr repository and module extension, and fails on `DIRTREE` inputs, too many batches, or
unguarded `DIRENTS` inputs:

```
bazel run @zephyr//bazel/tools/deps:audit_recorded_inputs -- $(bazel info output_base)
```
