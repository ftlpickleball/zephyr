# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""This library contains helpers for running Python from a repository rule or module extension."""

load("@pythons_hub//:interpreters.bzl", "INTERPRETER_LABELS")
load("@pythons_hub//:versions.bzl", "DEFAULT_PYTHON_VERSION")

# This is private to zephyr-bazel.
visibility(["//..."])

_DEFAULT_HOST_PYTHON_VERSION = "python_{}_host".format(DEFAULT_PYTHON_VERSION.replace(".", "_"))
_DEFAULT_PYTHON_INTERPRETER_LABEL = INTERPRETER_LABELS.get(_DEFAULT_HOST_PYTHON_VERSION)
_PIP_HUB_NAME = "zephyr_pip_deps"

def _materialize_repo_dir(ctx, repo_name):
    """Fetches and materializes an external repository on disk by canonical name.

    With --experimental_remote_repo_contents_cache, Bazel keeps remote-cached
    repositories in an in-memory overlay filesystem until ctx.path(Label(...))
    is called on a Label belonging to that repository. Because rules_python hub
    and host-wrapper repositories (@zephyr_pip_deps, @python_3_11_host) indirect
    to separate backing repositories via BUILD aliases or symlinks, resolving a
    Label only in the hub repository leaves the backing repository unmaterialized
    on the host filesystem when passed to ctx.execute().
    """
    return ctx.path(Label("@@" + repo_name + "//:BUILD.bazel")).dirname

def host_whl_platform_tag(os_name, arch, py_version):
    """Returns the rules_python whl_config_setting tag for the host OS and CPU.

    Args:
        os_name: Host OS name (e.g. from ctx.os.name).
        arch: Host CPU architecture (e.g. from ctx.os.arch).
        py_version: Compact Python major+minor version string (e.g. "311").

    Returns:
        A whl_config_setting platform string such as "cp311_linux_x86_64".
    """
    os_lower = os_name.lower()
    if "mac" in os_lower or "darwin" in os_lower:
        host_os = "osx"
    elif "win" in os_lower:
        host_os = "windows"
    else:
        host_os = "linux"

    arch_lower = arch.lower()
    if arch_lower in ("aarch64", "arm64"):
        host_arch = "aarch64"
    elif arch_lower in ("x86_64", "amd64", "x64"):
        host_arch = "x86_64"
    else:
        host_arch = arch_lower

    return "cp{}_{}_{}".format(py_version, host_os, host_arch)

def select_whl_repo_name(build_content, py_version, host_platform, pip_hub_name = _PIP_HUB_NAME):
    """Selects the host-compatible backing wheel repository from a hub BUILD file.

    Parses rules_python's generated pkg_aliases() BUILD.bazel content, handling
    both version-only keys ("//_config:is_cp311") and multi-line
    whl_config_setting(...) keys with target_platforms tuples.

    Args:
        build_content: Text contents of the hub package BUILD.bazel file.
        py_version: Compact Python major+minor version string (e.g. "311").
        host_platform: Host whl_config_setting tag (e.g. "cp311_linux_x86_64").
        pip_hub_name: Pip hub repository prefix.

    Returns:
        The resolved repository name (e.g. "zephyr_pip_deps_311_pyyaml_..."),
        or None if no matching entry is found.
    """
    repo_prefix = '"{}_{}_'.format(pip_hub_name, py_version)
    platform_token = '"{}"'.format(host_platform)

    in_whl_config = False
    paren_depth = 0
    has_target_platforms = False
    matched_platform = False

    for line in build_content.splitlines():
        if not in_whl_config and "whl_config_setting(" in line:
            in_whl_config = True

        if in_whl_config:
            if "target_platforms" in line:
                has_target_platforms = True
            if platform_token in line:
                matched_platform = True
            paren_depth += line.count("(") - line.count(")")

        stripped = line.strip()
        if not in_whl_config or paren_depth <= 0:
            if repo_prefix in line and stripped.endswith('",'):
                if (not in_whl_config) or (not has_target_platforms) or matched_platform:
                    parts = line.split('"')
                    if len(parts) >= 3:
                        return parts[-2]
            if in_whl_config and stripped.endswith(","):
                # Finish non-matching entries (e.g. another Python version) before the next block.
                in_whl_config = False
                paren_depth = 0
                has_target_platforms = False
                matched_platform = False

    return None

