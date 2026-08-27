# SPDX-FileCopyrightText: Copyright 2025 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")
load("//bazel:naming.bzl", "derive_module_label", "get_app_hash", "get_zc_repo_name_from_precomputed", "parse_label", "sanitize_board_id")
load("//bazel/private:repo_rule_python.bzl", "COMMON_PY_REPO_RULE_ATTRS", "get_python")
load("//bazel/private:zephyr_kconfig_gen_symbols.bzl", "zephyr_kconfig_schema")
load("//bazel/private:zephyr_kconfig_gen_values.bzl", "gen_zephyr_config")
load("//bazel/private:zephyr_state.bzl", "zephyr_index_repo", "zephyr_state_repo")

# --- Helper Functions ---

def _parse_board_id(board_id):
    """Splits a board_id string into (board_name, qualifiers, board_rev)."""
    board_name, _, rev_and_qual = board_id.partition("@")
    board_rev, _, rev_qualifiers = rev_and_qual.partition("/")
    board_name, slash, name_qualifiers = board_name.partition("/")
    qualifiers = name_qualifiers if slash else rev_qualifiers
    return board_name, qualifiers, board_rev

def _get_override_candidates(board_name, qualifiers, board_rev, ext):
    """Returns application boards/ override candidate filenames in precedence order."""
    safe_q = qualifiers.lstrip("/").replace("/", "_")
    safe_rev = board_rev.replace(".", "_") if board_rev else ""

    bases = [board_name]
    if safe_q:
        parts = qualifiers.lstrip("/").split("/")
        for i in range(0, len(parts)):
            q_sub = "_".join(parts[:i + 1])
            bases.append("%s_%s" % (board_name, q_sub))

    candidates = ["%s.%s" % (b, ext) for b in bases]
    if safe_rev:
        suffixes = ["_%s" % safe_rev]
        if board_rev != safe_rev:
            suffixes.append("@%s" % board_rev)
        candidates.extend(["%s%s.%s" % (b, s, ext) for b in bases for s in suffixes])

    return candidates

def find_nearest_build_file(ctx, start_dir):
    """Finds the nearest directory containing a BUILD or BUILD.bazel file.

    Args:
        ctx: The module or repository context.
        start_dir: The directory to start the search from.

    Returns:
        The path to the nearest directory with a BUILD file, or None if not found.
    """
    current = start_dir

    # Limit search depth to avoid infinite loops
    for _ in range(15):
        if current.get_child("BUILD").exists or current.get_child("BUILD.bazel").exists:
            return current
        parent = current.dirname
        if parent == current:
            break
        current = parent
    return None

def find_module_root(mctx, start_dir, limit_dir = None):
    """Finds the nearest directory containing a MODULE.bazel file.

    Args:
        mctx: The module context.
        start_dir: The directory to start the search from.
        limit_dir: Optional directory to limit the search to (do not traverse above it).

    Returns:
        The path to the nearest directory with a MODULE.bazel file, or None if not found.
    """
    current = start_dir

    # Limit search depth to avoid infinite loops
    for _ in range(15):
        if not current:
            break
        if current.get_child("MODULE.bazel").exists:
            return current
        if limit_dir and current == limit_dir:
            break
        parent = current.dirname
        if not parent or parent == current:
            break
        current = parent
    return None

def get_dir_from_label(mctx, label):
    """Resolves a label to a directory path.

    If the label points to a file, it returns the directory containing that file.
    If the label points to a non-existent path (e.g., a rule target), it returns its parent.

    Args:
        mctx: The module or repository context.
        label: The label to resolve.

    Returns:
        A path object pointing to the directory.
    """
    path = mctx.path(label)
    if not path.exists:
        return path.dirname

    # Use execute to check if it's a file, as Starlark's path object doesn't have is_file()
    if mctx.execute(["test", "-f", str(path)]).return_code == 0:
        return path.dirname
    return path

