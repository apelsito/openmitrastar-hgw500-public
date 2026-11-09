/* Userspace adapter for the separately retained proprietary OEM objects. */
#ifndef F338_SERVICE_CORE_H
#define F338_SERVICE_CORE_H
#include "f338_uapi.h"
typedef int (*f338_reset_rpc)(void*,struct f338_reset*);
enum {F338_ENGINE_OK=0,F338_ENGINE_CANCELED=1,F338_ENGINE_FAILED=-1};
int f338_engine_job(const struct f338_job*,struct f338_reply*,f338_reset_rpc,void*);
void f338_engine_cancel(void);
void f338_engine_close(void);
#endif
