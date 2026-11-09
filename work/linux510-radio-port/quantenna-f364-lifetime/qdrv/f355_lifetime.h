/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F355_LIFETIME_H
#define F355_LIFETIME_H
#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stdbool.h>
#endif
/* Caller serializes transitions. A retained reference has no release path:
 * F353 did not establish a safe hardware retirement contract. */
struct f355_lifetime {
 bool ready, closing, retained, core_attempted, boot_failed;
 unsigned rejected_unloads;
};
enum f355_result { F355_OK=0, F355_NOT_READY=-11, F355_BUSY=-16,
                  F355_BOOT_FAILED=-5, F355_ALREADY_ATTEMPTED=-114 };
static inline int f355_claim(struct f355_lifetime *s,
                            bool (*get_reference)(void *), void *context)
{
 if(!s->ready||s->closing)return F355_NOT_READY;
 if(s->boot_failed)return F355_BOOT_FAILED;
 if(!s->retained){
  if(!get_reference(context))return F355_BUSY;
  s->retained=true;
 }
 return F355_OK;
}
static inline int f355_core_begin(struct f355_lifetime *s)
{
 if(!s->ready||s->closing||!s->retained)return F355_NOT_READY;
 if(s->boot_failed)return F355_BOOT_FAILED;
 if(s->core_attempted)return F355_ALREADY_ATTEMPTED;
 s->core_attempted=true;
 return F355_OK;
}
static inline void f355_boot_failure(struct f355_lifetime *s)
{
 if(s->retained)s->boot_failed=true;
}
static inline int f355_exit_begin(struct f355_lifetime *s)
{
 if(s->retained){s->rejected_unloads++;return F355_BUSY;}
 s->closing=true;s->ready=false;return F355_OK;
}
#endif
