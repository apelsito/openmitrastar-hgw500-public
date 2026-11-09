// SPDX-License-Identifier: GPL-2.0
/* Quantenna PM_QOS_POWER_SAVE compatibility for Linux 5.10. */

#include <linux/errno.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/notifier.h>
#include <linux/slab.h>
#include <linux/string.h>

#include <linux/pm_qos_params.h>

struct qdrv_pm_qos_requirement {
	struct list_head list;
	char *name;
	s32 value;
};

static LIST_HEAD(qdrv_pm_qos_requirements);
static DEFINE_MUTEX(qdrv_pm_qos_lock);
static BLOCKING_NOTIFIER_HEAD(qdrv_pm_qos_notifiers);

/* Match the OEM class: default 1, initial aggregate 0. */
static s32 qdrv_pm_qos_target = BOARD_PM_LEVEL_FORCE_NO;

static bool qdrv_pm_qos_valid_class(int pm_qos_class)
{
	return pm_qos_class == PM_QOS_POWER_SAVE;
}

static s32 qdrv_pm_qos_normalize(s32 value)
{
	return value == PM_QOS_DEFAULT_VALUE ? BOARD_PM_LEVEL_NO : value;
}

static s32 qdrv_pm_qos_aggregate_locked(void)
{
	struct qdrv_pm_qos_requirement *req;
	s32 target = BOARD_PM_LEVEL_NO;

	list_for_each_entry(req, &qdrv_pm_qos_requirements, list) {
		if (req->value == BOARD_PM_LEVEL_FORCE_NO)
			return BOARD_PM_LEVEL_FORCE_NO;
		if (req->value > target)
			target = req->value;
	}

	return target;
}

static void qdrv_pm_qos_update_target(void)
{
	s32 target;
	bool changed;

	mutex_lock(&qdrv_pm_qos_lock);
	target = qdrv_pm_qos_aggregate_locked();
	changed = target != qdrv_pm_qos_target;
	WRITE_ONCE(qdrv_pm_qos_target, target);
	mutex_unlock(&qdrv_pm_qos_lock);

	if (changed)
		blocking_notifier_call_chain(&qdrv_pm_qos_notifiers,
					     (unsigned long)target, NULL);
}

static struct qdrv_pm_qos_requirement *
qdrv_pm_qos_find_locked(const char *name)
{
	struct qdrv_pm_qos_requirement *req;

	list_for_each_entry(req, &qdrv_pm_qos_requirements, list) {
		if (!strcmp(req->name, name))
			return req;
	}

	return NULL;
}

int pm_qos_requirement(int pm_qos_class)
{
	if (!qdrv_pm_qos_valid_class(pm_qos_class))
		return -EINVAL;

	return READ_ONCE(qdrv_pm_qos_target);
}
EXPORT_SYMBOL(pm_qos_requirement);

int pm_qos_add_requirement(int pm_qos_class, const char *name, s32 value)
{
	struct qdrv_pm_qos_requirement *req;

	if (!qdrv_pm_qos_valid_class(pm_qos_class) || !name)
		return -EINVAL;

	req = kzalloc(sizeof(*req), GFP_KERNEL);
	if (!req)
		return -ENOMEM;

	req->name = kstrdup(name, GFP_KERNEL);
	if (!req->name) {
		kfree(req);
		return -ENOMEM;
	}
	req->value = qdrv_pm_qos_normalize(value);

	mutex_lock(&qdrv_pm_qos_lock);
	if (qdrv_pm_qos_find_locked(name)) {
		mutex_unlock(&qdrv_pm_qos_lock);
		kfree(req->name);
		kfree(req);
		return -EEXIST;
	}
	list_add_tail(&req->list, &qdrv_pm_qos_requirements);
	mutex_unlock(&qdrv_pm_qos_lock);

	qdrv_pm_qos_update_target();
	return 0;
}
EXPORT_SYMBOL(pm_qos_add_requirement);

int pm_qos_update_requirement(int pm_qos_class, const char *name,
			      s32 new_value)
{
	struct qdrv_pm_qos_requirement *req;

	if (!qdrv_pm_qos_valid_class(pm_qos_class) || !name)
		return -EINVAL;

	mutex_lock(&qdrv_pm_qos_lock);
	req = qdrv_pm_qos_find_locked(name);
	if (req)
		req->value = qdrv_pm_qos_normalize(new_value);
	mutex_unlock(&qdrv_pm_qos_lock);

	if (!req)
		return -ENOENT;

	qdrv_pm_qos_update_target();
	return 0;
}
EXPORT_SYMBOL(pm_qos_update_requirement);

void pm_qos_remove_requirement(int pm_qos_class, const char *name)
{
	struct qdrv_pm_qos_requirement *req;

	if (!qdrv_pm_qos_valid_class(pm_qos_class) || !name)
		return;

	mutex_lock(&qdrv_pm_qos_lock);
	req = qdrv_pm_qos_find_locked(name);
	if (req)
		list_del(&req->list);
	mutex_unlock(&qdrv_pm_qos_lock);

	if (!req)
		return;

	kfree(req->name);
	kfree(req);
	qdrv_pm_qos_update_target();
}
EXPORT_SYMBOL(pm_qos_remove_requirement);

int pm_qos_add_notifier(int pm_qos_class, struct notifier_block *notifier)
{
	if (!qdrv_pm_qos_valid_class(pm_qos_class))
		return -EINVAL;

	return blocking_notifier_chain_register(&qdrv_pm_qos_notifiers, notifier);
}
EXPORT_SYMBOL(pm_qos_add_notifier);

int pm_qos_remove_notifier(int pm_qos_class, struct notifier_block *notifier)
{
	if (!qdrv_pm_qos_valid_class(pm_qos_class))
		return -EINVAL;

	return blocking_notifier_chain_unregister(&qdrv_pm_qos_notifiers,
						  notifier);
}
EXPORT_SYMBOL(pm_qos_remove_notifier);

void pm_qos_refresh_notifiers(int pm_qos_class)
{
	if (!qdrv_pm_qos_valid_class(pm_qos_class))
		return;

	blocking_notifier_call_chain(&qdrv_pm_qos_notifiers,
				     (unsigned long)READ_ONCE(qdrv_pm_qos_target),
				     NULL);
}
EXPORT_SYMBOL(pm_qos_refresh_notifiers);

MODULE_DESCRIPTION("OpenMitraStar Quantenna PM QoS compatibility");
MODULE_LICENSE("GPL");
