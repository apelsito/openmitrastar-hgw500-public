/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef QDRV_F367R9_TRACE_H
#define QDRV_F367R9_TRACE_H
#include <linux/types.h>
#define F367R9_NO_RESULT (-4096)
void qdrv_f367r9_hostlink_trace_arm(unsigned int channel);
bool qdrv_f367r9_hostlink_trace_active(void);
void qdrv_f367r9_boundary(const char *stage,int result);
#endif
