#!/bin/bash
set -euo pipefail

if ! command -v bazelisk &> /dev/null; then
  echo "bazelisk not found in PATH; downloading a temporary copy via cipd." >&2
  echo "Install bazelisk locally so it does not have to be downloaded on every run." >&2
  BAZELISK_DIR="$(mktemp -d)"
  trap 'rm -rf "${BAZELISK_DIR}"' EXIT
  cipd ensure -ensure-file - -root "${BAZELISK_DIR}" <<< 'fuchsia/third_party/bazelisk/${platform} latest'
  export PATH="${BAZELISK_DIR}:${PATH}"
fi

bazelisk test //bazel/tools/... //bazel/private/...
bazelisk build //samples/hello_world --platforms=@zephyr//boards/qemu/cortex_m3:qemu_cortex_m3
bazelisk build //samples/hello_world --platforms=@zephyr//boards/native/native_sim:native