def get_package_for_path(mctx, path, dir_labels):
    """Resolves the Bazel package for a given absolute path.

    Args:
        mctx: The module context.
        path: The absolute path to resolve.
        dir_labels: A list of directory labels that might contain the path.

    Returns:
        The Bazel package string (e.g., '//arch/arm'), or None.
    """
    path_str = str(path.realpath)

    best_pkg = None
    best_len = -1
    best_dir_len = -1

    for l in dir_labels:
        dir_path = get_dir_from_label(mctx, l)
        dir_path_str = str(dir_path.realpath)

        if path_str.startswith(dir_path_str):
            # Find the nearest BUILD file
            build_dir = find_nearest_build_file(mctx, path)
            if not build_dir:
                continue

            build_dir_str = str(build_dir.realpath)

            # Resolve repo root if external
            repo_root = None
            res_repo = ""
            if l.workspace_name:
                repo_root = get_dir_from_label(mctx, Label("@@" + l.workspace_name + "//:BUILD.bazel"))
                if repo_root:
                    repo_root = repo_root.realpath
                res_repo = str(l).split("//")[0]
            else:
                # Local repo (main workspace)
                repo_root = mctx.path(Label("//:MODULE.bazel")).dirname.realpath

            # The package is relative to the module root
            module_root = find_module_root(mctx, dir_path, limit_dir = repo_root)
            if not module_root:
                module_root = repo_root

            if not module_root:
                continue

            label_workspace_root = str(module_root.realpath)

            if build_dir_str.startswith(label_workspace_root):
                pkg = build_dir_str[len(label_workspace_root):].strip("/")

                build_file = "BUILD.bazel"
                if build_dir.get_child("BUILD").exists:
                    build_file = "BUILD"
                full_pkg = (res_repo + "//" + pkg) if res_repo else ("@@//" + pkg)
                full_pkg = full_pkg + ":" + build_file

                # We want the longest match (most specific package)
                # AND we prefer more specific dir_labels
                is_better = False
                if best_pkg == None:
                    is_better = True
                elif len(dir_path_str) > best_dir_len:
                    is_better = True
                elif len(dir_path_str) == best_dir_len:
                    if len(build_dir_str) > best_len:
                        is_better = True
                    elif len(build_dir_str) == best_len and not res_repo and best_pkg.startswith("@"):
                        is_better = True

                if is_better:
                    best_len = len(build_dir_str)
                    best_dir_len = len(dir_path_str)
                    best_pkg = full_pkg

    return best_pkg

# --- Repository Rules ---

def _create_zephyr_patch_file_impl(rctx):
    """Implementation of create_zephyr_patch_file."""
    script_path = Label("//:generate_diff.py")
    rctx.watch(rctx.path(script_path))

    bazel_overlay_path = rctx.path(Label("//:bazel_overlay"))
    rctx.watch_tree(bazel_overlay_path)
    third_party_zephyr_path = rctx.path(Label("//:third_party/zephyr"))
    rctx.watch_tree(third_party_zephyr_path)
    output_file = rctx.attr.filename
    output_file_path = rctx.path(output_file)

    rctx.file(output_file)
    rctx.file("BUILD")

    args = [
        script_path,
        "--root-dir",
        bazel_overlay_path,
        third_party_zephyr_path,
        "-o",
        output_file_path,
    ]
    if rctx.attr.debug:
        print(args)
    python = get_python(rctx)
    result = python.execute(args)
    if result.return_code != 0:
        fail("Failed to generate zephyr-bazel diff file (%s):\n%s" % (result.return_code, result.stderr))

    if rctx.attr.debug:
        print("Generated %s" % (output_file_path))
    return [
        DefaultInfo(
            files = depset([output_file_path, rctx.path("BUILD")]),
        ),
    ]

create_zephyr_patch_file = repository_rule(
    implementation = _create_zephyr_patch_file_impl,
    attrs = {
        "debug": attr.bool(default = False),
        "filename": attr.string(
            default = "patch.diff",
            mandatory = True,
        ),
    } | COMMON_PY_REPO_RULE_ATTRS,
    local = True,
)

