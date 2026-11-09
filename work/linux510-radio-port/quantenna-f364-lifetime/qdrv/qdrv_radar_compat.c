// SPDX-License-Identifier: GPL-2.0
/* Fail-closed replacement for the proprietary 2.6.35 radar.ko ABI. */

#include <linux/errno.h>
#include <linux/printk.h>

#include <radar/detect.h>
#include <radar/radar.h>

static struct detect_drv_sample_t qdrv_radar_sample = {
	.lock = __SPIN_LOCK_UNLOCKED(qdrv_radar_sample.lock),
};

static struct radar_ocac_info_s qdrv_radar_ocac = {
	.lock = __SPIN_LOCK_UNLOCKED(qdrv_radar_ocac.lock),
};

int radar_register(void (*dfs_mark_callback)(void))
{
	return -EOPNOTSUPP;
}

int radar_register_is_dfs_chan(bool (*is_dfs_chan)(uint8_t wifi_chan))
{
	return -EOPNOTSUPP;
}

int radar_register_is_dfs_weather_chan(
		bool (*is_weather_chan)(uint8_t wifi_chan))
{
	return -EOPNOTSUPP;
}

void radar_disable(void)
{
}

void radar_enable(void)
{
}

bool radar_start(const char *region)
{
	pr_warn_once("qdrv: DFS disabled: proprietary radar backend is unavailable\n");
	return false;
}

void radar_stop(void)
{
}

int radar_register_statcb(void (*stats_send)(void *data,
		int (*pulse_copy_iter)(void *dest, void *src, int pulse_index),
		void *pulse_buf, int num_pulses), void *stats_send_arg)
{
	return -EOPNOTSUPP;
}

unsigned dfs_rqmt_code(const char *region)
{
	return DFS_RQMT_UNKNOWN;
}

void radar_set_shared_params(struct shared_params *params)
{
}

int radar_set_chan(uint8_t channel)
{
	return -EOPNOTSUPP;
}

uint8_t radar_get_chan(void)
{
	return 0;
}

bool sta_dfs_is_region_required(void)
{
	return false;
}

struct radar_ocac_info_s *radar_ocac_info_addr_get(void)
{
	return &qdrv_radar_ocac;
}

void radar_record_buffer_pt(uint32_t *point)
{
	if (point)
		*point = 0;
}

bool radar_get_status(void)
{
	return false;
}

void radar_set_bw(uint32_t bandwidth)
{
}

struct detect_drv_sample_t *detect_drv_sample_loc_get(void)
{
	return &qdrv_radar_sample;
}
