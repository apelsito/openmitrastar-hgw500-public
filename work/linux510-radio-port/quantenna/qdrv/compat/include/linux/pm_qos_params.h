#ifndef OPENMITRASTAR_COMPAT_PM_QOS_PARAMS_H
#define OPENMITRASTAR_COMPAT_PM_QOS_PARAMS_H

#include <linux/notifier.h>
#include <linux/types.h>

#include <common/ruby_pm.h>

/* Quantenna's private power-save QoS class removed from modern kernels. */
#define PM_QOS_POWER_SAVE 4

#ifndef PM_QOS_DEFAULT_VALUE
#define PM_QOS_DEFAULT_VALUE (-1)
#endif

int pm_qos_requirement(int pm_qos_class);
int pm_qos_add_requirement(int pm_qos_class, const char *name, s32 value);
int pm_qos_update_requirement(int pm_qos_class, const char *name,
			      s32 new_value);
void pm_qos_remove_requirement(int pm_qos_class, const char *name);
int pm_qos_add_notifier(int pm_qos_class, struct notifier_block *notifier);
int pm_qos_remove_notifier(int pm_qos_class, struct notifier_block *notifier);
void pm_qos_refresh_notifiers(int pm_qos_class);

#endif
