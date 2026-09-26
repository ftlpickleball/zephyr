#!/bin/bash
set -euo pipefail

if ! command -v bazelisk &> /dev/null; then
  echo "bazelisk not found in PATH; downloading a temporary copy via cipd." >&2
  echo "Install bazelisk locally so it does not have to be downloaded on every run." >&2
  BAZELISK_DIR="$(mktemp -d)"
  trap 'rm -rf "${BAZELISK_DIR}"' EXIT
  cipd install 'fuchsia/third_party/bazelisk/${platform}' latest -root "${BAZELISK_DIR}"
  export PATH="${BAZELISK_DIR}:${PATH}"
fi

bazelisk build //samples/hello_world --platforms=@zephyr//boards/qemu/cortex_m3:qemu_cortex_m3
