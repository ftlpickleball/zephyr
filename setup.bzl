# Forwarding alias for backwards compatibility
load(
    "//bazel:setup.bzl",
    _zephyr_setup = "zephyr_setup",
    _zephyr_setup_apps = "zephyr_setup_apps",
)

zephyr_setup = _zephyr_setup
zephyr_setup_apps = _zephyr_setup_apps
