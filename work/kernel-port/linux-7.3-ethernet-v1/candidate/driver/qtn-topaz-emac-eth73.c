// SPDX-License-Identifier: GPL-2.0-only
/*
 * F352 two-port derivative of the exact F340 direct-DMA driver.
 * Each port owns its own rings/IRQ/NAPI; shared MDIO is serialized.
 * This candidate is disabled until the versioned DT explicitly opts in.
 * Historical F340 behavior documented below applies to each fixed port:
 *
 * This deliberately excludes the proprietary HBM/TQE accelerated path.  It
 * normally preserves the RGMII/PHY state established by Bootbase and only
 * takes over one EMAC DMA engine.  The explicit HGW-500BNA RAM-rescue DT gate
 * can instead restart PHY autonegotiation and select the linked MAC when a
 * serial handoff follows a Bootbase negotiation timeout.
 */

#include <linux/unaligned.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/build_bug.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/etherdevice.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/mii.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/rtnetlink.h>
#include "f352_contract.h"
#include <linux/netdevice.h>
#include <linux/of.h>
#include <linux/of_net.h>
#include <linux/platform_device.h>
#include <linux/skbuff.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/soc/qtn/topaz-ethernet.h>
#include <linux/sysfs.h>
#include <linux/workqueue.h>

#define QTN_TOPAZ_EMAC_TX_RING_COUNT	64
#define QTN_TOPAZ_EMAC_RX_RING_COUNT	256
#define QTN_TOPAZ_EMAC_NAPI_WEIGHT	128
#define QTN_TOPAZ_EMAC_RX_BUF_SIZE	2048
#define QTN_TOPAZ_EMAC_QUIESCE_US	50000
#define QTN_TOPAZ_EMAC_POLL_INTERVAL_MS	10
#define QTN_TOPAZ_EMAC_POLL_TRACE_FIRST	8
#define QTN_TOPAZ_EMAC_POLL_TRACE_DELAY_MS	1000
#define QTN_TOPAZ_EMAC_POLL_IDLE_LOG_MS	5000
#define QTN_TOPAZ_EMAC_POLL_STALL_POKE_MS	2000
#define QTN_TOPAZ_EMAC_POLL_POKE_INTERVAL_MS	250
#define QTN_TOPAZ_EMAC_RX_RESTART_POKES	16
#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS	10000
#define QTN_TOPAZ_EMAC_RX_RESTART_QUIESCE_US	5000
#define QTN_TOPAZ_EMAC_PORT_COUNT	2
#define QTN_TOPAZ_EMAC_AUTONEG_TIMEOUT_MS	8000
#define QTN_TOPAZ_EMAC_AUTONEG_POLL_MS	50

struct qtn_topaz_emac_port {
	void __iomem *regs;
	int irq;
	u32 mac_id;
	u32 phy_addr;
};

struct qtn_topaz_emac_buffer {
	struct sk_buff *skb;
	dma_addr_t dma;
	u32 len;
};

struct f352_pair {
 struct device *dev;
 struct qtn_topaz_emac_port ports[2];
 struct net_device *ndev[2];
 void __iomem *sysctl_regs;
 struct mutex mdio_lock;
 spinlock_t clock_lock;
 u8 addresses[2][ETH_ALEN];
};
struct qtn_topaz_emac {
	struct device *dev;
	struct net_device *ndev;
	struct f352_pair *pair;
	struct delayed_work link_work;
	bool link_polling;
	void __iomem *regs;
	void __iomem *mdio_regs;
	void __iomem *sysctl_regs;
	struct qtn_topaz_emac_port ports[QTN_TOPAZ_EMAC_PORT_COUNT];
	u32 port_count;
	u32 active_port;
	u32 mac_id;
	u32 phy_addr;
	bool phy_autoneg;
	bool phy_link_valid;
	struct napi_struct napi;
	spinlock_t tx_lock;

	struct qtn_topaz_emac_desc *tx_descs;
	dma_addr_t tx_descs_dma;
	void *desc_alloc;
	dma_addr_t desc_alloc_dma;
	size_t desc_alloc_size;
	struct qtn_topaz_emac_buffer tx_bufs[QTN_TOPAZ_EMAC_TX_RING_COUNT];
	u16 tx_head;
	u16 tx_tail;

	struct qtn_topaz_emac_desc *rx_descs;
	dma_addr_t rx_descs_dma;
	struct qtn_topaz_emac_buffer rx_bufs[QTN_TOPAZ_EMAC_RX_RING_COUNT];
	u16 rx_head;

	u32 fixed_speed;
	u32 active_speed;
	bool active_full_duplex;
	int irq;
	bool irq_requested;
	/* Latched forever if stopped DMA cannot be observed. */
	bool dma_unsafe;
	struct delayed_work irq_poll_work;
	bool irq_poll_fallback;
	u32 irq20_count;
	u32 poll_ticks;
	u8 poll_trace_budget;
	unsigned long poll_last_rx_packets;
	unsigned long poll_last_reported_packets;
	unsigned long poll_last_progress_jiffies;
	unsigned long poll_last_trace_jiffies;
	unsigned long poll_trace_start_jiffies;
	unsigned long poll_last_poke_jiffies;
	unsigned long poll_last_rx_restart_jiffies;
	u32 poll_last_cur_rx;
	u32 poll_same_cur_rx_pokes;
	u32 poll_stall_pokes;
	u32 poll_rx_dma_restarts;
	u32 poll_rx_restart_throttled;
	u32 poll_forced_napi;
	u32 irq_tx_done;
	u32 irq_rx_done;
	u32 irq_mac;
	u32 irq_rx_stopped;
	u32 irq_no_rx_desc;
	u32 irq_rx_missed;
	u32 irq_napi_schedules;
	u32 poll_napi_schedules;
	u32 napi_polls;
	u32 napi_completes;
	u32 napi_budget_exhaustions;
	u32 napi_rx_work;
	u32 rx_head_dma_owned_samples;
	u32 rx_head_cpu_owned_descs;
	u32 rx_alloc_failures;
	u32 rx_invalid_frames;
	u32 dma_rx_stopped_samples;
	u32 dma_no_rx_desc_samples;
	u32 dma_rx_missed_samples;
	u32 rx_restart_reason_stopped;
	u32 rx_restart_reason_no_desc;
	u32 rx_restart_reason_missed;
	u32 rx_restart_reason_stagnant;
	u32 poll_rx_quiesce_timeouts;
};

static inline u32 qtn_emac_read(struct qtn_topaz_emac *emac, u32 reg);
static inline u32 qtn_desc_read(const u32 *address);

static ssize_t qtn_emac_stats(struct net_device *ndev, char *buf)
{
	struct qtn_topaz_emac *emac;
	u32 dma_status;
	u32 dma_ctrl;
	u32 cur_rx;
	u32 rx_head_status;

	if (!ndev)
		return -ENODEV;
	emac = netdev_priv(ndev);
	dma_status = qtn_emac_read(emac, QTN_EMAC_DMA_STATUS_IRQ);
	dma_ctrl = qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	cur_rx = qtn_emac_read(emac, QTN_EMAC_DMA_CUR_RXDESC_PTR);
	rx_head_status = qtn_desc_read(&emac->rx_descs[READ_ONCE(emac->rx_head)].status);

	return sysfs_emit(buf,
		"schema=1\n"
		"irq=%d\nirq_count=%u\nirq_tx_done=%u\nirq_rx_done=%u\nirq_mac=%u\n"
		"irq_rx_stopped=%u\nirq_no_rx_desc=%u\nirq_rx_missed=%u\n"
		"irq_napi_schedules=%u\n"
		"napi_weight=%u\npoll_ticks=%u\npoll_napi_schedules=%u\npoll_forced_napi=%u\n"
		"napi_polls=%u\nnapi_completes=%u\nnapi_budget_exhaustions=%u\nnapi_rx_work=%u\n"
		"rx_head_dma_owned_samples=%u\nrx_head_cpu_owned_descs=%u\n"
		"rx_alloc_failures=%u\nrx_invalid_frames=%u\n"
		"dma_rx_stopped_samples=%u\ndma_no_rx_desc_samples=%u\ndma_rx_missed_samples=%u\n"
		"rx_restart_total=%u\nrx_restart_reason_stopped=%u\n"
		"rx_restart_reason_no_desc=%u\nrx_restart_reason_missed=%u\n"
		"rx_restart_reason_stagnant=%u\nrx_restart_throttled=%u\n"
		"rx_quiesce_timeouts=%u\n"
		"stall_pokes=%u\nsame_cur_rx_pokes=%u\n"
		"rx_head=%u\nrx_head_status=%08x\ncur_rx=%08x\ndma_status=%08x\ndma_ctrl=%08x\n",
		emac->irq, READ_ONCE(emac->irq20_count),
		READ_ONCE(emac->irq_tx_done), READ_ONCE(emac->irq_rx_done),
		READ_ONCE(emac->irq_mac), READ_ONCE(emac->irq_rx_stopped),
		READ_ONCE(emac->irq_no_rx_desc), READ_ONCE(emac->irq_rx_missed),
		READ_ONCE(emac->irq_napi_schedules), QTN_TOPAZ_EMAC_NAPI_WEIGHT,
		READ_ONCE(emac->poll_ticks),
		READ_ONCE(emac->poll_napi_schedules),
		READ_ONCE(emac->poll_forced_napi), READ_ONCE(emac->napi_polls),
		READ_ONCE(emac->napi_completes),
		READ_ONCE(emac->napi_budget_exhaustions),
		READ_ONCE(emac->napi_rx_work),
		READ_ONCE(emac->rx_head_dma_owned_samples),
		READ_ONCE(emac->rx_head_cpu_owned_descs),
		READ_ONCE(emac->rx_alloc_failures),
		READ_ONCE(emac->rx_invalid_frames),
		READ_ONCE(emac->dma_rx_stopped_samples),
		READ_ONCE(emac->dma_no_rx_desc_samples),
		READ_ONCE(emac->dma_rx_missed_samples),
		READ_ONCE(emac->poll_rx_dma_restarts),
		READ_ONCE(emac->rx_restart_reason_stopped),
		READ_ONCE(emac->rx_restart_reason_no_desc),
		READ_ONCE(emac->rx_restart_reason_missed),
		READ_ONCE(emac->rx_restart_reason_stagnant),
		READ_ONCE(emac->poll_rx_restart_throttled),
		READ_ONCE(emac->poll_rx_quiesce_timeouts),
		READ_ONCE(emac->poll_stall_pokes),
		READ_ONCE(emac->poll_same_cur_rx_pokes), READ_ONCE(emac->rx_head),
		rx_head_status, cur_rx, dma_status, dma_ctrl);
}

