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

def _requirement_to_py_repo_dir(ctx, dep):
    """Resolves the site-packages directory of a pip dependency.

    NOTE: Ideally rules_python provides a reliable API for this.
    """
    if type(dep) == "string":
        dep = Label(dep)
    pkg_dir = str(ctx.path(dep).dirname)
    build_bazel_path = ctx.path(pkg_dir + "/BUILD.bazel")
    repo_name = None

    # rules_python >= 0.40.0 uses dynamically generated repository hashes for wheel targets.
    # Read the hub-level BUILD file to get the actual resolved repository name.
    if build_bazel_path.exists:
        build_content = ctx.read(build_bazel_path)
        for line in build_content.splitlines():
            if '"' + _PIP_HUB_NAME + "_" in line and line.strip().endswith('",'):
                parts = line.split('"')
                if len(parts) >= 3:
                    actual_repo = parts[-2]
                    hub_repo_canonical = dep.workspace_name
                    if _PIP_HUB_NAME in hub_repo_canonical:
                        repo_name = hub_repo_canonical.replace(_PIP_HUB_NAME, actual_repo)
                        break

    if not repo_name:
        # Fallback to older rules_python handling if BUILD parsing fails
        py_version = DEFAULT_PYTHON_VERSION.replace(".", "")
        repo_name = "{}_{}_{}".format(
            dep.repo_name,
            py_version,
            dep.package,
        )

    wheel_build_file = ctx.path(Label("@@" + repo_name + "//:BUILD.bazel"))
    return str(wheel_build_file.dirname) + "/site-packages"

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
    }

    python_interpreter = str(ctx.path(python_interpreter_label))

    def _execute(args, **kwargs):
        environment = kwargs.pop("environment", {})
        environment.update(**py_env)

        return ctx.execute(
            [python_interpreter] + args,
            environment = environment,
            **kwargs
        )

    return struct(
        execute = _execute,
    )
