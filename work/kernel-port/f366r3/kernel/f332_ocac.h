// SPDX-License-Identifier: GPL-2.0-only
#ifndef F332_OCAC_H
#define F332_OCAC_H
#include "f316_portable.h"
struct f332_ocac_point {uint8_t status;uint32_t fifo_pointer;};
struct f332_ocac_state {
 uint8_t previous_status;
 uint32_t previous_pointer;
 uint8_t mask[256];
 bool filter,weather;
 uint8_t oem_iteration_marker;
};
/* Exact worker3c32..3dde. last_current is a real BB-protected snapshot when
 * an open OFF_CHANNEL interval must be completed; never substitute a zero. */
int f332_ocac_prepare(struct f332_ocac_state*,const struct f332_ocac_point*,unsigned count,
 bool home_is_dfs,bool scan_is_weather,bool current_valid,uint32_t last_current);
void f332_ocac_consume(struct f332_ocac_state*);
#endif