static ssize_t lyoko_emac_stats_show(struct device *dev,
 struct device_attribute *attr,char *buf)
{return qtn_emac_stats(dev_get_drvdata(dev),buf);}
static DEVICE_ATTR_RO(lyoko_emac_stats);
static void f352_link_work(struct work_struct *work);

static inline u32 qtn_emac_read(struct qtn_topaz_emac *emac, u32 reg)
{
	return readl(emac->regs + reg);
}

static inline void qtn_emac_write(struct qtn_topaz_emac *emac, u32 reg,
				  u32 value)
{
	writel(value, emac->regs + reg);
}

static int qtn_emac_mdio_wait(struct qtn_topaz_emac *emac)
{
	u32 value;

	return readl_poll_timeout(emac->mdio_regs + QTN_EMAC_MAC_MDIO_CTRL,
				  value, !(value & QTN_EMAC_MDIO_START),
				  10, 100000);
}

static int qtn_emac_mdio_read_unlocked(struct qtn_topaz_emac *emac, u32 phy,
			      u32 reg, u16 *value)
{
	u32 control;
	int ret;

	ret = qtn_emac_mdio_wait(emac);
	if (ret)
		return ret;
	control = (phy & QTN_EMAC_MDIO_PHY_MASK) |
		  ((reg << QTN_EMAC_MDIO_REG_SHIFT) & QTN_EMAC_MDIO_REG_MASK) |
		  QTN_EMAC_MDIO_CLK_DIV_1 | QTN_EMAC_MDIO_READ |
		  QTN_EMAC_MDIO_START;
	writel(control, emac->mdio_regs + QTN_EMAC_MAC_MDIO_CTRL);
	ret = qtn_emac_mdio_wait(emac);
	if (ret)
		return ret;
	*value = readl(emac->mdio_regs + QTN_EMAC_MAC_MDIO_DATA) &
		 QTN_EMAC_MDIO_DATA_MASK;
	return 0;
}

static int qtn_emac_mdio_write_unlocked(struct qtn_topaz_emac *emac, u32 phy,
			       u32 reg, u16 value)
{
	u32 control;
	int ret;

	ret = qtn_emac_mdio_wait(emac);
	if (ret)
		return ret;
	writel(value, emac->mdio_regs + QTN_EMAC_MAC_MDIO_DATA);
	control = (phy & QTN_EMAC_MDIO_PHY_MASK) |
		  ((reg << QTN_EMAC_MDIO_REG_SHIFT) & QTN_EMAC_MDIO_REG_MASK) |
		  QTN_EMAC_MDIO_CLK_DIV_1 | QTN_EMAC_MDIO_START;
	writel(control, emac->mdio_regs + QTN_EMAC_MAC_MDIO_CTRL);
	return qtn_emac_mdio_wait(emac);
}

static int qtn_emac_mdio_read(struct qtn_topaz_emac *emac,u32 phy,u32 reg,u16 *value)
{
 int ret;mutex_lock(&emac->pair->mdio_lock);
 ret=qtn_emac_mdio_read_unlocked(emac,phy,reg,value);
 mutex_unlock(&emac->pair->mdio_lock);return ret;
}
static int qtn_emac_mdio_write(struct qtn_topaz_emac *emac,u32 phy,u32 reg,u16 value)
{
 int ret;mutex_lock(&emac->pair->mdio_lock);
 ret=qtn_emac_mdio_write_unlocked(emac,phy,reg,value);
 mutex_unlock(&emac->pair->mdio_lock);return ret;
}
static int qtn_emac_phy_state(struct qtn_topaz_emac *emac, u32 phy,
			      u16 *bmcr, u16 *bmsr)
{
	int ret;

	ret = qtn_emac_mdio_read(emac, phy, MII_BMCR, bmcr);
	if (ret)
		return ret;
	/* BMSR link is latch-low; the second read is the current state. */
	ret = qtn_emac_mdio_read(emac, phy, MII_BMSR, bmsr);
	if (ret)
		return ret;
	return qtn_emac_mdio_read(emac, phy, MII_BMSR, bmsr);
}

static int qtn_emac_phy_decode(struct qtn_topaz_emac *emac,u32 phy,
 u32 *speed,bool *full_duplex)
{
 u16 bmcr,bmsr,adv=0,lpa=0,adv1000=0,lpa1000=0;unsigned full=0,next_speed=0;int ret;
 ret=qtn_emac_phy_state(emac,phy,&bmcr,&bmsr);if(ret)return ret;
 if((bmcr&BMCR_ANENABLE)&&(bmsr&BMSR_LSTATUS)&&(bmsr&BMSR_ANEGCOMPLETE)){
  ret=qtn_emac_mdio_read(emac,phy,MII_ADVERTISE,&adv);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_LPA,&lpa);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_CTRL1000,&adv1000);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_STAT1000,&lpa1000);if(ret)return ret;
 }
 ret=f352_link_decode(bmcr,bmsr,adv,lpa,adv1000,lpa1000,&next_speed,&full);
 if(!ret){*speed=next_speed;*full_duplex=!!full;}return ret;
}

static int qtn_emac_select_rescue_port(struct qtn_topaz_emac *emac)
{
	unsigned long deadline;
	u16 bmcr = 0, bmsr = 0, id1 = 0, id2 = 0;
	u32 i;
	int ret;

	if (!emac->phy_autoneg)
		return 0;

	/* First preserve a completed Bootbase negotiation if one exists. */
	for (i = 0; i < emac->port_count; i++) {
		ret = qtn_emac_phy_decode(emac, emac->ports[i].phy_addr,
					    &emac->active_speed,
					    &emac->active_full_duplex);
		if (!ret)
			goto selected;
	}

	/* Bootbase serial rescue may have timed out before the cable was ready.
	 * Restart negotiation on both QHS860 RTL8211E PHYs, then choose the MAC
	 * paired with the first PHY that reports a completed, live link.
	 */
	for (i = 0; i < emac->port_count; i++) {
		ret = qtn_emac_phy_state(emac, emac->ports[i].phy_addr,
					   &bmcr, &bmsr);
		if (ret)
			continue;
		bmcr &= ~(BMCR_PDOWN | BMCR_ISOLATE);
		bmcr |= BMCR_ANENABLE | BMCR_ANRESTART;
		qtn_emac_mdio_write(emac, emac->ports[i].phy_addr,
				    MII_BMCR, bmcr);
	}

	deadline = jiffies +
		msecs_to_jiffies(QTN_TOPAZ_EMAC_AUTONEG_TIMEOUT_MS);
	do {
		for (i = 0; i < emac->port_count; i++) {
			ret = qtn_emac_phy_decode(emac,
						    emac->ports[i].phy_addr,
						    &emac->active_speed,
						    &emac->active_full_duplex);
			if (!ret)
				goto selected;
		}
		msleep(QTN_TOPAZ_EMAC_AUTONEG_POLL_MS);
	} while (time_before(jiffies, deadline));

	for (i = 0; i < emac->port_count; i++) {
		id1 = id2 = bmcr = bmsr = 0;
		qtn_emac_mdio_read(emac, emac->ports[i].phy_addr,
				   MII_PHYSID1, &id1);
		qtn_emac_mdio_read(emac, emac->ports[i].phy_addr,
				   MII_PHYSID2, &id2);
		qtn_emac_phy_state(emac, emac->ports[i].phy_addr,
				    &bmcr, &bmsr);
		netdev_warn(emac->ndev,
			    "OMEMAC phy candidate mac=%u phy=%u id=%04x%04x bmcr=%04x bmsr=%04x link=%u aneg=%u\n",
			    emac->ports[i].mac_id, emac->ports[i].phy_addr,
			    id1, id2, bmcr, bmsr, !!(bmsr & BMSR_LSTATUS),
			    !!(bmsr & BMSR_ANEGCOMPLETE));
	}
	emac->phy_link_valid = false;
	emac->active_speed = emac->fixed_speed;
	emac->active_full_duplex = true;
	netdev_warn(emac->ndev,
		    "OMEMAC phy-autoneg timeout; retaining preferred mac=%u phy=%u at fallback=%u/full carrier=off\n",
		    emac->mac_id, emac->phy_addr, emac->active_speed);
	return -ENOLINK;

selected:
	emac->active_port = i;
	emac->regs = emac->ports[i].regs;
	emac->irq = emac->ports[i].irq;
	emac->mac_id = emac->ports[i].mac_id;
	emac->phy_addr = emac->ports[i].phy_addr;
	emac->phy_link_valid = true;
	emac->ndev->irq = emac->irq;
	netdev_info(emac->ndev,
		    "OMEMAC phy selected mac=%u phy=%u irq=%d speed=%u/%s\n",
		    emac->mac_id, emac->phy_addr, emac->irq,
		    emac->active_speed,
		    emac->active_full_duplex ? "full" : "half");
	return 0;
}

