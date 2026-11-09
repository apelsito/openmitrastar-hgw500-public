/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/module.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include "f355_lifetime.h"
#include "qdrv_f355_lifetime.h"

/* The module reference, not a return from module_exit, prevents removal.
 * Forced removal bypasses that contract and is not supported by this build. */
#ifdef CONFIG_MODULE_FORCE_UNLOAD
#error F355 requires CONFIG_MODULE_FORCE_UNLOAD disabled
#endif
static DEFINE_SPINLOCK(f355_lock);
static struct f355_lifetime f355_state;
static char f355_first_operation[24];

static bool f355_get_reference(void *unused)
{
 return try_module_get(THIS_MODULE);
}
int qdrv_f355_claim(const char *operation)
{
 unsigned long flags;bool first;int rc;
 spin_lock_irqsave(&f355_lock,flags);
 first=!f355_state.retained;
 rc=f355_claim(&f355_state,f355_get_reference,NULL);
 if(!rc&&first)strlcpy(f355_first_operation,operation,sizeof(f355_first_operation));
 spin_unlock_irqrestore(&f355_lock,flags);
 if(!rc&&first)pr_info("OMF355_LIFETIME retained=1 operation=%s release=reboot-only\n",f355_first_operation);
 return rc;
}
int qdrv_f355_core_begin(void)
{
 unsigned long flags;int rc=qdrv_f355_claim("core-start");
 if(rc)return rc;
 spin_lock_irqsave(&f355_lock,flags);rc=f355_core_begin(&f355_state);
 spin_unlock_irqrestore(&f355_lock,flags);return rc;
}
void qdrv_f355_boot_failure(void)
{
 unsigned long flags;spin_lock_irqsave(&f355_lock,flags);
 f355_boot_failure(&f355_state);spin_unlock_irqrestore(&f355_lock,flags);
}
bool qdrv_f355_retained(void){return READ_ONCE(f355_state.retained);}
bool qdrv_f355_ready(void){return READ_ONCE(f355_state.ready)&&!READ_ONCE(f355_state.closing);}
bool qdrv_f355_failed(void){return READ_ONCE(f355_state.boot_failed);}
void qdrv_f355_ready_commit(void)
{
 unsigned long flags;spin_lock_irqsave(&f355_lock,flags);
 f355_state.ready=true;spin_unlock_irqrestore(&f355_lock,flags);
}
int qdrv_f355_exit_begin(void)
{
 unsigned long flags;int rc;spin_lock_irqsave(&f355_lock,flags);
 rc=f355_exit_begin(&f355_state);spin_unlock_irqrestore(&f355_lock,flags);return rc;
}
int qdrv_f355_status(char *buf)
{
 unsigned long flags;int n;spin_lock_irqsave(&f355_lock,flags);
 n=scnprintf(buf,512,"schema=openmitrastar.f355-lifetime/v1\nready=%u\nretained=%u\ncore_attempted=%u\nboot_failed=%u\nreboot_required=%u\nrelease_supported=0\nfirst_operation=%s\n",
  f355_state.ready,f355_state.retained,f355_state.core_attempted,
  f355_state.boot_failed,f355_state.retained,f355_first_operation);
 spin_unlock_irqrestore(&f355_lock,flags);return n;
}
