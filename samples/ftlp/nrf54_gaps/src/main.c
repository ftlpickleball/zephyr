/*
 * SPDX-License-Identifier: Apache-2.0
 */

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/comparator.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

#include "lsm6dsk320x_reg.h"

LOG_MODULE_REGISTER(nrf54_gaps, LOG_LEVEL_INF);

int main(void)
{
	const struct device *const devs[] = {
		DEVICE_DT_GET(DT_NODELABEL(comp)),
		DEVICE_DT_GET(DT_NODELABEL(npm1304_charger)),
		DEVICE_DT_GET(DT_NODELABEL(lps22df)),
		DEVICE_DT_GET(DT_NODELABEL(lps22hb)),
	};
	int ready = 0;

	for (size_t i = 0; i < ARRAY_SIZE(devs); i++) {
		ready += device_is_ready(devs[i]) ? 1 : 0;
	}
	/* Keeps the PID linked through the //modules/st_pid alias. */
	LOG_INF("%d/%u ready, pid %p", ready, (unsigned int)ARRAY_SIZE(devs),
		(void *)lsm6dsk320x_device_id_get);

	return ready == ARRAY_SIZE(devs) ? 0 : -ENODEV;
}