static void qtn_emac_program_gmii_clock(struct qtn_topaz_emac *emac)
{
	u32 clock;
	u32 shift;
	u32 mask;
	unsigned long flags;

	if (!emac->sysctl_regs)
		return;
	shift = emac->mac_id ? QTN_TOPAZ_GMII1_CLOCK_SHIFT :
		QTN_TOPAZ_GMII0_CLOCK_SHIFT;
	mask = QTN_TOPAZ_GMII_CLOCK_MASK << shift;
	switch (emac->active_speed) {
	case 10:
		clock = QTN_TOPAZ_GMII_CLOCK_10;
		break;
	case 100:
		clock = QTN_TOPAZ_GMII_CLOCK_100;
		break;
	default:
		clock = QTN_TOPAZ_GMII_CLOCK_1000;
		break;
	}
	spin_lock_irqsave(&emac->pair->clock_lock, flags);
	writel(mask, emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL_MASK);
	writel(clock << shift, emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL);
	writel(0, emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL_MASK);
	readl(emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL);
	spin_unlock_irqrestore(&emac->pair->clock_lock, flags);
	netdev_info(emac->ndev,
		    "OMEMAC gmii clock mac=%u speed=%u mask=%08x\n",
		    emac->mac_id, emac->active_speed, mask);
}

/* Topaz SRAM is cacheable at 0x88000000.  Quantenna's ARC700 ABI accesses
 * shared DMA descriptors through ld.di/st.di, which bypass D-cache without
 * relying on an MMUv2 vmalloc/ioremap translation.
 */
static inline u32 qtn_desc_read(const u32 *address)
{
	u32 value;

	asm volatile("ld.di %0, [%1]"
		     : "=r" (value)
		     : "r" (address)
		     : "memory");
	return value;
}

static inline void qtn_desc_write(u32 *address, u32 value)
{
	asm volatile("st.di %0, [%1]"
		     :
		     : "r" (value), "r" (address)
		     : "memory");
}

static void qtn_desc_zero(struct qtn_topaz_emac_desc *descs,
			  unsigned int count)
{
	u32 *word = (u32 *)descs;
	unsigned int i;

	for (i = 0; i < count * (sizeof(*descs) / sizeof(*word)); i++)
		qtn_desc_write(&word[i], 0);
}

static inline u16 qtn_tx_next(u16 index)
{
	return (index + 1) & (QTN_TOPAZ_EMAC_TX_RING_COUNT - 1);
}

static inline u16 qtn_rx_next(u16 index)
{
	return (index + 1) & (QTN_TOPAZ_EMAC_RX_RING_COUNT - 1);
}

static void qtn_emac_rearm_rx(struct qtn_topaz_emac *emac, u16 index);

static void qtn_emac_disable_irqs(struct qtn_topaz_emac *emac)
{
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
	qtn_emac_write(emac, QTN_EMAC_MAC_INT_ENABLE, 0);
}

static int qtn_emac_quiesce(struct qtn_topaz_emac *emac)
{
	u32 value;

	qtn_emac_disable_irqs(emac);
	value = qtn_emac_read(emac, QTN_EMAC_MAC_TX_CTRL);
	qtn_emac_write(emac, QTN_EMAC_MAC_TX_CTRL,
			value & ~QTN_EMAC_MAC_TX_ENABLE);
	value = qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			value & ~QTN_EMAC_MAC_RX_ENABLE);
	value = qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			value & ~(QTN_EMAC_DMA_CTRL_START_TX |
				  QTN_EMAC_DMA_CTRL_START_RX));

	return readl_poll_timeout(emac->regs + QTN_EMAC_DMA_STATUS_IRQ, value,
				  !(value & (QTN_EMAC_DMA_TX_STATE_MASK |
					     QTN_EMAC_DMA_RX_STATE_MASK)),
				  10, QTN_TOPAZ_EMAC_QUIESCE_US);
}

static void qtn_emac_program_address(struct qtn_topaz_emac *emac)
{
	const u8 *address = emac->ndev->dev_addr;

	qtn_emac_write(emac, QTN_EMAC_MAC_ADDR1_HIGH,
			get_unaligned_le16(address));
	qtn_emac_write(emac, QTN_EMAC_MAC_ADDR1_MED,
			get_unaligned_le16(address + 2));
	qtn_emac_write(emac, QTN_EMAC_MAC_ADDR1_LOW,
			get_unaligned_le16(address + 4));
	qtn_emac_write(emac, QTN_EMAC_MAC_ADDR_CTRL,
			QTN_EMAC_MAC_ADDR1_ENABLE | QTN_EMAC_MAC_PROMISCUOUS);
}

static int qtn_emac_speed_bits(struct qtn_topaz_emac *emac, u32 *bits)
{
	switch (emac->fixed_speed) {
	case 10:
		*bits = QTN_EMAC_MAC_SPEED_10;
		return 0;
	case 100:
		*bits = QTN_EMAC_MAC_SPEED_100;
		return 0;
	case 1000:
		*bits = QTN_EMAC_MAC_SPEED_1000;
		return 0;
	default:
		return -EINVAL;
	}
}

