#ifndef OPENMITRASTAR_COMPAT_BOARD_PM_H
#define OPENMITRASTAR_COMPAT_BOARD_PM_H

#include <linux/pm_qos_params.h>
#include <linux/workqueue.h>

int pm_queue_work(struct delayed_work *dwork, unsigned long delay);
int pm_flush_work(struct delayed_work *dwork);

#endif
