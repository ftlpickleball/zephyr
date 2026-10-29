# SPDX-License-Identifier: Apache-2.0

"""Fetches the arm-zephyr-eabi SDK tarball matching the build host's OS + arch."""

# (os, arch) -> (url, sha256)
_ARM_SDKS = {
    ("linux", "amd64"): (
        "https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v1.0.1/toolchain_gnu_linux-x86_64_arm-zephyr-eabi.tar.xz",
        "21b85981cb5a1818d9bc53d82af80f208946ec038b982ff1907287572ed3a634",
    ),
    ("linux", "aarch64"): (
        "https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v1.0.1/toolchain_gnu_linux-aarch64_arm-zephyr-eabi.tar.xz",
        "b9805b691f2f0a8926c92694cae378d05ba07b76abca745e216fcc52753cc4d6",
    ),
    ("macos", "aarch64"): (
        "https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v1.0.1/toolchain_gnu_macos-aarch64_arm-zephyr-eabi.tar.xz",
        "4008edb5d4840cd994aedd7f1309bfb63e7243729d57839ebf1cc83c1f17c886",
    ),
}

def _host_key(rctx):
    name = rctx.os.name.lower()
    arch = rctx.os.arch.lower()
    if name.startswith("mac") or name.startswith("darwin"):
        os = "macos"
    elif name.startswith("linux"):
        os = "linux"
    else:
        os = name
    if arch in ("x86_64", "amd64", "x64"):
        cpu = "amd64"
    elif arch in ("aarch64", "arm64"):
        cpu = "aarch64"
    else:
        cpu = arch
    return (os, cpu)

def _host_arm_sdk_impl(rctx):
    key = _host_key(rctx)
    entry = _ARM_SDKS.get(key)
    if entry == None:
        fail("No arm-zephyr-eabi SDK for host %s; supported: %s" % (key, _ARM_SDKS.keys()))
    url, sha256 = entry
    rctx.download_and_extract(url = url, sha256 = sha256, stripPrefix = "arm-zephyr-eabi")
    rctx.symlink(rctx.attr.build_file, "BUILD.bazel")

host_arm_sdk = repository_rule(
    implementation = _host_arm_sdk_impl,
    attrs = {
        "build_file": attr.label(mandatory = True),
    },
)
