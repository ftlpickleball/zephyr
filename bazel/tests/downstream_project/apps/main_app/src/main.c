#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include "sample_mod.h"

int main(void) {
#if DT_NODE_EXISTS(DT_NODELABEL(sample_dev))
    return sample_mod_get() + DT_PROP(DT_NODELABEL(sample_dev), sample_prop);
#else
    return sample_mod_get();
#endif
}