def _version_header_impl(ctx):
    """Implementation of version_header."""
    version_file = ctx.attr.version_file
    version_template = ctx.attr.version_template

    version_content = ctx.read(version_file)
    template_content = ctx.read(version_template)

    # Extract version components using string manipulation
    version_major = 0
    version_minor = 0
    patchlevel = 0
    version_tweak = 0
    for line in version_content.splitlines():
        if line.startswith("VERSION_MAJOR"):
            version_major = int(line.split("=")[1].strip())
        elif line.startswith("VERSION_MINOR"):
            version_minor = int(line.split("=")[1].strip())
        elif line.startswith("PATCHLEVEL"):
            patchlevel = int(line.split("=")[1].strip())
        elif line.startswith("VERSION_TWEAK"):
            version_tweak = int(line.split("=")[1].strip())

    version_type = ctx.attr.VERSION_TYPE
    zephyr_version_code = (version_major << 16) | (version_minor << 8) | patchlevel
    kernelversion = (zephyr_version_code << 8) | version_tweak
    kernelversion_hex = "0x%x" % kernelversion
    kernel_version_number_hex = "0x%x" % zephyr_version_code
    kernel_version_major = version_major
    kernel_version_minor = version_minor
    kernel_patchlevel = patchlevel
    kernel_version_tweak = version_tweak
    kernel_version_string = "{}.{}.{}-{}".format(version_major, version_minor, patchlevel, version_tweak)
    kernel_version_extended_string = kernel_version_string + "+0"
    kernel_version_tweak_string = "{}.{}.{}-0".format(version_major, version_minor, patchlevel)
    build_version_name = "BUILD_VERSION"

    template_dict = {
        "VERSION_TYPE": version_type,
        "ZEPHYR_VERSION_CODE": str(zephyr_version_code),
        "KERNELVERSION": kernelversion_hex,
        "KERNEL_VERSION_NUMBER": kernel_version_number_hex,
        "KERNEL_VERSION_MAJOR": str(kernel_version_major),
        "KERNEL_VERSION_MINOR": str(kernel_version_minor),
        "KERNEL_PATCHLEVEL": str(kernel_patchlevel),
        "KERNEL_VERSION_TWEAK": str(kernel_version_tweak),
        "KERNEL_VERSION_STRING": kernel_version_string,
        "KERNEL_VERSION_EXTENDED_STRING": kernel_version_extended_string,
        "KERNEL_VERSION_TWEAK_STRING": kernel_version_tweak_string,
        "KERNEL_VERSION_CUSTOMIZATION": "",
        "BUILD_VERSION_NAME": build_version_name,
        "BUILD_VERSION": "v" + kernel_version_string,
    }

    template_content = template_content.replace("#cmakedefine", "#define")

    for variable, value in template_dict.items():
        template_content = template_content.replace("@" + variable + "@", value)

    ctx.file("zephyr/version.h", content = template_content, executable = False)
    ctx.file(
        "BUILD.bazel",
        content = """load("@rules_cc//cc:defs.bzl", "cc_library")

cc_library(
  name = "version",
  hdrs = ["zephyr/version.h"],
  includes = ["zephyr", "."],
  visibility = ["//visibility:public"],
)
""",
        executable = False,
    )

    return ctx.repo_metadata(reproducible = True)

version_header = repository_rule(
    implementation = _version_header_impl,
    attrs = {
        "version_file": attr.label(
            mandatory = True,
            allow_single_file = True,
        ),
        "version_template": attr.label(
            mandatory = True,
            allow_single_file = True,
        ),
        "VERSION_TYPE": attr.string(default = "KERNEL"),
    },
)

# --- Module Extensions ---

def _zephyr_patch_file_impl(module_ctx):
    """Implementation of zephyr_patch_file module extension."""
    create_zephyr_patch_file(
        name = "zephyr-patch",
        filename = "patch.diff",
        # This is optional, use it to see what's going on under the hood
        debug = True,
    )

    remote = "https://pigweed.googlesource.com/third_party/github/zephyrproject-rtos/zephyr"
    commit = None
    patches = ["@zephyr-patch//:patch.diff"]

    for mod in module_ctx.modules:
        for tag in mod.tags.checkout:
            if not commit:
                commit = tag.commit
            if tag.remote:
                remote = tag.remote
            for p in tag.patches:
                if p not in patches:
                    patches.append(p)

    if not commit:
        fail("No commit specified for zephyr_patch_file.checkout")

    git_repository(
        name = "zephyr",
        remote = remote,
        commit = commit,
        patches = patches,
        patch_args = ["-p1"],
    )

    version_header(
        name = "zephyr_version",
        version_file = "//:VERSION",
        version_template = "//:version.h.in",
    )

    return module_ctx.extension_metadata(reproducible = True)

_zephyr_checkout = tag_class(
    attrs = {
        "commit": attr.string(
            mandatory = True,
        ),
        "remote": attr.string(),
        "patches": attr.label_list(),
    },
)

zephyr_patch_file = module_extension(
    implementation = _zephyr_patch_file_impl,
    tag_classes = {
        "checkout": _zephyr_checkout,
    },
)