static int qtn_emac_hw_start(struct qtn_topaz_emac *emac)
{
	u32 inherited_link;
	u32 speed_bits;
	u32 value;
	int ret;

	inherited_link = qtn_emac_read(emac, QTN_EMAC_MAC_GLOBAL_CTRL) &
			 (QTN_EMAC_MAC_SPEED_MASK | QTN_EMAC_MAC_FULL_DUPLEX);
	ret = qtn_emac_quiesce(emac);
	if (ret) {
		netdev_err(emac->ndev,
			   "bootloader DMA did not quiesce; refusing takeover\n");
		return ret;
	}

	ret = qtn_emac_speed_bits(emac, &speed_bits);
	if (ret)
		return ret;
	if (emac->phy_autoneg) {
		switch (emac->active_speed) {
		case 10:
			inherited_link = QTN_EMAC_MAC_SPEED_10;
			break;
		case 100:
			inherited_link = QTN_EMAC_MAC_SPEED_100;
			break;
		default:
			inherited_link = QTN_EMAC_MAC_SPEED_1000;
			break;
		}
		if (emac->active_full_duplex)
			inherited_link |= QTN_EMAC_MAC_FULL_DUPLEX;
		qtn_emac_program_gmii_clock(emac);
	} else {
		if ((inherited_link & QTN_EMAC_MAC_SPEED_MASK) ==
		    QTN_EMAC_MAC_SPEED_MASK)
			inherited_link = speed_bits | QTN_EMAC_MAC_FULL_DUPLEX;
		switch (inherited_link & QTN_EMAC_MAC_SPEED_MASK) {
		case QTN_EMAC_MAC_SPEED_10:
			emac->active_speed = 10;
			break;
		case QTN_EMAC_MAC_SPEED_100:
			emac->active_speed = 100;
			break;
		default:
			emac->active_speed = 1000;
			break;
		}
		emac->active_full_duplex =
			!!(inherited_link & QTN_EMAC_MAC_FULL_DUPLEX);
	}

	/* The OEM driver always resets the Arasan DMA block before replacing its
	 * descriptor bases.  RXP/TXP were quiesced by the RAM handoff, but repeat
	 * that locally so this driver is also correct after an ordinary probe.
	 */
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, 0);
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_TXP_CTRL, 0);
	qtn_emac_write(emac, QTN_EMAC_DMA_CONFIG,
			QTN_EMAC_DMA_CONFIG_SOFT_RESET);
	udelay(1000);
	qtn_emac_write(emac, QTN_EMAC_DMA_CONFIG,
			QTN_EMAC_DMA_CONFIG_ROUND_ROBIN |
			QTN_EMAC_DMA_CONFIG_16_WORD_BURST |
			QTN_EMAC_DMA_CONFIG_64BIT_MODE);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL, 0);
	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ,
			QTN_EMAC_DMA_IRQ_ALL);
	qtn_emac_write(emac, QTN_EMAC_DMA_TX_AUTO_POLL, 0);
	qtn_emac_write(emac, QTN_EMAC_DMA_TX_BASE_ADDR,
			lower_32_bits(emac->tx_descs_dma));
	qtn_emac_write(emac, QTN_EMAC_DMA_RX_BASE_ADDR,
			lower_32_bits(emac->rx_descs_dma));

	value = qtn_emac_read(emac, QTN_EMAC_MAC_GLOBAL_CTRL);
	value &= ~(QTN_EMAC_MAC_SPEED_MASK | QTN_EMAC_MAC_FULL_DUPLEX);
	qtn_emac_write(emac, QTN_EMAC_MAC_GLOBAL_CTRL,
			value | inherited_link);
	qtn_emac_write(emac, QTN_EMAC_MAC_TX_CTRL,
			QTN_EMAC_MAC_TX_AUTO_RETRY);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			QTN_EMAC_MAC_RX_STRIP_FCS |
			QTN_EMAC_MAC_RX_STORE_FORWARD |
			QTN_EMAC_MAC_RX_ACCOUNT_VLANS);
	qtn_emac_write(emac, QTN_EMAC_MAC_MAX_FRAME_SIZE, 0xc80);
	qtn_emac_program_address(emac);
	qtn_emac_write(emac, QTN_EMAC_MAC_FLOW_CTRL,
			QTN_EMAC_MAC_FLOW_DECODE |
			QTN_EMAC_MAC_FLOW_GENERATE |
			QTN_EMAC_MAC_FLOW_AUTO_GENERATE |
			QTN_EMAC_MAC_FLOW_MULTICAST |
			QTN_EMAC_MAC_FLOW_BLOCK_PAUSE);
	dma_wmb();
	/* Match arasan_emac_ahb start_traffic() ordering. */
	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ,
			QTN_EMAC_DMA_IRQ_TX_STOPPED |
			QTN_EMAC_DMA_IRQ_RX_STOPPED);
	qtn_emac_write(emac, QTN_EMAC_MAC_TX_CTRL,
			QTN_EMAC_MAC_TX_AUTO_RETRY | QTN_EMAC_MAC_TX_ENABLE);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			QTN_EMAC_DMA_CTRL_START_TX);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			QTN_EMAC_DMA_CTRL_START_TX |
			QTN_EMAC_DMA_CTRL_START_RX);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			QTN_EMAC_MAC_RX_ENABLE |
			QTN_EMAC_MAC_RX_STRIP_FCS |
			QTN_EMAC_MAC_RX_STORE_FORWARD |
			QTN_EMAC_MAC_RX_ACCOUNT_VLANS);
	/* Topaz's wrapper selects whether received frames feed TQE or native RX. */
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL,
			QTN_TOPAZ_EMAC_RXP_ENABLE |
			QTN_TOPAZ_EMAC_RXP_SYNC_RX_DMA);
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_TXP_CTRL,
			QTN_TOPAZ_EMAC_TXP_AHB_ENABLE);
	qtn_emac_write(emac, QTN_EMAC_MAC_INT, ~0U);
	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ, ~0U);
	qtn_emac_write(emac, QTN_EMAC_MAC_INT_ENABLE,
			QTN_EMAC_MAC_IRQ_UNDERRUN | QTN_EMAC_MAC_IRQ_JABBER);
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE,
			QTN_EMAC_DMA_IRQ_TX_DONE |
			QTN_EMAC_DMA_IRQ_RX_DONE |
			QTN_EMAC_DMA_IRQ_MAC);
	qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	return 0;
}

static int qtn_emac_restart_rx_dma(struct qtn_topaz_emac *emac, u32 dma_ctrl)
{
	u32 irq_mask;
	u32 mac_rx_ctrl;
	u32 rxp_ctrl;
	u32 value;
	u16 i;
	int ret;

	/* Called only by the running-netdev worker on the pinned single-core
	 * PREEMPT_NONE kernel. SMP/preemptible NAPI-tail interleavings are
	 * outside this candidate's qualified configuration. A zero snapshot
	 * is NAPI masking, so completion must restore the supported mask.
	 */
	irq_mask = qtn_emac_read(emac, QTN_EMAC_DMA_INT_ENABLE);
	if (!irq_mask)
		irq_mask = QTN_EMAC_DMA_IRQ_TX_DONE |
			   QTN_EMAC_DMA_IRQ_RX_DONE | QTN_EMAC_DMA_IRQ_MAC;
	mac_rx_ctrl = qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL);
	rxp_ctrl = qtn_emac_read(emac, QTN_TOPAZ_EMAC_RXP_CTRL);
	dma_ctrl = qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
	napi_disable(&emac->napi);
	/* A poll completing during napi_disable may have unmasked DMA IRQs. */
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);

	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, 0);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			mac_rx_ctrl & ~QTN_EMAC_MAC_RX_ENABLE);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			dma_ctrl & ~QTN_EMAC_DMA_CTRL_START_RX);
	/* RX_STOPPED is latched status, not proof of current DMA ownership. */
	ret = readl_poll_timeout(emac->regs + QTN_EMAC_DMA_STATUS_IRQ, value,
				 !(value & QTN_EMAC_DMA_RX_STATE_MASK),
				 10, QTN_TOPAZ_EMAC_RX_RESTART_QUIESCE_US);
	if (ret) {
		/* Preserve every descriptor/buffer and the consumer index. Restore
		 * the exact producer state from DMA outward before IRQ delivery.
		 */
		qtn_emac_write(emac, QTN_EMAC_DMA_CTRL, dma_ctrl);
		qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL, mac_rx_ctrl);
		qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, rxp_ctrl);
		napi_enable(&emac->napi);
		qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, irq_mask);
		return ret;
	}

	for (i = 0; i < QTN_TOPAZ_EMAC_RX_RING_COUNT; i++)
		qtn_emac_rearm_rx(emac, i);
	emac->rx_head = 0;

	qtn_emac_write(emac, QTN_EMAC_DMA_RX_BASE_ADDR,
			lower_32_bits(emac->rx_descs_dma));
	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ,
			QTN_EMAC_DMA_IRQ_RX_DONE |
			QTN_EMAC_DMA_IRQ_NO_RX_DESC |
			QTN_EMAC_DMA_IRQ_RX_STOPPED |
			QTN_EMAC_DMA_IRQ_RX_MISSED);
	dma_wmb();
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			dma_ctrl | QTN_EMAC_DMA_CTRL_START_RX);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			mac_rx_ctrl | QTN_EMAC_MAC_RX_ENABLE);
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL,
			QTN_TOPAZ_EMAC_RXP_ENABLE |
			QTN_TOPAZ_EMAC_RXP_SYNC_RX_DMA);
	qtn_emac_write(emac, QTN_EMAC_DMA_RX_POLL_DEMAND, 0);
	napi_enable(&emac->napi);
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, irq_mask);
	return 0;
}

/* Temporary hardware bring-up fallback.  The direct ARC IRQ20 route is not
 * reaching Linux yet, while the DMA status and descriptor writeback prove
 * RX is active.  Poll only the same status bits as the ISR and feed NAPI;
 * once IRQ20 is fixed this work can be removed without changing data paths.
 */
