# Forwarding alias for backwards compatibility
load(
    "//bazel:runner.bzl",
    _zephyr_runner_config = "zephyr_runner_config",
    _zephyr_runners_yaml = "zephyr_runners_yaml",
)

zephyr_runner_config = _zephyr_runner_config
zephyr_runners_yaml = _zephyr_runners_yaml
