# SPDX-FileCopyrightText: Copyright 2026 The Pigweed Authors
# SPDX-License-Identifier: Apache-2.0

def zephyr():
    """Returns target_compatible_with constraints required by Zephyr targets.

    This constraint guarantees that targets requiring Zephyr (such as
    zephyr_cc_library and //include:zephyr) are only built on target
    platforms using a Zephyr-compatible C++ toolchain. Specifically, Zephyr
    targets rely on the toolchain to inject the `-include zephyr/autoconf.h`
    compiler option and stage the autoconf header in the action sandbox across
    all translation units.
    """
    return [Label("//constraints:zephyr_autoconf_force_included")]