static void qtn_emac_irq_poll_work(struct work_struct *work)
{
	struct qtn_topaz_emac *emac =
		container_of(to_delayed_work(work), struct qtn_topaz_emac,
			     irq_poll_work);
	unsigned long packets;
	unsigned long previous_packets;
	unsigned long idle_ms;
	u32 cur_rx;
	u32 cur_tx;
	u32 dma_ctrl;
	u32 dma_status;
	u32 ring_base;
	u16 rx_prod = U16_MAX;
	u16 tx_head;
	u16 tx_tail;
	u32 pending;
	u32 mac_pending;
	int rx_restart_ret;
	bool progress;
	bool initial_trace;
	bool periodic;
	bool trace;
	bool stall_poked = false;
	bool forced_napi = false;
	bool napi_queued = false;
	bool rearmed = false;
	bool rx_restarted = false;
	bool rx_restart_throttled = false;
	u32 rx_head_status = 0;
	unsigned long delay = max_t(unsigned long, 1,
		msecs_to_jiffies(QTN_TOPAZ_EMAC_POLL_INTERVAL_MS));
	unsigned long rx_restart_cooldown =
		msecs_to_jiffies(QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS);

	/* Serialize full worker with stop/open without blocking RTNL cancellation. */
	if (!rtnl_trylock()) {
		if (emac->irq_poll_fallback && netif_running(emac->ndev))
			schedule_delayed_work(&emac->irq_poll_work, delay);
		return;
	}
	if (!netif_running(emac->ndev) || READ_ONCE(emac->dma_unsafe)) {
		rtnl_unlock();
		return;
	}
	emac->poll_ticks++;
	dma_status = qtn_emac_read(emac, QTN_EMAC_DMA_STATUS_IRQ);
	if (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)
		emac->dma_rx_stopped_samples++;
	if (dma_status & QTN_EMAC_DMA_IRQ_NO_RX_DESC)
		emac->dma_no_rx_desc_samples++;
	if (dma_status & QTN_EMAC_DMA_IRQ_RX_MISSED)
		emac->dma_rx_missed_samples++;
	pending = dma_status &
		  (QTN_EMAC_DMA_IRQ_TX_DONE | QTN_EMAC_DMA_IRQ_RX_DONE |
		   QTN_EMAC_DMA_IRQ_MAC);
	cur_rx = qtn_emac_read(emac, QTN_EMAC_DMA_CUR_RXDESC_PTR);
	cur_tx = qtn_emac_read(emac, QTN_EMAC_DMA_CUR_TXDESC_PTR);
	dma_ctrl = qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	tx_head = READ_ONCE(emac->tx_head);
	tx_tail = READ_ONCE(emac->tx_tail);
	ring_base = lower_32_bits(emac->rx_descs_dma);
	if (cur_rx >= ring_base &&
	    cur_rx < ring_base + sizeof(*emac->rx_descs) *
			     QTN_TOPAZ_EMAC_RX_RING_COUNT)
		rx_prod = (cur_rx - ring_base) / sizeof(*emac->rx_descs);
	previous_packets = emac->poll_last_rx_packets;
	packets = READ_ONCE(emac->ndev->stats.rx_packets);
	progress = packets != previous_packets;
	if (progress) {
		emac->poll_last_rx_packets = packets;
		emac->poll_last_progress_jiffies = jiffies;
	}
	idle_ms = jiffies_to_msecs(jiffies - emac->poll_last_progress_jiffies);
	periodic = time_after_eq(jiffies,
			emac->poll_last_trace_jiffies +
			msecs_to_jiffies(QTN_TOPAZ_EMAC_POLL_IDLE_LOG_MS));
	initial_trace = emac->poll_trace_budget &&
		time_after_eq(jiffies, emac->poll_trace_start_jiffies);
	if (initial_trace)
		emac->poll_trace_budget--;
	trace = initial_trace || periodic;
	if (trace) {
		emac->poll_last_trace_jiffies = jiffies;
		if (packets != emac->poll_last_reported_packets) {
			netdev_info(emac->ndev,
				    "OMEMAC poll progress packets=%lu delta=%lu tick=%u\n",
				    packets,
				    packets - emac->poll_last_reported_packets,
				    emac->poll_ticks);
			emac->poll_last_reported_packets = packets;
		}
		netdev_info(emac->ndev,
			    "OMEMAC poll tick=%u rx_cons=%u rx_prod=%u tx_head=%u tx_tail=%u cur_tx=%08x irq=%d irq20=%u pending=%08x dma_ctrl=%08x rx_packets=%lu tx_packets=%lu rx_errors=%lu tx_errors=%lu queue_stopped=%u idle_ms=%lu\n",
			    emac->poll_ticks, emac->rx_head, rx_prod,
			    tx_head, tx_tail, cur_tx, emac->irq,
			    emac->irq20_count, pending,
			    dma_ctrl, READ_ONCE(emac->ndev->stats.rx_packets),
			    READ_ONCE(emac->ndev->stats.tx_packets),
			    READ_ONCE(emac->ndev->stats.rx_errors),
			    READ_ONCE(emac->ndev->stats.tx_errors),
			    netif_queue_stopped(emac->ndev), idle_ms);
	}
	if (pending) {
		qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ, pending);
		if (pending & QTN_EMAC_DMA_IRQ_MAC) {
			mac_pending = qtn_emac_read(emac, QTN_EMAC_MAC_INT);
			qtn_emac_write(emac, QTN_EMAC_MAC_INT, mac_pending);
		}
		if (pending & (QTN_EMAC_DMA_IRQ_TX_DONE |
			       QTN_EMAC_DMA_IRQ_RX_DONE)) {
			qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
			if (napi_schedule_prep(&emac->napi)) {
				__napi_schedule(&emac->napi);
				napi_queued = true;
				emac->poll_napi_schedules++;
			}
		}
	}
	if (!pending && idle_ms >= QTN_TOPAZ_EMAC_POLL_STALL_POKE_MS &&
	    (dma_ctrl & (QTN_EMAC_DMA_CTRL_START_TX |
			 QTN_EMAC_DMA_CTRL_START_RX)) &&
	    time_after_eq(jiffies, emac->poll_last_poke_jiffies +
			  msecs_to_jiffies(QTN_TOPAZ_EMAC_POLL_POKE_INTERVAL_MS))) {
		if (cur_rx == emac->poll_last_cur_rx)
			emac->poll_same_cur_rx_pokes++;
		else
			emac->poll_same_cur_rx_pokes = 0;
		emac->poll_last_cur_rx = cur_rx;
		qtn_emac_write(emac, QTN_EMAC_DMA_RX_POLL_DEMAND, 0);
		if (tx_head != tx_tail)
			qtn_emac_write(emac, QTN_EMAC_DMA_TX_POLL_DEMAND, 0);
		emac->poll_last_poke_jiffies = jiffies;
		emac->poll_stall_pokes++;
		stall_poked = true;
		rx_head_status = qtn_desc_read(&emac->rx_descs[emac->rx_head].status);
		if (rx_head_status & QTN_EMAC_DESC_OWN)
			emac->rx_head_dma_owned_samples++;
		else
			emac->rx_head_cpu_owned_descs++;
		if (!(rx_head_status & QTN_EMAC_DESC_OWN)) {
			qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
			if (napi_schedule_prep(&emac->napi)) {
				__napi_schedule(&emac->napi);
				napi_queued = true;
				forced_napi = true;
				emac->poll_forced_napi++;
			}
		} else if (emac->poll_same_cur_rx_pokes >=
				QTN_TOPAZ_EMAC_RX_RESTART_POKES) {
			if (!time_after_eq(jiffies,
					   emac->poll_last_rx_restart_jiffies +
					   rx_restart_cooldown)) {
				rx_restart_throttled = true;
				emac->poll_rx_restart_throttled++;
				goto rearm_poll;
			}
			/* Cool down failed attempts too; they are not successful restarts. */
			rx_restart_ret = qtn_emac_restart_rx_dma(emac, dma_ctrl);
			emac->poll_last_rx_restart_jiffies = jiffies;
			if (rx_restart_ret) {
				emac->poll_rx_quiesce_timeouts++;
				goto rearm_poll;
			}
			if (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)
				emac->rx_restart_reason_stopped++;
			else if (dma_status & QTN_EMAC_DMA_IRQ_NO_RX_DESC)
				emac->rx_restart_reason_no_desc++;
			else if (dma_status & QTN_EMAC_DMA_IRQ_RX_MISSED)
				emac->rx_restart_reason_missed++;
			else
				emac->rx_restart_reason_stagnant++;
			emac->poll_rx_dma_restarts++;
			emac->poll_same_cur_rx_pokes = 0;
			emac->poll_last_progress_jiffies = jiffies;
			rx_restarted = true;
			netdev_info(emac->ndev,
				    "OMEMAC rx restart reason=stalled-cur-rx restarts=%u cooldown_ms=%u rx_head=%u rx_prod=%u dma_ctrl=%08x rx_head_status=%08x\n",
				    emac->poll_rx_dma_restarts,
				    QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS,
				    emac->rx_head, rx_prod, dma_ctrl,
				    rx_head_status);
		}
	}

rearm_poll:
	rtnl_unlock();
	if (emac->irq_poll_fallback && netif_running(emac->ndev))
		rearmed = schedule_delayed_work(&emac->irq_poll_work, delay);
	if (trace || !rearmed)
		netdev_info(emac->ndev,
			    "OMEMAC poll rearmed tick=%u queued=%u napi_queued=%u forced_napi=%u forced_napis=%u stall_poked=%u stall_pokes=%u rx_restarted=%u rx_restart_throttled=%u rx_restarts=%u same_cur_rx_pokes=%u rx_head_status=%08x\n",
			    emac->poll_ticks, rearmed, napi_queued,
			    forced_napi, emac->poll_forced_napi,
			    stall_poked, emac->poll_stall_pokes,
			    rx_restarted, rx_restart_throttled,
			    emac->poll_rx_dma_restarts,
			    emac->poll_same_cur_rx_pokes, rx_head_status);
}

static void qtn_emac_rearm_rx(struct qtn_topaz_emac *emac, u16 index)
{
	struct qtn_topaz_emac_desc *desc = &emac->rx_descs[index];
	struct qtn_topaz_emac_buffer *buffer = &emac->rx_bufs[index];
	u32 control = QTN_TOPAZ_EMAC_RX_BUF_SIZE;

	if (index == QTN_TOPAZ_EMAC_RX_RING_COUNT - 1)
		control |= QTN_EMAC_DESC_END_OF_RING;

	qtn_desc_write(&desc->bufaddr1, lower_32_bits(buffer->dma));
	qtn_desc_write(&desc->bufaddr2, 0);
	qtn_desc_write(&desc->control, control);
	dma_wmb();
	qtn_desc_write(&desc->status, QTN_EMAC_DESC_OWN);
	if (qtn_emac_read(emac, QTN_EMAC_DMA_CTRL) & QTN_EMAC_DMA_CTRL_START_RX)
		qtn_emac_write(emac, QTN_EMAC_DMA_RX_POLL_DEMAND, 0);
}

