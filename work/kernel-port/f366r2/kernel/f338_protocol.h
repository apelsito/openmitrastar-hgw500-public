// SPDX-License-Identifier: GPL-2.0-only
#ifndef F338_PROTOCOL_H
#define F338_PROTOCOL_H
#include "f338_uapi.h"
enum f338_state {F338_OFF,F338_IDLE,F338_QUEUED,F338_DELIVERED,F338_REPLY,F338_ABORTED};
enum f338_result {F338_PROTO_OK=0,F338_PROTO_STALE=-1,F338_PROTO_BUSY=-2,F338_PROTO_INVALID=-3,F338_PROTO_TIMEOUT=-4,F338_PROTO_EXHAUSTED=-5,F338_PROTO_REPLAY=1};
struct f338_protocol {
 f338_u32 session,sequence,generation,deadline_ms,reset_count;
 enum f338_state state;
 struct f338_reset resets[F338_RESET_MAX];
 f338_u32 reset_pending;
};
/* One caller lock protects this core. It contains no pointers, IO, waits or
 * user memory access; kernel wrappers own copying and all synchronization. */
int f338_protocol_attach(struct f338_protocol*);
void f338_protocol_detach(struct f338_protocol*,f338_u32 session);
int f338_protocol_queue(struct f338_protocol*,struct f338_job*,f338_u32 now_ms);
int f338_protocol_delivered(struct f338_protocol*,const struct f338_header*,f338_u32 now_ms);
int f338_protocol_reply(struct f338_protocol*,const struct f338_reply*,f338_u32 now_ms);
int f338_protocol_reset_begin(struct f338_protocol*,const struct f338_reset*,struct f338_reset *cached,f338_u32 now_ms);
int f338_protocol_reset_end(struct f338_protocol*,const struct f338_reset*,f338_u32 now_ms);
int f338_protocol_check_timeout(struct f338_protocol*,f338_u32 now_ms);
void f338_protocol_abort(struct f338_protocol*);
void f338_protocol_cancel(struct f338_protocol*); /* Legitimate new generation. */
int f338_validate_job(const struct f338_job*);
#endif
