/*
 * SPDX-License-Identifier: Apache-2.0
 */

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

int main(void)
{
	const struct device *dev = DEVICE_DT_GET_ONE(st_lsm6dsk320x);

	return device_is_ready(dev) ? 0 : -ENODEV;
}