def _requirement_to_py_repo_dir(ctx, dep):
    """Resolves the site-packages directory of a pip dependency.

    NOTE: Ideally rules_python provides a reliable API for this.
    """
    if type(dep) == "string":
        dep = Label(dep)
    pkg_dir = str(ctx.path(dep).dirname)
    build_bazel_path = ctx.path(pkg_dir + "/BUILD.bazel")
    repo_name = None
    py_version = "".join(DEFAULT_PYTHON_VERSION.split(".")[:2])

    # rules_python >= 0.40.0 uses dynamically generated repository hashes for wheel targets.
    # Read the hub-level BUILD file to get the actual resolved repository name.
    if build_bazel_path.exists:
        build_content = ctx.read(build_bazel_path)
        host_platform = host_whl_platform_tag(ctx.os.name, ctx.os.arch, py_version)
        actual_repo = select_whl_repo_name(build_content, py_version, host_platform)
        if actual_repo:
            hub_repo_canonical = dep.workspace_name
            if _PIP_HUB_NAME in hub_repo_canonical:
                repo_name = hub_repo_canonical.replace(_PIP_HUB_NAME, actual_repo)

    if not repo_name:
        # Fallback to older rules_python handling if BUILD parsing fails
        repo_name = "{}_{}_{}".format(
            dep.repo_name,
            py_version,
            dep.package,
        )

    return str(_materialize_repo_dir(ctx, repo_name)) + "/site-packages"

def _resolve_python_interpreter(ctx, label):
    """Resolves the host Python interpreter path and materializes its backing repo."""
    interp_path = ctx.path(label)

    # TODO(b/575637070): Remove this workaround once upstream Bazel fixes
    # RemoteExternalOverlayFileSystem.ensureMaterialized() to materialize
    # cached repositories targeted by symlinks in native repositories.
    # @python_3_11_host//:python is a symlink into the platform-specific
    # interpreter repository (e.g. rules_python++python+python_3_11_<platform>).
    # Calling interp_path.realpath fails with ENOENT in Bazel 9.3.0 when the
    # backing repository is only in the in-memory overlay filesystem, so read
    # the host repository's .marker file (with watch = "no") to find and
    # materialize the backing repository on disk before ctx.execute() runs.
    repo_dir = interp_path.dirname
    marker_file = repo_dir.dirname.get_child("@" + repo_dir.basename + ".marker")
    if marker_file.exists:
        for line in ctx.read(marker_file, watch = "no").splitlines():
            if "@@" in line and "//" in line:
                target_repo = line.split("@@", 1)[1].split("//", 1)[0]
                if target_repo and target_repo != repo_dir.basename:
                    _materialize_repo_dir(ctx, target_repo)

    return str(interp_path)

COMMON_PY_REPO_RULE_ATTRS = {
    "_python_interpreter": attr.label(
        default = _DEFAULT_PYTHON_INTERPRETER_LABEL,
    ),
}

def get_python(ctx, extra_import_paths = [], pip_deps = None):
    """Returns a struct with an `execute()` method for running Python scripts/modules.

    Usage:
        python = get_python(ctx)
        python.execute(["path/to/script.py", "--arg1=foo", "--arg2"])

    Args:
        ctx: Repository context (rctx) or module context (mctx).
        extra_import_paths: Extra directories to add to the Python include path
            (PYTHONPATH).
        pip_deps: Optional list of pip dependency labels to include in PYTHONPATH.
            If None, defaults to ctx.attr._pip_deps if available, otherwise empty.

    Returns:
        A struct with an `execute()` function to run Python scripts.
    """
    if hasattr(ctx, "attr"):
        python_interpreter_label = getattr(ctx.attr, "_python_interpreter", _DEFAULT_PYTHON_INTERPRETER_LABEL)
    else:
        python_interpreter_label = _DEFAULT_PYTHON_INTERPRETER_LABEL

    if pip_deps != None:
        pip_deps_labels = pip_deps
    elif hasattr(ctx, "attr") and hasattr(ctx.attr, "_pip_deps"):
        pip_deps_labels = ctx.attr._pip_deps
    else:
        pip_deps_labels = []

    pip_dep_dirs = [
        _requirement_to_py_repo_dir(ctx, dep)
        for dep in pip_deps_labels
    ]
    pythonpath = ":".join(extra_import_paths + pip_dep_dirs)

    py_env = {
        "PYTHONPATH": pythonpath,
        # The scripts may live in the workspace (e.g. an override of @zephyr), whose directory
        # listings can be watched: don't write __pycache__ next to them.
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "",
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
    }

    python_interpreter = _resolve_python_interpreter(ctx, python_interpreter_label)

    def _execute(args, **kwargs):
        environment = kwargs.pop("environment", {})
        environment.update(**py_env)

        return ctx.execute(
            [python_interpreter, "-B", "-s"] + args,
            environment = environment,
            **kwargs
        )

    return struct(
        execute = _execute,
    )