static int qtn_emac_alloc_rx_buffer(struct qtn_topaz_emac *emac, u16 index,
				    gfp_t flags)
{
	struct qtn_topaz_emac_buffer *buffer = &emac->rx_bufs[index];
	struct sk_buff *skb;
	dma_addr_t dma;

	skb = __netdev_alloc_skb_ip_align(emac->ndev,
					  QTN_TOPAZ_EMAC_RX_BUF_SIZE, flags);
	if (!skb)
		return -ENOMEM;

	dma = dma_map_single(emac->dev, skb->data,
			     QTN_TOPAZ_EMAC_RX_BUF_SIZE, DMA_FROM_DEVICE);
	if (dma_mapping_error(emac->dev, dma) || upper_32_bits(dma)) {
		if (!dma_mapping_error(emac->dev, dma))
			dma_unmap_single(emac->dev, dma,
					 QTN_TOPAZ_EMAC_RX_BUF_SIZE,
					 DMA_FROM_DEVICE);
		dev_kfree_skb_any(skb);
		return -EIO;
	}

	buffer->skb = skb;
	buffer->dma = dma;
	buffer->len = QTN_TOPAZ_EMAC_RX_BUF_SIZE;
	qtn_emac_rearm_rx(emac, index);
	return 0;
}

static void qtn_emac_free_rx_buffers(struct qtn_topaz_emac *emac)
{
	unsigned int i;
	if (READ_ONCE(emac->dma_unsafe))
		return; /* Quarantine until a hardware reset outside this driver. */


	for (i = 0; i < QTN_TOPAZ_EMAC_RX_RING_COUNT; i++) {
		struct qtn_topaz_emac_buffer *buffer = &emac->rx_bufs[i];

		if (!buffer->skb)
			continue;
		dma_unmap_single(emac->dev, buffer->dma, buffer->len,
				 DMA_FROM_DEVICE);
		dev_kfree_skb_any(buffer->skb);
		memset(buffer, 0, sizeof(*buffer));
	}
}

static void qtn_emac_tx_reclaim_locked(struct qtn_topaz_emac *emac)
{
	while (emac->tx_tail != emac->tx_head) {
		struct qtn_topaz_emac_desc *desc =
			&emac->tx_descs[emac->tx_tail];
		struct qtn_topaz_emac_buffer *buffer =
			&emac->tx_bufs[emac->tx_tail];

		u32 status = qtn_desc_read(&desc->status);

		if (status & QTN_EMAC_DESC_OWN)
			break;
		dma_rmb();
		if (buffer->skb) {
			dma_unmap_single(emac->dev, buffer->dma, buffer->len,
					 DMA_TO_DEVICE);
			dev_consume_skb_any(buffer->skb);
			memset(buffer, 0, sizeof(*buffer));
		}
		qtn_desc_write(&desc->bufaddr1, 0);
		qtn_desc_write(&desc->bufaddr2, 0);
		qtn_desc_write(&desc->control,
			       emac->tx_tail == QTN_TOPAZ_EMAC_TX_RING_COUNT - 1 ?
			       QTN_EMAC_DESC_END_OF_RING : 0);
		emac->tx_tail = qtn_tx_next(emac->tx_tail);
	}

	if (netif_queue_stopped(emac->ndev) &&
	    qtn_tx_next(emac->tx_head) != emac->tx_tail)
		netif_wake_queue(emac->ndev);
}

static void qtn_emac_free_tx_buffers(struct qtn_topaz_emac *emac)
{
	unsigned long flags;
	unsigned int i;
	if (READ_ONCE(emac->dma_unsafe))
		return; /* Quarantine until a hardware reset outside this driver. */


	spin_lock_irqsave(&emac->tx_lock, flags);
	for (i = 0; i < QTN_TOPAZ_EMAC_TX_RING_COUNT; i++) {
		struct qtn_topaz_emac_buffer *buffer = &emac->tx_bufs[i];

		if (!buffer->skb)
			continue;
		dma_unmap_single(emac->dev, buffer->dma, buffer->len,
				 DMA_TO_DEVICE);
		dev_kfree_skb_any(buffer->skb);
		memset(buffer, 0, sizeof(*buffer));
	}
	emac->tx_head = 0;
	emac->tx_tail = 0;
	spin_unlock_irqrestore(&emac->tx_lock, flags);
}

static int qtn_emac_rx_poll(struct qtn_topaz_emac *emac, int budget)
{
	int work_done = 0;

	while (work_done < budget) {
		struct qtn_topaz_emac_desc *desc =
			&emac->rx_descs[emac->rx_head];
		struct qtn_topaz_emac_buffer old_buffer;
		struct qtn_topaz_emac_buffer *buffer;
		struct sk_buff *skb;
		u32 status;
		u32 length;

		status = qtn_desc_read(&desc->status);
		if (status & QTN_EMAC_DESC_OWN) {
			emac->rx_head_dma_owned_samples++;
			break;
		}
		emac->rx_head_cpu_owned_descs++;
		dma_rmb();
		buffer = &emac->rx_bufs[emac->rx_head];
		old_buffer = *buffer;

		if (qtn_emac_alloc_rx_buffer(emac, emac->rx_head,
					     GFP_ATOMIC)) {
			emac->rx_alloc_failures++;
			emac->ndev->stats.rx_dropped++;
			dma_sync_single_for_device(emac->dev, old_buffer.dma,
						   old_buffer.len,
						   DMA_FROM_DEVICE);
			*buffer = old_buffer;
			qtn_emac_rearm_rx(emac, emac->rx_head);
			goto next;
		}

		dma_unmap_single(emac->dev, old_buffer.dma, old_buffer.len,
				 DMA_FROM_DEVICE);
		skb = old_buffer.skb;
		length = status & QTN_EMAC_RX_DESC_FRAME_LENGTH_MASK;
		if ((status & QTN_EMAC_RX_DESC_ERROR_MASK) ||
		    !(status & QTN_EMAC_RX_DESC_FIRST) ||
		    !(status & QTN_EMAC_RX_DESC_LAST) ||
		    length < ETH_HLEN || length > QTN_TOPAZ_EMAC_RX_BUF_SIZE) {
			emac->ndev->stats.rx_errors++;
			emac->rx_invalid_frames++;
			dev_kfree_skb_any(skb);
		} else {
			skb_put(skb, length);
			skb->protocol = eth_type_trans(skb, emac->ndev);
			emac->ndev->stats.rx_packets++;
			emac->ndev->stats.rx_bytes += length;
			napi_gro_receive(&emac->napi, skb);
		}

next:
		emac->rx_head = qtn_rx_next(emac->rx_head);
		work_done++;
	}

	return work_done;
}

static int qtn_emac_poll(struct napi_struct *napi, int budget)
{
	struct qtn_topaz_emac *emac =
		container_of(napi, struct qtn_topaz_emac, napi);
	unsigned long flags;
	int work_done;

	if (unlikely(READ_ONCE(emac->dma_unsafe)))
		return 0;
	emac->napi_polls++;
	spin_lock_irqsave(&emac->tx_lock, flags);
	qtn_emac_tx_reclaim_locked(emac);
	spin_unlock_irqrestore(&emac->tx_lock, flags);
	work_done = qtn_emac_rx_poll(emac, budget);
	emac->napi_rx_work += work_done;
	if (work_done == budget)
		emac->napi_budget_exhaustions++;

	if (work_done < budget && napi_complete_done(napi, work_done)) {
		emac->napi_completes++;
		qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE,
				QTN_EMAC_DMA_IRQ_TX_DONE |
				QTN_EMAC_DMA_IRQ_RX_DONE |
				QTN_EMAC_DMA_IRQ_MAC);
	}

	return work_done;
}

static irqreturn_t qtn_emac_interrupt(int irq, void *data)
{
	struct net_device *ndev = data;
	struct qtn_topaz_emac *emac = netdev_priv(ndev);
	u32 dma_status;
	u32 pending;
	u32 mac_pending;

	dma_status = qtn_emac_read(emac, QTN_EMAC_DMA_STATUS_IRQ);
	pending = dma_status &
		  (QTN_EMAC_DMA_IRQ_TX_DONE | QTN_EMAC_DMA_IRQ_RX_DONE |
		   QTN_EMAC_DMA_IRQ_MAC);
	if (!pending)
		return IRQ_NONE;
	emac->irq20_count++;
	if (dma_status & QTN_EMAC_DMA_IRQ_TX_DONE)
		emac->irq_tx_done++;
	if (dma_status & QTN_EMAC_DMA_IRQ_RX_DONE)
		emac->irq_rx_done++;
	if (dma_status & QTN_EMAC_DMA_IRQ_MAC)
		emac->irq_mac++;
	if (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)
		emac->irq_rx_stopped++;
	if (dma_status & QTN_EMAC_DMA_IRQ_NO_RX_DESC)
		emac->irq_no_rx_desc++;
	if (dma_status & QTN_EMAC_DMA_IRQ_RX_MISSED)
		emac->irq_rx_missed++;

	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ, pending);
	if (pending & QTN_EMAC_DMA_IRQ_MAC) {
		mac_pending = qtn_emac_read(emac, QTN_EMAC_MAC_INT);
		qtn_emac_write(emac, QTN_EMAC_MAC_INT, mac_pending);
	}

	if (pending & (QTN_EMAC_DMA_IRQ_TX_DONE |
		       QTN_EMAC_DMA_IRQ_RX_DONE)) {
		qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
		emac->irq_napi_schedules++;
		napi_schedule_irqoff(&emac->napi);
	}

	return IRQ_HANDLED;
}

