# ftlpickleball/zephyr mirror

Mirror of Pigweed's in-tree Bazel Zephyr fork, plus FTLP build fixes.

| Branch | Content |
| --- | --- |
| `upstream/v4.4-branch` | Pure mirror of `pigweed.googlesource.com/third_party/github/zephyrproject-rtos/zephyr` `v4.4-branch`. Force-updated. |
| `ftlp/v4.4` (default) | Upstream merged with FTLP fix commits. `ftlp-source` `xiao/MODULE.bazel` pins SHAs here. |

- `.github/workflows/ftlp-sync-upstream.yml` merges upstream daily; never rebases.
- Every inherited upstream Zephyr workflow is disabled by that sync.
