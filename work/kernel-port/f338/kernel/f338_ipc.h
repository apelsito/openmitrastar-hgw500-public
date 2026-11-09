// SPDX-License-Identifier: GPL-2.0-only
#ifndef F338_IPC_H
#define F338_IPC_H
#include "f338_protocol.h"
enum f338_loss_reason {F338_SERVICE_CLOSED=1,F338_SERVICE_TIMEOUT=2,F338_SERVICE_PROTOCOL=3,F338_HARDWARE_FAULT=4,F338_SERVICE_READY=5};
int f338_ipc_init(void (*lost)(unsigned reason));
void f338_ipc_exit(void);
int f338_ipc_available(void);
void f338_ipc_wake(void);
void f338_ipc_cancel(void);
/* Only the provider worker calls exchange and owns PM for its entire scope.
 * It must release state_lock and BB before calling this blocking function.
 * Reset requests are executed HERE by that same worker, never in ioctl. */
int f338_ipc_exchange(struct f338_job*,struct f338_reply*,
 int (*current_generation)(unsigned),
 int (*reset)(void*,unsigned,unsigned,int*,int*));
#endif
