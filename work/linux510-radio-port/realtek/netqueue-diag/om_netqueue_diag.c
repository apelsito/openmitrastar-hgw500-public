// SPDX-License-Identifier: GPL-2.0-only
/*
 * Read-only netdev/mac80211 queue snapshot for the HGW-500BNA-QCv2 lab.
 * Loading and unloading the module never changes queue state.
 */

#include <linux/delay.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/of.h>
#include <linux/workqueue.h>
#include <net/net_namespace.h>
#include <net/sch_generic.h>

static char *ifname = "wlan0";
module_param(ifname, charp, 0444);
MODULE_PARM_DESC(ifname, "Network interface to observe (default wlan0)");

static unsigned int samples = 60;
module_param(samples, uint, 0444);
MODULE_PARM_DESC(samples, "Number of read-only queue samples (1..600)");

static unsigned int interval_ms = 250;
module_param(interval_ms, uint, 0444);
MODULE_PARM_DESC(interval_ms, "Milliseconds between samples (20..5000)");

static struct delayed_work om_netqueue_work;
static struct net_device *om_netqueue_dev;
static unsigned int om_netqueue_seq;

static void om_netqueue_sample(struct work_struct *work)
{
	struct rtnl_link_stats64 temp;
	const struct rtnl_link_stats64 *stats;
	unsigned int q;

	if (!om_netqueue_dev)
		return;

	stats = dev_get_stats(om_netqueue_dev, &temp);
	pr_info("OMNETQ sample=%u if=%s running=%u carrier=%u queues=%u tx_packets=%llu tx_bytes=%llu tx_dropped=%llu\n",
		om_netqueue_seq, om_netqueue_dev->name,
		netif_running(om_netqueue_dev), netif_carrier_ok(om_netqueue_dev),
		om_netqueue_dev->real_num_tx_queues,
		(unsigned long long)stats->tx_packets,
		(unsigned long long)stats->tx_bytes,
		(unsigned long long)stats->tx_dropped);

	for (q = 0; q < om_netqueue_dev->real_num_tx_queues; q++) {
		struct netdev_queue *txq = netdev_get_tx_queue(om_netqueue_dev, q);
		struct Qdisc *qdisc;
		unsigned int qlen = 0;

		rcu_read_lock_bh();
		qdisc = rcu_dereference_bh(txq->qdisc);
		if (qdisc)
			qlen = qdisc_qlen(qdisc);
		rcu_read_unlock_bh();

		pr_info("OMNETQ queue=%u stopped=%u frozen=%u xmit_stopped=%u qdisc_qlen=%u trans_start=%lu\n",
			q, netif_tx_queue_stopped(txq),
			test_bit(__QUEUE_STATE_FROZEN, &txq->state),
			netif_xmit_stopped(txq),
			qlen, READ_ONCE(txq->trans_start));
	}

	om_netqueue_seq++;
	if (om_netqueue_seq < samples)
		schedule_delayed_work(&om_netqueue_work,
				      msecs_to_jiffies(interval_ms));
	else
		pr_info("OMNETQ complete samples=%u classification=READ_ONLY\n",
			om_netqueue_seq);
}

static int __init om_netqueue_init(void)
{
	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")) {
		pr_err("OMNETQ refused reason=wrong-target\n");
		return -ENODEV;
	}
	if (!samples || samples > 600 || interval_ms < 20 || interval_ms > 5000)
		return -EINVAL;

	om_netqueue_dev = dev_get_by_name(&init_net, ifname);
	if (!om_netqueue_dev) {
		pr_err("OMNETQ refused reason=interface-missing if=%s\n", ifname);
		return -ENODEV;
	}
	INIT_DELAYED_WORK(&om_netqueue_work, om_netqueue_sample);
	pr_info("OMNETQ start if=%s samples=%u interval_ms=%u classification=READ_ONLY\n",
		ifname, samples, interval_ms);
	schedule_delayed_work(&om_netqueue_work, 0);
	return 0;
}

static void __exit om_netqueue_exit(void)
{
	cancel_delayed_work_sync(&om_netqueue_work);
	if (om_netqueue_dev) {
		dev_put(om_netqueue_dev);
		om_netqueue_dev = NULL;
	}
	pr_info("OMNETQ stopped classification=READ_ONLY\n");
}

module_init(om_netqueue_init);
module_exit(om_netqueue_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenMitraStar read-only netdev queue discriminator");
MODULE_AUTHOR("OpenMitraStar lab");
