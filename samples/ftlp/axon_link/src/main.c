/*
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "axon/nrf_axon_platform.h"

int main(void)
{
	nrf_axon_result_e res = nrf_axon_platform_init();

	printk("axon init: %d, clk %u Hz\n", (int)res, nrf_axon_platform_get_clk_hz());
	return 0;
}
