# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

"""Utility for generating deterministic repository names for Zephyr contextual configurations."""

def normalize_app_label(app_label):
    """Normalizes an application label to a consistent path format.

    Args:
        app_label: The label of the application (e.g., //apps/blinky) or a string.

    Returns:
        A normalized string path.
    """
    if type(app_label) == "Label":
        if app_label.package:
            return app_label.package
        return app_label.name

    norm_app = str(app_label)

    # Discard repo part if present (e.g. @@repo//path -> path)
    if "//" in norm_app:
        norm_app = norm_app.split("//")[-1]

    norm_app = norm_app.strip("/").lstrip(":")

    # If the label has a target name, and it matches the last part of the package name, strip it.
    # e.g., examples/hello_bazel:hello_bazel -> examples/hello_bazel
    if ":" in norm_app:
        pkg, target = norm_app.split(":", 1)
        t_base = target
        for ext in [".elf", "_elf", "_bin", ".bin"]:
            if t_base.endswith(ext):
                t_base = t_base[:-len(ext)]
        if pkg.endswith(target) or target == pkg.split("/")[-1] or pkg.endswith(t_base) or t_base == pkg.split("/")[-1]:
            norm_app = pkg

    return norm_app

def get_app_hash(app_label):
    """Extracts and hashes an application label.

    Args:
        app_label: The label of the application (e.g., //apps/blinky).

    Returns:
        An 8-character deterministic hash string for the app.
    """
    norm_app = normalize_app_label(app_label)

    # 2. Hash to 8 characters for collision resistance.
    # We use a 32-bit unsigned hex representation of the Starlark hash.
    h = hash(norm_app)
    app_hash = "%x" % (h & 0xFFFFFFFF)
    app_hash = ("00000000" + app_hash)[-8:]
    return app_hash

def sanitize_board_id(board_id):
    """Sanitizes a board ID for use in a repository name.

    Args:
        board_id: The Zephyr board ID (e.g., nrf52840dk/nrf52840).

    Returns:
        A sanitized board ID safe for repository names.
    """
    return board_id.replace("/", "_").replace("-", "_").replace(".", "_").replace("@", "_")

def get_zc_repo_name_from_precomputed(app_hash, safe_board):
    """Generates a deterministic repository name from a precalculated app hash and a pre-sanitized board ID.

    Args:
        app_hash: Precomputed app hash from get_app_hash.
        safe_board: Precomputed safe board name from sanitize_board_id.

    Returns:
        A string following the pattern zc_<app_hash>_<safe_board>.
    """
    return "zc_%s_%s" % (app_hash, safe_board)

def get_zc_repo_name_from_hash(app_hash, board_id):
    """Generates a deterministic repository name from a precalculated app hash and board ID.

    Args:
        app_hash: Precomputed app hash from get_app_hash.
        board_id: The Zephyr board ID.

    Returns:
        A string following the pattern zc_<app_hash>_<board_id>.
    """
    safe_board = sanitize_board_id(board_id)
    return get_zc_repo_name_from_precomputed(app_hash, safe_board)

def get_zc_repo_name(app_label, board_id):
    """Generates a deterministic repository name for an (app, board) combination.

    Args:
        app_label: The label of the application (e.g., //apps/blinky).
        board_id: The Zephyr board ID (e.g., nrf52840dk/nrf52840).

    Returns:
        A string following the pattern zc_<app_hash>_<board_id>.
    """
    app_hash = get_app_hash(app_label)
    return get_zc_repo_name_from_hash(app_hash, board_id)

def normalize_repo_name(name):
    """Normalizes a Bzlmod canonical repository name to a simple @name.

    Args:
        name: The canonical repository name.

    Returns:
        The normalized repository name starting with @@ for canonical names or @ for apparent names.
    """
    if not name:
        return ""

    # Handle @@+zephyr_patch_file+zephyr -> @zephyr (if we want the apparent name)
    # But for absolute references in repo rules, we often want the canonical one.
    if name.startswith("@@"):
        return name
    if name.startswith("+"):
        return "@@" + name
    if name.endswith("+") or "+" in name or "~" in name:
        return "@@" + name
    return "@" + name

