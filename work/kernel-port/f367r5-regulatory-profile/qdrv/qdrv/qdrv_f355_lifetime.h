/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef QDRV_F355_LIFETIME_H
#define QDRV_F355_LIFETIME_H
#include <linux/types.h>
int qdrv_f355_claim(const char *operation);
int qdrv_f355_core_begin(void);
void qdrv_f355_boot_failure(void);
bool qdrv_f355_retained(void);
bool qdrv_f355_ready(void);
bool qdrv_f355_failed(void);
void qdrv_f355_ready_commit(void);
int qdrv_f355_exit_begin(void);
int qdrv_f355_status(char *buf);
#endif
