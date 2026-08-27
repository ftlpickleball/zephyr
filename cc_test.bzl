# Forwarding alias for backwards compatibility
load(
    "//bazel:cc_test.bzl",
    _zephyr_cc_test = "zephyr_cc_test",
    _ztest = "ztest",
)

zephyr_cc_test = _zephyr_cc_test
ztest = _ztest
