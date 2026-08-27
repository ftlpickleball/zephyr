# Forwarding alias for backwards compatibility
load(
    "//bazel:cc.bzl",
    _if_compiler_is_clang = "if_compiler_is_clang",
    _if_compiler_is_gcc = "if_compiler_is_gcc",
    _zephyr_app = "zephyr_app",
    _zephyr_cc_binary = "zephyr_cc_binary",
    _zephyr_cc_library = "zephyr_cc_library",
    _zephyr_freestanding_library = "zephyr_freestanding_library",
    _zephyr_module = "zephyr_module",
    _zephyr_soc_library = "zephyr_soc_library",
)

if_compiler_is_clang = _if_compiler_is_clang
if_compiler_is_gcc = _if_compiler_is_gcc
zephyr_app = _zephyr_app
zephyr_cc_binary = _zephyr_cc_binary
zephyr_cc_library = _zephyr_cc_library
zephyr_freestanding_library = _zephyr_freestanding_library
zephyr_module = _zephyr_module
zephyr_soc_library = _zephyr_soc_library
