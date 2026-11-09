// SPDX-License-Identifier: GPL-2.0-only
#ifndef F332_EVENTS_H
#define F332_EVENTS_H
#include "f316_portable.h"
/* F327 generation/draining semantics without its old F316 classifier. All
 * methods use one caller lock. No lock is held during callback(void). */
enum {F332_OFF,F332_ACTIVE,F332_DRAINING,F332_MUTATING,F332_FAULT};
struct f332_token {uint64_t epoch,serial;uint32_t channel,bandwidth;};
struct f332_events {
 uint64_t epoch,serial,delivered_epoch;
 uint32_t channel,bandwidth;
 unsigned phase;
 bool capture,callback,event,authority,dfs,ready;
 struct f332_token capture_token,event_token;
};
int f332_events_transition(struct f332_events*,uint64_t*);
int f332_events_commit(struct f332_events*,uint64_t,uint32_t,uint32_t,bool ready,bool dfs,bool authority);
int f332_events_capture(struct f332_events*,struct f332_token*);
int f332_events_complete(struct f332_events*,const struct f332_token*,bool eligible,struct f332_token*);
int f332_events_dispatch(struct f332_events*,const struct f332_token*);
int f332_events_return(struct f332_events*,const struct f332_token*);
#endif
