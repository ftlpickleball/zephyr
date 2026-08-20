# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Utilities for handling Bazel runfiles."""

def resolve_runfiles_path(ctx, file):
    """Resolves the path of a file relative to the runfiles directory root.

    In Bazel, runfiles are structured in a directory containing subdirectories
    for each repository (including the main workspace).

    - For files in the main workspace, `file.short_path` is relative to the
      workspace root (e.g., `path/to/file.txt`). To access it in runfiles, we
      must prepend the workspace name (yielding `workspace_name/path/to/file.txt`).
    - For files in external repositories, `file.short_path` starts with `../`
      followed by the repository name (e.g., `../external_repo/path/to/file.txt`).
      To access it in runfiles, we must strip the `../` prefix (yielding
      `external_repo/path/to/file.txt`).

    Args:
        ctx: The rule context.
        file: The File object to resolve.

    Returns:
        The path string relative to the runfiles root, or None if file is None.
    """
    if not file:
        return None
    path = file.short_path
    if path.startswith("../"):
        # Strip "../" to get "repo_name/path/to/file"
        return path[3:]

    # Prepend workspace name to get "workspace_name/path/to/file"
    return ctx.workspace_name + "/" + path