def parse_label(label_or_str):
    """Parses a label or string into its component parts, including the apparent repo name.

    Args:
        label_or_str: A Label object or a string representation of a label.

    Returns:
        A struct containing:
            canonical_repo: The full canonical name (e.g., '@@+_repo_rules+hal_atmel' or '@@//').
            apparent_repo: The base/apparent name of the repository (e.g., 'hal_atmel' or '').
            package: The package path (e.g., 'modules/foo' or '').
            name: The target name (e.g., 'my_module' or '').
    """

    # Purely manual string parsing for all string inputs to avoid repo mapping issues in tests
    canonical_repo = ""
    apparent_repo = ""
    package = ""
    name = ""

    if type(label_or_str) == "Label":
        lbl = label_or_str
        if lbl.workspace_name:
            canonical_repo = "@@" + lbl.workspace_name
            apparent_repo = lbl.workspace_name
        else:
            canonical_repo = "@@"
            apparent_repo = ""
        package = lbl.package
        name = lbl.name
    else:
        label_str = str(label_or_str)

        if label_str.startswith("@@"):
            # Canonical label
            if "//" in label_str:
                canonical_repo, rest = label_str.split("//", 1)
                if ":" in rest:
                    package, name = rest.split(":", 1)
                else:
                    package = rest
            else:
                canonical_repo = label_str

            c_name = canonical_repo[2:]
            if "~" in c_name:
                parts = c_name.split("~")
                if len(parts) >= 2:
                    apparent_repo = parts[0]
            elif "+" in c_name:
                parts = c_name.split("+")
                if len(parts) >= 4 and parts[1] == "":
                    apparent_repo = parts[3]
                elif len(parts) >= 3 and parts[0] == "" and parts[1] == "_repo_rules":
                    apparent_repo = parts[2]
                else:
                    apparent_repo = parts[-1]
            else:
                apparent_repo = c_name
        elif label_str.startswith("@"):
            # Apparent label
            if "//" in label_str:
                repo_part, rest = label_str.split("//", 1)
                apparent_repo = repo_part[1:]
                canonical_repo = "@@" + apparent_repo  # Fallback for unmapped repos in tests
                if ":" in rest:
                    package, name = rest.split(":", 1)
                else:
                    package = rest
            else:
                apparent_repo = label_str[1:]
                canonical_repo = "@@" + apparent_repo
        else:
            # Local label (main workspace)
            canonical_repo = "@@"
            apparent_repo = ""
            if label_str.startswith("//"):
                rest = label_str[2:]
                if ":" in rest:
                    package, name = rest.split(":", 1)
                else:
                    package = rest
            elif ":" in label_str:
                package = native.package_name()
                name = label_str.split(":", 1)[1]
            else:
                package = native.package_name()
                name = label_str

    return struct(
        canonical_repo = canonical_repo,
        apparent_repo = apparent_repo,
        package = package,
        name = name,
    )

def derive_module_label(dir_label_str, relpath, name):
    """Derives a normalized canonical label for a module.

    Args:
        dir_label_str: The base directory label string (e.g., '@hal_atmel//' or '//mock_modules_dir').
        relpath: Relative path from the base directory to the module.
        name: The target name of the module.

    Returns:
        A canonical label string starting with @@.
    """
    info = parse_label(dir_label_str)

    if info.package and relpath:
        new_pkg = info.package + "/" + relpath
    elif info.package:
        new_pkg = info.package
    else:
        new_pkg = relpath

    if info.canonical_repo and info.canonical_repo != "@@":
        return "%s//%s:%s" % (info.canonical_repo, new_pkg, name)
    else:
        return "@@//%s:%s" % (new_pkg, name)

def resolve_module_roots(ctx_or_rctx, state):
    """Resolves the absolute paths of all module roots from the state.

    Args:
        ctx_or_rctx: The module context (mctx) or repository context (rctx).
        state: The decoded state JSON dict.

    Returns:
        A list of string paths to the module roots.
    """
    resolved_modules = []

    # Process both standard and config-only modules
    for m_set in ["modules", "config_only_modules"]:
        m_dict = state.get(m_set, {})
        if type(m_dict) == "dict":
            for m_info in m_dict.values():
                m_label_str = m_info.get("original")
                if m_label_str:
                    m_label = Label(m_label_str)
                    m_path = ctx_or_rctx.path(m_label)

                    if m_path.basename == "module.yml" and m_path.dirname.basename == "zephyr":
                        mod_root = m_path.dirname.dirname
                    else:
                        mod_root = m_path.dirname

                    relpath = m_info.get("relpath")
                    if relpath:
                        mod_root = mod_root.get_child(relpath)

                    path_str = str(mod_root)
                    if path_str not in resolved_modules:
                        resolved_modules.append(path_str)

    return resolved_modules

def get_repo_root(repo_name):
    """Returns the canonical external repository path prefix."""
    if repo_name.startswith("@"):
        repo_name = repo_name[1:]
    return "external/+_repo_rules+" + repo_name

def get_zephyr_bazel_root():
    """Returns the root path for zephyr."""
    return "."

