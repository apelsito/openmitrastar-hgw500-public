#ifndef F338_ORACLE_CONTRACT_H
#define F338_ORACLE_CONTRACT_H
#include "f338_uapi.h"
struct f338_probe {uint32_t total,current_count,poll,candidate,flushes,resets,callback,cfg_hash,stats_hash,history_hash,rate_hash;};
uint32_t f338_hash(const void*,unsigned);
int f338_reference_step(const struct f338_job*,struct f338_probe*);
void f338_reference_end(void);
#endif