static netdev_tx_t qtn_emac_start_xmit(struct sk_buff *skb,
				       struct net_device *ndev)
{
	struct qtn_topaz_emac *emac = netdev_priv(ndev);
	struct qtn_topaz_emac_buffer *buffer;
	struct qtn_topaz_emac_desc *desc;
	unsigned long flags;
	dma_addr_t dma;
	u32 control;
	u16 next;
	int ret;

	if (unlikely(skb_is_nonlinear(skb)) && unlikely(skb_linearize(skb))) {
		ndev->stats.tx_dropped++;
		dev_kfree_skb_any(skb);
		return NETDEV_TX_OK;
	}
	if (unlikely(skb->len > QTN_EMAC_DESC_BUF1_SIZE_MASK)) {
		ndev->stats.tx_dropped++;
		dev_kfree_skb_any(skb);
		return NETDEV_TX_OK;
	}
	if (unlikely(skb->ip_summed == CHECKSUM_PARTIAL)) {
		ret = skb_checksum_help(skb);
		if (ret) {
			ndev->stats.tx_dropped++;
			dev_kfree_skb_any(skb);
			return NETDEV_TX_OK;
		}
	}

	spin_lock_irqsave(&emac->tx_lock, flags);
	qtn_emac_tx_reclaim_locked(emac);
	next = qtn_tx_next(emac->tx_head);
	if (next == emac->tx_tail) {
		netif_stop_queue(ndev);
		spin_unlock_irqrestore(&emac->tx_lock, flags);
		return NETDEV_TX_BUSY;
	}

	dma = dma_map_single(emac->dev, skb->data, skb->len, DMA_TO_DEVICE);
	if (dma_mapping_error(emac->dev, dma) || upper_32_bits(dma)) {
		if (!dma_mapping_error(emac->dev, dma))
			dma_unmap_single(emac->dev, dma, skb->len,
					 DMA_TO_DEVICE);
		spin_unlock_irqrestore(&emac->tx_lock, flags);
		ndev->stats.tx_dropped++;
		dev_kfree_skb_any(skb);
		return NETDEV_TX_OK;
	}

	desc = &emac->tx_descs[emac->tx_head];
	buffer = &emac->tx_bufs[emac->tx_head];
	buffer->skb = skb;
	buffer->dma = dma;
	buffer->len = skb->len;
	control = QTN_EMAC_TX_DESC_INTERRUPT | QTN_EMAC_TX_DESC_FIRST |
		  QTN_EMAC_TX_DESC_LAST | skb->len;
	if (emac->tx_head == QTN_TOPAZ_EMAC_TX_RING_COUNT - 1)
		control |= QTN_EMAC_DESC_END_OF_RING;

	qtn_desc_write(&desc->bufaddr1, lower_32_bits(dma));
	qtn_desc_write(&desc->bufaddr2, 0);
	qtn_desc_write(&desc->control, control);
	dma_wmb();
	qtn_desc_write(&desc->status, QTN_EMAC_DESC_OWN);
	dma_wmb();
	emac->tx_head = next;
	ndev->stats.tx_packets++;
	ndev->stats.tx_bytes += skb->len;
	netif_trans_update(ndev);
	qtn_emac_write(emac, QTN_EMAC_DMA_TX_POLL_DEMAND, 0);

	if (qtn_tx_next(emac->tx_head) == emac->tx_tail)
		netif_stop_queue(ndev);
	spin_unlock_irqrestore(&emac->tx_lock, flags);
	return NETDEV_TX_OK;
}

static int qtn_emac_open(struct net_device *ndev)
{
	struct qtn_topaz_emac *emac = netdev_priv(ndev);
	unsigned int i;
	int ret;

	/* A failed stop permanently bars reopening and descriptor recycling. */
	if (READ_ONCE(emac->dma_unsafe))
		return -EIO;
	/* Stop inherited/previous DMA BEFORE touching descriptors or buffers. */
	ret = qtn_emac_quiesce(emac);
	if (ret) {
		WRITE_ONCE(emac->dma_unsafe, true);
		return ret;
	}
	qtn_desc_zero(emac->tx_descs, QTN_TOPAZ_EMAC_TX_RING_COUNT);
	qtn_desc_zero(emac->rx_descs, QTN_TOPAZ_EMAC_RX_RING_COUNT);
	emac->tx_head = 0;
	emac->tx_tail = 0;
	emac->rx_head = 0;
	emac->irq20_count = 0;
	emac->poll_ticks = 0;
	emac->poll_trace_budget = QTN_TOPAZ_EMAC_POLL_TRACE_FIRST;
	emac->poll_last_rx_packets = 0;
	emac->poll_last_reported_packets = 0;
	emac->poll_last_progress_jiffies = jiffies;
	emac->poll_last_trace_jiffies = jiffies;
	emac->poll_trace_start_jiffies = jiffies +
		msecs_to_jiffies(QTN_TOPAZ_EMAC_POLL_TRACE_DELAY_MS);
	emac->poll_last_poke_jiffies = jiffies;
	emac->poll_last_rx_restart_jiffies = jiffies -
		msecs_to_jiffies(QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS);
	emac->poll_last_cur_rx = 0;
	emac->poll_same_cur_rx_pokes = 0;
	emac->poll_stall_pokes = 0;
	emac->poll_rx_dma_restarts = 0;
	emac->poll_rx_quiesce_timeouts = 0;
	emac->poll_rx_restart_throttled = 0;
	emac->poll_forced_napi = 0;
	emac->irq_tx_done = 0;
	emac->irq_rx_done = 0;
	emac->irq_mac = 0;
	emac->irq_rx_stopped = 0;
	emac->irq_no_rx_desc = 0;
	emac->irq_rx_missed = 0;
	emac->irq_napi_schedules = 0;
	emac->poll_napi_schedules = 0;
	emac->napi_polls = 0;
	emac->napi_completes = 0;
	emac->napi_budget_exhaustions = 0;
	emac->napi_rx_work = 0;
	emac->rx_head_dma_owned_samples = 0;
	emac->rx_head_cpu_owned_descs = 0;
	emac->rx_alloc_failures = 0;
	emac->rx_invalid_frames = 0;
	emac->dma_rx_stopped_samples = 0;
	emac->dma_no_rx_desc_samples = 0;
	emac->dma_rx_missed_samples = 0;
	emac->rx_restart_reason_stopped = 0;
	emac->rx_restart_reason_no_desc = 0;
	emac->rx_restart_reason_missed = 0;
	emac->rx_restart_reason_stagnant = 0;
	if (emac->phy_autoneg)
		qtn_emac_select_rescue_port(emac);
	for (i = 0; i < QTN_TOPAZ_EMAC_TX_RING_COUNT; i++) {
		qtn_desc_write(&emac->tx_descs[i].control,
			       i == QTN_TOPAZ_EMAC_TX_RING_COUNT - 1 ?
			       QTN_EMAC_DESC_END_OF_RING : 0);
		qtn_desc_write(&emac->tx_descs[i].bufaddr2, 0);
	}

	for (i = 0; i < QTN_TOPAZ_EMAC_RX_RING_COUNT; i++) {
		ret = qtn_emac_alloc_rx_buffer(emac, i, GFP_KERNEL);
		if (ret)
			goto err_free_rx;
	}

	napi_enable(&emac->napi);
	ret = request_irq(emac->irq, qtn_emac_interrupt, 0, ndev->name, ndev);
	if (ret)
		goto err_disable_napi;
	emac->irq_requested = true;

	ret = qtn_emac_hw_start(emac);
	if (ret)
		goto err_free_irq;

	if (!emac->phy_autoneg || emac->phy_link_valid)
		netif_carrier_on(ndev);
	else
		netif_carrier_off(ndev);
	netif_start_queue(ndev);
	WRITE_ONCE(emac->link_polling, true);
	schedule_delayed_work(&emac->link_work, msecs_to_jiffies(500));
	if (emac->irq_poll_fallback) {
		bool queued = schedule_delayed_work(&emac->irq_poll_work,
			max_t(unsigned long, 1,
			      msecs_to_jiffies(QTN_TOPAZ_EMAC_POLL_INTERVAL_MS)));

		netdev_info(ndev,
			    "OMEMAC poll-fallback enabled interval_ms=%u queued=%u\n",
			    QTN_TOPAZ_EMAC_POLL_INTERVAL_MS, queued);
	}
	netdev_info(ndev,
		    "RAM-rescue direct EMAC active at %u/%s, IRQ %d%s\n",
		    emac->active_speed,
		    emac->active_full_duplex ? "full" : "half", emac->irq,
		    emac->irq_poll_fallback ? " with polling fallback" : "");
	netdev_info(ndev,
		    "DMA rings tx=%pad rx=%pad status=%08x cur_tx=%08x cur_rx=%08x "
		    "rxp=%08x txp=%08x\n",
		    &emac->tx_descs_dma, &emac->rx_descs_dma,
		    qtn_emac_read(emac, QTN_EMAC_DMA_STATUS_IRQ),
		    qtn_emac_read(emac, QTN_EMAC_DMA_CUR_TXDESC_PTR),
		    qtn_emac_read(emac, QTN_EMAC_DMA_CUR_RXDESC_PTR),
		    qtn_emac_read(emac, QTN_TOPAZ_EMAC_RXP_CTRL),
		    qtn_emac_read(emac, QTN_TOPAZ_EMAC_TXP_CTRL));
	netdev_info(ndev,
		    "RXD0 status=%08x control=%08x buf1=%08x next=%08x\n",
		    qtn_desc_read(&emac->rx_descs[0].status),
		    qtn_desc_read(&emac->rx_descs[0].control),
		    qtn_desc_read(&emac->rx_descs[0].bufaddr1),
		    qtn_desc_read(&emac->rx_descs[0].bufaddr2));
	netdev_info(ndev,
		    "RXD_LAST status=%08x control=%08x buf1=%08x buf2=%08x\n",
		    qtn_desc_read(&emac->rx_descs[QTN_TOPAZ_EMAC_RX_RING_COUNT - 1].status),
		    qtn_desc_read(&emac->rx_descs[QTN_TOPAZ_EMAC_RX_RING_COUNT - 1].control),
		    qtn_desc_read(&emac->rx_descs[QTN_TOPAZ_EMAC_RX_RING_COUNT - 1].bufaddr1),
		    qtn_desc_read(&emac->rx_descs[QTN_TOPAZ_EMAC_RX_RING_COUNT - 1].bufaddr2));
	return 0;

err_free_irq:
	/* No worker is scheduled yet. Disable both IRQ and NAPI before final stop. */
	qtn_emac_disable_irqs(emac);
	free_irq(emac->irq, ndev);
	emac->irq_requested = false;
err_disable_napi:
	napi_disable(&emac->napi);
	/* NAPI completion may have unmasked hardware before disable returned. */
	if (qtn_emac_quiesce(emac))
		WRITE_ONCE(emac->dma_unsafe, true);
err_free_rx:
	qtn_emac_free_rx_buffers(emac);
	return ret;
}