def _zephyr_setup_core_impl(mctx):
    """Implementation of zephyr_setup_core module extension."""
    zephyr_root = mctx.path(Label("//:BUILD.bazel")).dirname
    workspace_root = mctx.path(Label("@@//:MODULE.bazel")).dirname
    python = get_python(
        mctx,
        extra_import_paths = [
            str(zephyr_root.get_child("scripts")),
        ],
        pip_deps = [
            Label("@zephyr_pip_deps//pyyaml"),
            Label("@zephyr_pip_deps//jsonschema"),
            Label("@zephyr_pip_deps//attrs"),
            Label("@zephyr_pip_deps//jsonschema_specifications"),
            Label("@zephyr_pip_deps//referencing"),
            Label("@zephyr_pip_deps//rpds_py"),
            Label("@zephyr_pip_deps//typing_extensions"),
        ],
    )
    apps_dir_labels = []
    boards_dir_labels = []
    modules_labels = []
    manual_boards = []

    for mod in mctx.modules:
        for tag in mod.tags.env:
            if mod.is_root:
                apps_dir_labels.extend(tag.apps_dirs)
            boards_dir_labels.extend(tag.boards_dirs)
            modules_labels.extend(tag.modules)
            manual_boards.extend(tag.manual_boards)

    # Discover Modules
    modules_dirs_map = {}
    for l in modules_labels:
        p = mctx.path(l)
        if p.basename == "module.yml" and p.dirname.basename == "zephyr":
            mod_root = p.dirname.dirname
        else:
            mod_root = p.dirname

        if l.package:
            pkg_dir = mod_root.get_child(l.package)
        else:
            pkg_dir = mod_root

        modules_dirs_map[str(l)] = {
            "root": str(mod_root),
            "package_dir": str(pkg_dir),
        }

    scanner_script = mctx.path(Label("//bazel/tools/metadata:scan_modules.py"))
    scanner_res = python.execute([
        str(scanner_script),
        "--modules-dirs-json",
        json.encode(modules_dirs_map),
    ])
    if scanner_res.return_code != 0:
        fail("scan_modules.py failed: %s" % scanner_res.stderr)
    discovered = json.decode(scanner_res.stdout)

    discovered_modules = {}  # name -> root
    discovered_modules_labels = {}
    discovered_config_only_modules_labels = {}
    watched_kconfigs = []

    # Watch parent directories non-recursively for discovery containers
    for l in modules_labels:
        mctx.watch(get_dir_from_label(mctx, l))

    for item in discovered:
        name = item["name"]
        abs_path_str = item["abs_path"]
        dir_label_str = item["modules_dir_label"]
        relpath = item["relpath"]
        has_zephyr_module_target_in_build = item.get("has_zephyr_module_target_in_build", False)

        derived_label = derive_module_label(dir_label_str, relpath, name)
        discovered_modules[name] = abs_path_str
        module_info = {
            "target": derived_label,
            "original": dir_label_str,
            "relpath": relpath,
        }

        # Determine module linking mode:
        # Modules with a BUILD.bazel file containing a zephyr_module target
        # with a matching module name are Auto-Linked.
        # Otherwise, the module is Scan-Only (Kconfig/DTS only).
        auto_link = has_zephyr_module_target_in_build

        if auto_link:
            discovered_modules_labels[name] = module_info
        else:
            discovered_config_only_modules_labels[name] = module_info

        # Watch metadata
        mctx.watch(mctx.path(abs_path_str).get_child("zephyr").get_child("module.yml"))
        k1 = mctx.path(abs_path_str).get_child("Kconfig")
        mctx.watch(k1)
        watched_kconfigs.append(str(k1))
        k2 = mctx.path(abs_path_str).get_child("zephyr").get_child("Kconfig")
        mctx.watch(k2)
        watched_kconfigs.append(str(k2))

    # Watch for the creation of new module.yml files in subdirectories,
    # so Bazel knows to re-run the module extension if a new module is added.
    for l in modules_labels:
        container = get_dir_from_label(mctx, l)
        if container.exists:
            for subdir in container.readdir():
                mctx.watch(subdir.get_child("zephyr").get_child("module.yml"))

    # Discover Boards
    list_boards_py = zephyr_root.get_child("scripts").get_child("list_boards.py")

    board_roots = [str(zephyr_root)]
    for l in boards_dir_labels:
        b_dir = get_dir_from_label(mctx, l)
        mctx.watch(b_dir)
        mctx.watch(b_dir.get_child("boards"))
        mctx.watch(b_dir.get_child("Kconfig"))
        board_roots.append(str(b_dir))

    cmd = [str(list_boards_py), "--arch-root", str(zephyr_root)]
    cmd.extend(["--soc-root", str(zephyr_root)])
    for m_root in discovered_modules.values():
        cmd.extend(["--soc-root", m_root])
        cmd.extend(["--arch-root", m_root])

    for r in board_roots:
        cmd.extend(["--board-root", r])
    cmd.extend(["--cmakeformat", "{NAME}:{DIR}:{QUALIFIERS}"])

    res = python.execute(cmd)
    if res.return_code != 0:
        fail("list_boards.py failed: %s" % res.stderr)

    board_index = {}
    package_to_boards = {}
    path_str_dict = {}

    for line in res.stdout.splitlines():
        if not line:
            continue
        parts = line.split(":")
        if len(parts) < 2:
            continue

        name = parts[0]
        if name.startswith("NAME;"):
            name = name[5:]

        path_str = parts[1]
        if path_str.startswith("DIR;"):
            path_str = path_str[4:]
        path_str = path_str.split(";")[0]

        qualifiers = []
        if len(parts) >= 3:
            q_part = parts[2]
            if q_part.startswith("QUALIFIERS;"):
                q_part = q_part[11:]
            qualifiers = [q for q in q_part.split(";") if q]

        path = mctx.path(path_str)
        pkg_label = get_package_for_path(mctx, path, boards_dir_labels)
        pkg_path = ""
        if not pkg_label:
            zephyr_root_str = str(mctx.path(zephyr_root).realpath)
            realpath_str = str(path.realpath)
            if realpath_str.startswith(zephyr_root_str):
                zephyr_canonical = str(Label("//:BUILD.bazel")).split("//")[0]
                build_dir = find_nearest_build_file(mctx, path)
                if build_dir:
                    build_dir_str = str(build_dir.realpath)
                    rel_build_pkg = build_dir_str[len(zephyr_root_str):].strip("/")
                    build_file = "BUILD.bazel"
                    if build_dir.get_child("BUILD").exists:
                        build_file = "BUILD"
                    pkg_path = zephyr_canonical + "//" + rel_build_pkg
                    pkg_label = pkg_path + ":" + build_file
                else:
                    rel_path = path_str[len(zephyr_root_str):].strip("/")
                    build_file = "BUILD.bazel"
                    if path.get_child("BUILD").exists:
                        build_file = "BUILD"
                    pkg_path = zephyr_canonical + "//" + rel_path
                    pkg_label = pkg_path + ":" + build_file
            else:
                continue
        else:
            pkg_path = pkg_label.split(":")[0]

        board_index[name] = pkg_label

        if pkg_path not in package_to_boards:
            package_to_boards[pkg_path] = []
        if name not in package_to_boards[pkg_path]:
            package_to_boards[pkg_path].append(name)

        # Also register qualified names (board/soc)
        for q in qualifiers:
            full_board_id = name + "/" + q
            board_index[full_board_id] = pkg_label

            # Add to package_to_boards so it's discoverable
            if full_board_id not in package_to_boards[pkg_path]:
                package_to_boards[pkg_path].append(full_board_id)

        path_str_dict[path_str] = {
            "name": name,
            "qualifiers": qualifiers,
            "pkg_label": pkg_label,
            "pkg_path": pkg_path,
        }

    boards_json_file = "discovered_boards.json"
    board_revisions_file = "board_revisions.json"
    mctx.file(boards_json_file, json.encode(path_str_dict))

    board_meta_script = mctx.path(Label("//bazel/tools/metadata:parse_board_metadata.py"))
    board_meta_res = python.execute([
        str(board_meta_script),
        "--boards-json",
        boards_json_file,
        "--output-json",
        board_revisions_file,
    ])
    if board_meta_res.return_code != 0:
        fail("parse_board_metadata.py failed (%d):\n%s" % (board_meta_res.return_code, board_meta_res.stderr))
    board_revisions_map = json.decode(mctx.read(board_revisions_file))

    for path_str, bdata in path_str_dict.items():
        path = mctx.path(path_str)
        for b_yml_name in ["board.yml", "board.yaml"]:
            b_yml_file = path.get_child(b_yml_name)
            if b_yml_file.exists:
                mctx.watch(b_yml_file)
        rev_dir = path.get_child("revisions")
        if rev_dir.exists:
            mctx.watch(rev_dir)

        name = bdata["name"]
        qualifiers = bdata["qualifiers"]
        pkg_label = bdata["pkg_label"]
        pkg_path = bdata["pkg_path"]

        board_revisions = board_revisions_map.get(path_str, [])

        all_base_ids = [name]
        for q in qualifiers:
            all_base_ids.append(name + "/" + q)

        for rev in board_revisions:
            for base_id in all_base_ids:
                rev_board_id = base_id + "@" + rev
                board_index[rev_board_id] = pkg_label
                if rev_board_id not in package_to_boards[pkg_path]:
                    package_to_boards[pkg_path].append(rev_board_id)

    for mb in manual_boards:
        base, _, _ = mb.partition("@")
        base, _, _ = base.partition("/")
        if base and base in board_index:
            pkg_label = board_index[base]
            pkg_path = pkg_label.split(":", 1)[0]
            board_index[mb] = pkg_label
            if pkg_path in package_to_boards and mb not in package_to_boards[pkg_path]:
                package_to_boards[pkg_path].append(mb)
    # Discover Apps
    discovered_apps = {}
    discovered_apps_labels = {}
    collision_registry = {}  # hash -> label

    for l in apps_dir_labels:
        dir_path = get_dir_from_label(mctx, l)
        dir_path.readdir(watch = "yes")
        res = mctx.execute([
            "find",
            str(dir_path),
            "-name",
            "out",
            "-prune",
            "-o",
            "-name",
            "bazel-*",
            "-prune",
            "-o",
            "-name",
            ".*",
            "-prune",
            "-o",
            "-name",
            "prj.conf",
            "-print",
        ])
        if res.return_code == 0:
            for line in res.stdout.splitlines():
                app_path = mctx.path(line).dirname
                app_pkg = get_package_for_path(mctx, app_path, apps_dir_labels)
                if app_pkg:
                    # Robust normalization: strip repo and redundant target name
                    norm_app = str(app_pkg).split(":")[0]
                    if "//" in norm_app:
                        norm_app = norm_app.split("//")[-1]
                    norm_app = norm_app.strip("/").lstrip(":")

                    # Actually let's use the same logic as naming.bzl for the check
                    h = hash(norm_app)
                    app_hash = ("%x" % (h & 0xFFFFFFFF))
                    app_hash = ("00000000" + app_hash)[-8:]

                    collision_registry[app_hash] = norm_app
                    discovered_apps[norm_app] = str(app_path)
                    discovered_apps_labels[norm_app] = app_pkg
                    mctx.watch(app_path.get_child("prj.conf"))
                    mctx.watch(app_path.get_child("app.overlay"))
                    mctx.watch(app_path.get_child("Kconfig"))
                    mctx.watch(app_path.get_child("sysbuild.yml"))
                    mctx.watch(app_path.get_child("sysbuild.conf"))
                    sysbuild_dir = app_path.get_child("sysbuild")
                    if sysbuild_dir.exists:
                        mctx.watch(sysbuild_dir)
                    else:
                        mctx.watch(app_path)

    apps_json_file = "discovered_apps.json"
    test_metadata_file = "test_metadata.json"
    mctx.file(apps_json_file, json.encode(discovered_apps))

    # Parse metadata YAML
    script_path = mctx.path(Label("//bazel/tools/metadata:parse_test_metadata.py"))
    metadata_res = python.execute([
        str(script_path),
        "--apps-json",
        apps_json_file,
        "--zephyr-root",
        str(zephyr_root),
        "--output-json",
        test_metadata_file,
    ])
    if metadata_res.return_code != 0:
        fail("parse_test_metadata.py failed (%d):\n%s" % (metadata_res.return_code, metadata_res.stderr))
    test_metadata_content = mctx.read(test_metadata_file)
    yaml_metadata = json.decode(test_metadata_content)

    sysbuild_metadata_file = "sysbuild_metadata.json"
    sysbuild_script_path = mctx.path(Label("//bazel/tools/metadata:parse_sysbuild_metadata.py"))
    sysbuild_res = python.execute([
        str(sysbuild_script_path),
        "--apps-json",
        apps_json_file,
        "--output-json",
        sysbuild_metadata_file,
    ])
    if sysbuild_res.return_code != 0:
        fail("parse_sysbuild_metadata.py failed (%d):\n%s" % (sysbuild_res.return_code, sysbuild_res.stderr))
    sysbuild_metadata_content = mctx.read(sysbuild_metadata_file)
    sysbuild_metadata = json.decode(sysbuild_metadata_content)

    # Post-process to make conf_fragments relative to workspace root
    if "custom_repos" in sysbuild_metadata:
        for repo in sysbuild_metadata["custom_repos"]:
            parent_app = repo["parent_app"]
            resolved_conf_fragments = []
            for fragment in repo["conf_fragments"]:
                if not fragment.startswith("/"):
                    resolved_conf_fragments.append(parent_app + "/" + fragment)
                else:
                    resolved_conf_fragments.append(fragment)
            repo["conf_fragments"] = resolved_conf_fragments

    surviving_combinations = {}
    for app_pkg, app_path in discovered_apps.items():
        surviving_combinations[app_pkg] = []
        yaml_res = yaml_metadata.get(app_pkg, None)
        is_oot_app = not app_path.startswith(str(zephyr_root))

        for board_id, board_path in board_index.items():
            is_oot_board = not board_path.startswith(str(zephyr_root))

            # OOT Exemption
            if is_oot_app and is_oot_board:
                surviving_combinations[app_pkg].append(board_id)
                continue

            # Manual fallback
            found_manual = False
            has_rev = "@" in board_id
            for mb in manual_boards:
                mb_has_rev = "@" in mb
                if has_rev != mb_has_rev:
                    continue
                if has_rev:
                    if board_id == mb:
                        found_manual = True
                        break
                else:
                    if board_id == mb or board_id.split("/")[0] == mb:
                        found_manual = True
                        break

            if found_manual:
                surviving_combinations[app_pkg].append(board_id)
                continue

            # YAML
            if yaml_res != None and len(yaml_res) > 0:
                if board_id in yaml_res:
                    surviving_combinations[app_pkg].append(board_id)
                continue

            # Filesystem
            boards_dir = mctx.path(app_path).get_child("boards")
            if boards_dir.exists:
                # Watch the boards dir so we re-filter if a new file is added.
                mctx.watch(boards_dir)
                board_name, qualifiers, board_rev = _parse_board_id(board_id)
                override_candidates = (
                    _get_override_candidates(board_name, qualifiers, board_rev, "conf") +
                    _get_override_candidates(board_name, qualifiers, board_rev, "overlay")
                )

                found = False
                for c in override_candidates:
                    c_file = boards_dir.get_child(c)
                    if c_file.exists:
                        mctx.watch(c_file)
                        found = True
                        break
                if found:
                    surviving_combinations[app_pkg].append(board_id)
                    continue
                elif yaml_res == None:
                    clean_b = board_id.split("/")[0].split("@")[0]
                    if clean_b in ["native_sim", "native_sim_64", "qemu_cortex_m3", "qemu_x86", "qemu_riscv32"]:
                        surviving_combinations[app_pkg].append(board_id)
                    continue
            else:
                # If the boards dir does not exist we must watch the app dir to catch if a boards dir is added.
                mctx.watch(app_path)
                if yaml_res == None:
                    clean_b = board_id.split("/")[0].split("@")[0]
                    if clean_b in ["native_sim", "native_sim_64", "qemu_cortex_m3", "qemu_x86", "qemu_riscv32"]:
                        surviving_combinations[app_pkg].append(board_id)
                    continue

    # Generate Repositories
    state_data = {
        "zephyr_root": "//:BUILD.bazel",
        "board_index": board_index,
        "apps": discovered_apps_labels,
        "modules": discovered_modules_labels,
        "config_only_modules": discovered_config_only_modules_labels,
        "oot_dts_roots": [str(l) for l in boards_dir_labels],
        "package_to_boards": package_to_boards,
        "manual_boards": manual_boards,
        "surviving_combinations": surviving_combinations,
        "sysbuild_metadata": sysbuild_metadata,
        "translated_conf": sysbuild_metadata.get("translated_confs", {}),
    }
    zephyr_state_repo(
        name = "zephyr_state",
        content = json.encode(state_data),
    )
    print("DEBUG _zephyr_setup_core_impl: zephyr_state workspace_name =", Label("@zephyr_state//:state.json").workspace_name)
    print("DEBUG _zephyr_setup_core_impl: BUILD.bazel workspace_name =", Label("//:BUILD.bazel").workspace_name)
    print("DEBUG _zephyr_setup_core_impl: BUILD.bazel str =", str(Label("//:BUILD.bazel")))
    print("DEBUG _zephyr_setup_core_impl: zephyr_state str =", str(Label("@zephyr_state//:state.json")))

    version_header(
        name = "zephyr_version",
        version_file = "//:VERSION",
        version_template = "//:version.h.in",
    )

    # Resolve canonical name prefix for this extension's repos
    repo_prefix = str(Label("//:BUILD.bazel")).split("//")[0] + "+zephyr_setup_apps+"

    board_id_to_safe = {b: sanitize_board_id(b) for b in board_index.keys()}
    repo_name_to_canonical = {}
    for app_pkg, boards in surviving_combinations.items():
        app_hash = get_app_hash(app_pkg)
        for board_id in boards:
            repo_name = get_zc_repo_name_from_precomputed(app_hash, board_id_to_safe[board_id])
            repo_name_to_canonical[repo_name] = repo_prefix + repo_name

    custom_repos = sysbuild_metadata.get("custom_repos", [])
    for repo in custom_repos:
        repo_name_to_canonical[repo["name"]] = repo_prefix + repo["name"]

    index_content = "PACKAGE_TO_BOARDS = %r\n" % package_to_boards
    index_content += "REPO_NAME_TO_CANONICAL = %r\n" % repo_name_to_canonical
    index_content += "SYSBUILD_METADATA = %r\n" % sysbuild_metadata
    sysbuild_custom_repos = {}
    for repo in custom_repos:
        key = "%s:%s:%s" % (repo["parent_app"], repo["helper_name"], repo["board_id"])
        sysbuild_custom_repos[key] = repo["name"]
        for fragment in repo["conf_fragments"]:
            if not fragment.startswith("/"):
                fragment_path = mctx.path(str(workspace_root) + "/" + fragment)
            else:
                fragment_path = mctx.path(fragment)
            mctx.watch(fragment_path)

    index_content += "SYSBUILD_CUSTOM_REPOS = %r\n" % sysbuild_custom_repos

    zephyr_index_repo(
        name = "zephyr_index",
        content = index_content,
    )

    zephyr_kconfig_schema(
        name = "zephyr_kconfig",
        state_file = "@zephyr_state//:state.json",
        kconfigs = watched_kconfigs,
    )

    return mctx.extension_metadata(reproducible = True)

