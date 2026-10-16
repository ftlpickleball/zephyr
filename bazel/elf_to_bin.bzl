# Copyright 2026 The Pigweed Authors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""Rule to convert ELF to BIN (raw binary) using the toolchain's objcopy."""

load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load("@bazel_tools//tools/cpp:toolchain_utils.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")

def _elf_to_bin_impl(ctx):
    elf = ctx.file.src
    out_name = ctx.label.name if ctx.label.name.endswith(".bin") else ctx.label.name + ".bin"
    bin_file = ctx.actions.declare_file(out_name)

    cc_toolchain = find_cpp_toolchain(ctx)
    feature_configuration = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    objcopy_executable = cc_common.get_tool_for_action(
        feature_configuration = feature_configuration,
        action_name = ACTION_NAMES.objcopy_embed_data,
    )

    ctx.actions.run(
        outputs = [bin_file],
        inputs = depset(direct = [elf], transitive = [cc_toolchain.all_files]),
        executable = objcopy_executable,
        arguments = ["-O", "binary", elf.path, bin_file.path],
        mnemonic = "ElfToBin",
        progress_message = "Converting %s to BIN" % elf.short_path,
    )

    return [DefaultInfo(files = depset([bin_file]))]

elf_to_bin = rule(
    implementation = _elf_to_bin_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "The ELF input file",
        ),
        "_cc_toolchain": attr.label(
            default = Label("@bazel_tools//tools/cpp:current_cc_toolchain"),
        ),
    },
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
    fragments = ["cpp"],
)
