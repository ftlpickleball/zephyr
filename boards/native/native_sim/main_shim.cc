// SPDX-FileCopyrightText: Copyright 2024 The Pigweed Authors
// SPDX-License-Identifier: Apache-2.0

// A shim to bridge Zephyr's native_sim "zephyr_app_main()" call to a C++
// user app's "main()""

// When building for native_sim, "main" is #defined to be "zephyr_app_main"
// when compiling the app code, as otherwise there is a conflict with the
// main() provided by the native sim framework.

// This is declared as a weak reference so that if a C++ app is built, it
// will provide a strong version of the symbol given the #define of "main".
// Note that the symbol used will have the traditional C++ name mangling.

__attribute__((weak)) int zephyr_app_main(void) {
    return -1;
}

// This is the C version of the zephyr_app_main() interface. This name is
// unmangled, but we need to give it a distinct name to the C++ compiler to
// avoid confusion with the unmangled C++ function name, so the C++
// function can be called.
//
// Again if the app defines its own 'extern "C" main', it will be used instead
// of this weak reference.

extern "C" {
    __attribute__((weak)) int zephyr_app_main_c_link(void) __asm__("zephyr_app_main");
}

extern "C" __attribute__((weak)) int zephyr_app_main_c_link(void) {
    return zephyr_app_main();
}