def _get_parent_platform(pkg, board_id):
    clean_board_id, _, _ = board_id.partition("@")
    board_family, slash, variant = clean_board_id.partition("/")
    target_name = variant.replace("/", "_") if slash else clean_board_id
    return pkg + ":" + target_name

def _zephyr_setup_apps_impl(mctx):
    """Implementation of zephyr_setup_apps module extension."""
    state_file = mctx.path(Label("@zephyr_state//:state.json"))
    print("DEBUG _zephyr_setup_apps_impl: state_file.exists =", state_file.exists, "path =", state_file)
    if not state_file.exists:
        return mctx.extension_metadata(reproducible = True)
    state = json.decode(mctx.read(state_file))

    discovered_apps = state["apps"]
    board_index = state["board_index"]
    package_to_boards = state["package_to_boards"]

    # Reverse mapping for internal use to find the platform for a board
    board_to_package = {}
    for pkg, boards in package_to_boards.items():
        for b in boards:
            if b not in board_to_package:
                board_to_package[b] = pkg

    # Resolve canonical name prefix for this extension's repos
    repo_prefix = str(Label("//:BUILD.bazel")).split("//")[0] + "+zephyr_setup_apps+"

    # Declare ALL combinations
    all_repo_names = []
    repo_name_to_canonical = {}
    board_id_to_safe = {b: sanitize_board_id(b) for b in board_index.keys()}
    surviving_combinations = state["surviving_combinations"]
    for app_pkg, boards in surviving_combinations.items():
        app_hash = get_app_hash(app_pkg)
        for board_id in boards:
            repo_name = get_zc_repo_name_from_precomputed(app_hash, board_id_to_safe[board_id])
            pkg = board_to_package.get(board_id)
            if not pkg:
                print("DEBUG: board_id not in board_to_package:", board_id)
                continue

            parent_platform = _get_parent_platform(pkg, board_id)
            print("DEBUG: generating repo_name:", repo_name, "for app_pkg:", app_pkg, "board_id:", board_id, "parent_platform:", parent_platform)

            app_fragments = state.get("translated_conf", {}).get(app_pkg, {})
            main_fragment = app_fragments.get("main", "")

            gen_zephyr_config(
                name = repo_name,
                app_label = "//" + app_pkg if not app_pkg.startswith("//") else app_pkg,
                board_id = board_id,
                parent_platform = parent_platform,
                state_file = "@zephyr_state//:state.json",
                extra_kconfig = main_fragment,
            )
            all_repo_names.append(repo_name)
            repo_name_to_canonical[repo_name] = repo_prefix + repo_name

    custom_repos = state.get("sysbuild_metadata", {}).get("custom_repos", [])
    for repo in custom_repos:
        board_id = repo["board_id"]
        pkg = board_to_package.get(board_id)
        if not pkg:
            continue

        parent_platform = _get_parent_platform(pkg, board_id)

        gen_zephyr_config(
            name = repo["name"],
            app_label = repo["app_label"],
            board_id = board_id,
            parent_platform = parent_platform,
            state_file = "@zephyr_state//:state.json",
            conf_fragments = repo["conf_fragments"],
            extra_kconfig = repo.get("extra_kconfig", ""),
        )
        all_repo_names.append(repo["name"])
        repo_name_to_canonical[repo["name"]] = repo_prefix + repo["name"]

    return mctx.extension_metadata(reproducible = True)

_env = tag_class(
    attrs = {
        "apps_dirs": attr.label_list(),
        "boards_dirs": attr.label_list(),
        "modules": attr.label_list(),
        "manual_boards": attr.string_list(),
    },
)

zephyr_setup = module_extension(
    implementation = _zephyr_setup_core_impl,
    tag_classes = {
        "env": _env,
    },
)

zephyr_setup_apps = module_extension(
    implementation = _zephyr_setup_apps_impl,
)

###############################################################################

def _print_file_impl(ctx):
    """Implementation of print_file."""

    # Get the input file
    input_file = ctx.file.file

    # Create an empty output file
    output_file = ctx.actions.declare_file(ctx.label.name + ".out")

    # Create a shell action to print the file
    ctx.actions.run_shell(
        outputs = [output_file],
        inputs = [input_file],
        command = "cat {} > {}".format(input_file.path, output_file.path),
    )

    # Return DefaultInfo to signal dependencies on the input file
    return DefaultInfo(files = depset([output_file]))

# Define the rule
print_file = rule(
    implementation = _print_file_impl,
    attrs = {
        "file": attr.label(allow_single_file = True, mandatory = True),
    },
)
