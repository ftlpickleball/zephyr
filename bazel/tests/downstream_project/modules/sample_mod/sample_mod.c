#include "sample_mod.h"
#include <zephyr/autoconf.h>

int sample_mod_get(void) {
    return CONFIG_SAMPLE_MOD_VALUE;
}