static int qtn_emac_stop(struct net_device *ndev)
{
	struct qtn_topaz_emac *emac = netdev_priv(ndev);
	bool cancelled = false;
	int ret;

	WRITE_ONCE(emac->link_polling, false);
	cancel_delayed_work_sync(&emac->link_work);
	netif_stop_queue(ndev);
	if (emac->irq_poll_fallback)
		cancelled = cancel_delayed_work_sync(&emac->irq_poll_work);
	if (emac->irq_poll_fallback)
		netdev_info(ndev,
			    "OMEMAC poll stopped reason=ndo_stop tick=%u cancelled=%u\n",
			    emac->poll_ticks, cancelled);
	netif_carrier_off(ndev);
	qtn_emac_disable_irqs(emac);
	if (emac->irq_requested)
		disable_irq(emac->irq);
	napi_disable(&emac->napi);
	/* Final stop follows NAPI shutdown; no late completion can unmask IRQ. */
	ret = qtn_emac_quiesce(emac);
	if (ret) {
		WRITE_ONCE(emac->dma_unsafe, true);
		netdev_err(ndev, "DMA stop timeout; buffers pinned, reopen refused\n");
	}
	if (emac->irq_requested) {
		free_irq(emac->irq, ndev);
		emac->irq_requested = false;
	}
	qtn_emac_free_tx_buffers(emac);
	qtn_emac_free_rx_buffers(emac);
	return 0;
}

static const struct net_device_ops qtn_emac_netdev_ops = {
	.ndo_open = qtn_emac_open,
	.ndo_stop = qtn_emac_stop,
	.ndo_start_xmit = qtn_emac_start_xmit,
	.ndo_set_mac_address = eth_mac_addr,
	.ndo_validate_addr = eth_validate_addr,
};

static int qtn_emac_alloc_rings(struct qtn_topaz_emac *emac)
{
	size_t tx_size = sizeof(*emac->tx_descs) *
			 QTN_TOPAZ_EMAC_TX_RING_COUNT;
	size_t rx_size = sizeof(*emac->rx_descs) *
			 QTN_TOPAZ_EMAC_RX_RING_COUNT;
	void *rings;

	BUILD_BUG_ON((QTN_TOPAZ_EMAC_TX_RING_COUNT *
		      sizeof(struct qtn_topaz_emac_desc)) != 0x400);
	BUILD_BUG_ON(0x400 + (QTN_TOPAZ_EMAC_RX_RING_COUNT *
		      sizeof(struct qtn_topaz_emac_desc)) >
		     QTN_TOPAZ_EMAC_DESC_SRAM_SIZE);

	/* The OEM direct-AHB driver passes rxdescs_sram=0 and txdescs_sram=0.
	 * Only switch_emac/TQE uses SRAM.  Allocate one contiguous DDR block,
	 * map it once for the Topaz DMA bus, and retain ld.di/st.di CPU access.
	 */
	emac->desc_alloc_size = tx_size + rx_size;
	rings = kzalloc(emac->desc_alloc_size, GFP_KERNEL);
	if (!rings)
		return -ENOMEM;
	if (!IS_ALIGNED((unsigned long)rings, 8)) {
		kfree(rings);
		return -EINVAL;
	}
	emac->desc_alloc = rings;
	emac->desc_alloc_dma = dma_map_single(emac->dev, rings,
					      emac->desc_alloc_size,
					      DMA_BIDIRECTIONAL);
	if (dma_mapping_error(emac->dev, emac->desc_alloc_dma) ||
	    upper_32_bits(emac->desc_alloc_dma)) {
		if (!dma_mapping_error(emac->dev, emac->desc_alloc_dma))
			dma_unmap_single(emac->dev, emac->desc_alloc_dma,
					 emac->desc_alloc_size, DMA_BIDIRECTIONAL);
		kfree(rings);
		emac->desc_alloc = NULL;
		return -EIO;
	}
	emac->tx_descs = rings;
	emac->rx_descs = rings + tx_size;
	qtn_desc_zero(emac->tx_descs, QTN_TOPAZ_EMAC_TX_RING_COUNT);
	qtn_desc_zero(emac->rx_descs, QTN_TOPAZ_EMAC_RX_RING_COUNT);
	emac->tx_descs_dma = emac->desc_alloc_dma;
	emac->rx_descs_dma = emac->desc_alloc_dma + tx_size;
	dma_wmb();
	dev_info(emac->dev,
		 "descriptor DDR ld.di/st.di=%px bus=%pad tx=%zu rx=%zu\n",
		 rings, &emac->tx_descs_dma, tx_size, rx_size);

	return 0;
}

static void qtn_emac_free_rings(struct qtn_topaz_emac *emac)
{
	if (READ_ONCE(emac->dma_unsafe))
		return; /* Quarantine until a hardware reset outside this driver. */

	if (!emac->desc_alloc)
		return;
	dma_unmap_single(emac->dev, emac->desc_alloc_dma,
			 emac->desc_alloc_size, DMA_BIDIRECTIONAL);
	kfree(emac->desc_alloc);
	emac->desc_alloc = NULL;
}

static void qtn_emac_setup(struct net_device *ndev)
{
	ether_setup(ndev);
	ndev->netdev_ops = &qtn_emac_netdev_ops;
	ndev->watchdog_timeo = 5 * HZ;
	ndev->min_mtu = ETH_MIN_MTU;
	ndev->max_mtu = ETH_DATA_LEN;
	ndev->features = 0;
	ndev->hw_features = 0;
	ndev->tx_queue_len = QTN_TOPAZ_EMAC_TX_RING_COUNT - 1;
}

#include "f352_pair.inc"

static const struct of_device_id qtn_emac_of_match[] = {
	{ .compatible = "openmitrastar,eth73-v1-dual-emac" },
	{ }
};
MODULE_DEVICE_TABLE(of, qtn_emac_of_match);

static struct platform_driver qtn_emac_driver = {
	.probe = qtn_emac_probe,
	.remove = qtn_emac_remove,
	.driver = {
		.name = "qtn-topaz-emac-eth73",
		.of_match_table = qtn_emac_of_match,
	},
};
module_platform_driver(qtn_emac_driver);

MODULE_AUTHOR("OpenMitraStar");
MODULE_DESCRIPTION("F352 HGW500 two independent direct EMAC ports, opt-in");
MODULE_LICENSE("GPL");
