/**
 * Copyright (c) 2015 Quantenna Communications, Inc.
 * All rights reserved.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 **/

#include <linux/module.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/netdevice.h>
#include <linux/etherdevice.h>
#include <linux/if_vlan.h>
#include <linux/of.h>
#include <linux/spinlock.h>
#include <linux/net/bridge/br_public.h>

#include <net80211/if_ethersubr.h>
#include <qtn/topaz_tqe_cpuif.h>
#include <qtn/qtn_skb_cb.h>
#include <qtn/qtn_vlan.h>
#include <qtn_platform_support.h>
#include <qtn/lhost_muc_comm.h>
#include <drivers/ruby/emac_lib.h>
#include "../../qdrv/qdrv_dma_wire.h"

__sram_data uint8_t vlan_enabled;
EXPORT_SYMBOL(vlan_enabled);

__sram_data struct qtn_vlan_dev *vdev_tbl_lhost[VLAN_INTERFACE_MAX];
EXPORT_SYMBOL(vdev_tbl_lhost);

__sram_data struct qtn_vlan_dev *vdev_tbl_bus[VLAN_INTERFACE_MAX];
EXPORT_SYMBOL(vdev_tbl_bus);

__sram_data struct qtn_vlan_dev *vport_tbl_lhost[TOPAZ_TQE_NUM_PORTS];
EXPORT_SYMBOL(vport_tbl_lhost);

__sram_data struct qtn_vlan_dev *vport_tbl_bus[TOPAZ_TQE_NUM_PORTS];
EXPORT_SYMBOL(vport_tbl_bus);

struct qtn_vlan_info qtn_vlan_info;
EXPORT_SYMBOL(qtn_vlan_info);

#ifdef OPENMITRASTAR_QDRV_V89_PAIR
static u32 *om_vdev_tbl_muc;
static u32 *om_vport_tbl_muc;
static struct qtn_vlan_info *om_vlan_info_muc;
static dma_addr_t om_vdev_tbl_dma;
static dma_addr_t om_vport_tbl_dma;
static dma_addr_t om_vlan_info_dma;
static u32 om_vdev_tbl_wire;
static u32 om_vport_tbl_wire;
static u32 om_vlan_info_wire;
static dma_addr_t om_vdev_dma[VLAN_INTERFACE_MAX];
static dma_addr_t om_vintf_dma[VLAN_INTERFACE_MAX];
static bool om_vlan_wire_active;

static void om_vlan_info_sync(void)
{
	if (!om_vlan_wire_active)
		return;
	memcpy(om_vlan_info_muc, &qtn_vlan_info, sizeof(qtn_vlan_info));
	dma_wmb();
}

struct qtn_vlan_dev **switch_vlan_vdev_table_bus(void)
{
	if (om_vlan_wire_active)
		return (struct qtn_vlan_dev **)(unsigned long)om_vdev_tbl_wire;
	return (struct qtn_vlan_dev **)virt_to_bus(vdev_tbl_bus);
}
EXPORT_SYMBOL(switch_vlan_vdev_table_bus);

struct qtn_vlan_dev **switch_vlan_vport_table_bus(void)
{
	if (om_vlan_wire_active)
		return (struct qtn_vlan_dev **)(unsigned long)om_vport_tbl_wire;
	return (struct qtn_vlan_dev **)virt_to_bus(vport_tbl_bus);
}
EXPORT_SYMBOL(switch_vlan_vport_table_bus);

struct qtn_vlan_info *switch_vlan_info_bus(void)
{
	if (om_vlan_wire_active)
		return (struct qtn_vlan_info *)(unsigned long)om_vlan_info_wire;
	return (struct qtn_vlan_info *)virt_to_bus(&qtn_vlan_info);
}
EXPORT_SYMBOL(switch_vlan_info_bus);

static void om_vlan_wire_exit(void)
{
	struct device *dma_dev = qtn_platform_dma_device();

	if (!dma_dev)
		return;
	if (om_vlan_info_muc)
		dma_free_coherent(dma_dev, sizeof(qtn_vlan_info), om_vlan_info_muc,
			om_vlan_info_dma);
	if (om_vport_tbl_muc)
		dma_free_coherent(dma_dev, sizeof(vport_tbl_bus), om_vport_tbl_muc,
			om_vport_tbl_dma);
	if (om_vdev_tbl_muc)
		dma_free_coherent(dma_dev, sizeof(vdev_tbl_bus), om_vdev_tbl_muc,
			om_vdev_tbl_dma);
	om_vlan_info_muc = NULL;
	om_vport_tbl_muc = NULL;
	om_vdev_tbl_muc = NULL;
	om_vlan_wire_active = false;
}

static int om_vlan_wire_init(void)
{
	struct device *dma_dev;

	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))
		return 0;
	dma_dev = qtn_platform_dma_device();
	if (!dma_dev)
		return -ENODEV;
	om_vdev_tbl_muc = dma_alloc_coherent(dma_dev, sizeof(vdev_tbl_bus),
		&om_vdev_tbl_dma, GFP_KERNEL);
	om_vport_tbl_muc = dma_alloc_coherent(dma_dev, sizeof(vport_tbl_bus),
		&om_vport_tbl_dma, GFP_KERNEL);
	om_vlan_info_muc = dma_alloc_coherent(dma_dev, sizeof(qtn_vlan_info),
		&om_vlan_info_dma, GFP_KERNEL);
	if (!om_vdev_tbl_muc || !om_vport_tbl_muc || !om_vlan_info_muc ||
	    qdrv_dma_handle_to_wire(om_vdev_tbl_dma, sizeof(vdev_tbl_bus),
		&om_vdev_tbl_wire) ||
	    qdrv_dma_handle_to_wire(om_vport_tbl_dma, sizeof(vport_tbl_bus),
		&om_vport_tbl_wire) ||
	    qdrv_dma_handle_to_wire(om_vlan_info_dma, sizeof(qtn_vlan_info),
		&om_vlan_info_wire)) {
		om_vlan_wire_exit();
		return -ERANGE;
	}
	memset(om_vdev_tbl_muc, 0, sizeof(vdev_tbl_bus));
	memset(om_vport_tbl_muc, 0, sizeof(vport_tbl_bus));
	memset(om_vlan_info_muc, 0, sizeof(qtn_vlan_info));
	om_vlan_wire_active = true;
	dma_wmb();
	pr_info("OMVLAN stage=wire-shadow-ready vdev=%#x vport=%#x info=%#x\n",
		om_vdev_tbl_wire, om_vport_tbl_wire, om_vlan_info_wire);
	return 0;
}
#else
static inline void om_vlan_info_sync(void) { }

struct qtn_vlan_dev **switch_vlan_vdev_table_bus(void)
{
	return (struct qtn_vlan_dev **)virt_to_bus(vdev_tbl_bus);
}
EXPORT_SYMBOL(switch_vlan_vdev_table_bus);

struct qtn_vlan_dev **switch_vlan_vport_table_bus(void)
{
	return (struct qtn_vlan_dev **)virt_to_bus(vport_tbl_bus);
}
EXPORT_SYMBOL(switch_vlan_vport_table_bus);

struct qtn_vlan_info *switch_vlan_info_bus(void)
{
	return (struct qtn_vlan_info *)virt_to_bus(&qtn_vlan_info);
}
EXPORT_SYMBOL(switch_vlan_info_bus);
static inline int om_vlan_wire_init(void) { return 0; }
static inline void om_vlan_wire_exit(void) { }
#endif

static DEFINE_SPINLOCK(lock);

#define		SWITCH_VLAN_PROC	"topaz_vlan"

static inline void __switch_vlan_add_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	set_bit_a(vdev->u.member_bitmap, vid);
}

static inline void __switch_vlan_del_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	clr_bit_a(vdev->u.member_bitmap, vid);
}

static inline void __switch_vlan_tag_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	set_bit_a(vdev->tag_bitmap, vid);
}

static inline void __switch_vlan_untag_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	clr_bit_a(vdev->tag_bitmap, vid);
}

static inline void
switch_vlan_set_tagrx(struct qtn_vlan_info *vlan_info, uint16_t vlanid, uint8_t tagrx)
{
	uint32_t *tagrx_bitmap = vlan_info->vlan_tagrx_bitmap;
	tagrx = tagrx & QVLAN_TAGRX_BITMASK;

	tagrx_bitmap[qvlan_tagrx_index(vlanid)] &=
		~(QVLAN_TAGRX_BITMASK << qvlan_tagrx_shift(vlanid));

	tagrx_bitmap[qvlan_tagrx_index(vlanid)] |=
		tagrx << (qvlan_tagrx_shift(vlanid));
}

static inline int switch_vlan_manage_tagrx(struct qtn_vlan_dev *vdev,
		uint16_t vlanid, uint8_t tag, uint32_t member_quit)
{
	struct qtn_vlan_dev *other_dev;

	if (vdev->port == TOPAZ_TQE_EMAC_0_PORT)
		other_dev = vport_tbl_lhost[TOPAZ_TQE_EMAC_1_PORT];
	else if (vdev->port == TOPAZ_TQE_EMAC_1_PORT)
		other_dev = vport_tbl_lhost[TOPAZ_TQE_EMAC_0_PORT];
	else if (vdev->port == TOPAZ_TQE_PCIE_PORT || vdev->port == TOPAZ_TQE_DSP_PORT) {
		other_dev = NULL;
	} else {
		return qtn_vlan_get_tagrx(qtn_vlan_info.vlan_tagrx_bitmap, vlanid);
	}

	if (other_dev && !member_quit
			&& qtn_vlan_is_member(other_dev, vlanid)
			&& qtn_vlan_is_tagged_member(other_dev, vlanid) != !!tag) {
		/*
		 * NOTE: All ethernet ports should have the same tag/untag config
		 * for one VLAN ID. This is to avoid confusion for multicast packets
		 * destined for multiple ethernet ports.
		 */
		printk(KERN_INFO"Warning:port %u forced to %s VLAN %u packets\n",
			other_dev->port, tag ? "tag" : "untag", vlanid);

		if (tag)
			__switch_vlan_tag_member(other_dev, vlanid);
		else
			__switch_vlan_untag_member(other_dev, vlanid);
	} else if (member_quit) {
		if (!other_dev || !qtn_vlan_is_member(other_dev, vlanid))
			return QVLAN_TAGRX_UNTOUCH;
		else
			return qtn_vlan_get_tagrx(qtn_vlan_info.vlan_tagrx_bitmap, vlanid);
	}

	return (tag ? QVLAN_TAGRX_TAG : QVLAN_TAGRX_STRIP);
}

static void switch_vlan_add(struct qtn_vlan_dev *vdev, uint16_t vlanid, uint8_t tag)
{
	int tagrx;

	if (!qtn_vlan_is_member(vdev, vlanid)) {
		__switch_vlan_add_member(vdev, vlanid);
	}

	/* update tag bitmap */
	if (tag)
		__switch_vlan_tag_member(vdev, vlanid);
	else
		__switch_vlan_untag_member(vdev, vlanid);

	tagrx = switch_vlan_manage_tagrx(vdev, vlanid, tag, 0);
	switch_vlan_set_tagrx(&qtn_vlan_info, vlanid, tagrx);
	om_vlan_info_sync();
}

static void switch_vlan_del(struct qtn_vlan_dev *vdev, uint16_t vlanid)
{
	int tagrx;
	if (!qtn_vlan_is_member(vdev, vlanid))
		return;

	tagrx = switch_vlan_manage_tagrx(vdev, vlanid, 0, 1);
	switch_vlan_set_tagrx(&qtn_vlan_info, vlanid, tagrx);
	om_vlan_info_sync();

	__switch_vlan_del_member(vdev, vlanid);
	__switch_vlan_untag_member(vdev, vlanid);
}

struct qtn_vlan_dev *switch_alloc_vlan_dev(uint8_t port, uint8_t idx, int ifindex)
{
	struct qtn_vlan_dev *vdev = NULL;
	struct qtn_vlan_user_interface *vintf = NULL;
	struct device *dma_dev;
	dma_addr_t bus_addr = 0, bus_addr2 = 0;
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	u32 vdev_wire = 0;
	u32 vintf_wire = 0;
#endif

	dma_dev = qtn_platform_dma_device();
	if (!dma_dev) {
		pr_err("OMVLAN stage=alloc-failed reason=dma-device-absent port=%u idx=%u\n",
			port, idx);
		return NULL;
	}

	spin_lock_bh(&lock);

	if (vdev_tbl_lhost[idx] != NULL)
		goto out;

	vdev = (struct qtn_vlan_dev *)dma_alloc_coherent(dma_dev,
		sizeof(struct qtn_vlan_dev), &bus_addr, GFP_ATOMIC);
	if (!vdev)
		goto out;

	memset(vdev, 0, sizeof(*vdev));
	vdev->pvid = QVLAN_DEF_PVID;
	vdev->port = port;
	vdev->idx = idx;
	vdev->ifindex = ifindex;

	vintf = (struct qtn_vlan_user_interface *)dma_alloc_coherent(dma_dev,
		sizeof(struct qtn_vlan_user_interface), &bus_addr2, GFP_ATOMIC);
	if (!vintf)
		goto out;

	memset(vintf, 0, sizeof(*vintf));
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	if (om_vlan_wire_active) {
		if (qdrv_dma_handle_to_wire(bus_addr, sizeof(*vdev), &vdev_wire) ||
		    qdrv_dma_handle_to_wire(bus_addr2, sizeof(*vintf), &vintf_wire))
			goto out;
		vdev->bus_addr = vdev_wire;
		vintf->bus_addr = vintf_wire;
		om_vdev_dma[idx] = bus_addr;
		om_vintf_dma[idx] = bus_addr2;
	} else
#endif
	{
		vdev->bus_addr = (unsigned long)bus_addr;
		vintf->bus_addr = bus_addr2;
	}
	vintf->mode = QVLAN_MODE_ACCESS;
	vdev->user_data = (void *)vintf;

	arc_write_uncached_32((uint32_t *)&vdev_tbl_lhost[idx], (uint32_t)vdev);
	arc_write_uncached_32((uint32_t *)&vdev_tbl_bus[idx],
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
		om_vlan_wire_active ? vdev_wire :
#endif
		(uint32_t)bus_addr);
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	if (om_vlan_wire_active)
		WRITE_ONCE(om_vdev_tbl_muc[idx], vdev_wire);
#endif

	if (qtn_vlan_port_indexable(port)) {
		arc_write_uncached_32((uint32_t *)&vport_tbl_lhost[port], (uint32_t)vdev);
		arc_write_uncached_32((uint32_t *)&vport_tbl_bus[port],
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
			om_vlan_wire_active ? vdev_wire :
#endif
			(uint32_t)bus_addr);
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
		if (om_vlan_wire_active)
			WRITE_ONCE(om_vport_tbl_muc[port], vdev_wire);
#endif
	}
	dma_wmb();

	switch_vlan_add(vdev, vdev->pvid, 0);
	pr_info("OMVLAN stage=alloc-pass port=%u idx=%u ifindex=%d vdev_bus=%pad vintf_bus=%pad\n",
		port, idx, ifindex, &bus_addr, &bus_addr2);

	spin_unlock_bh(&lock);
	return vdev;

out:
	if (vintf)
		dma_free_coherent(dma_dev, sizeof(struct qtn_vlan_user_interface),
			vintf, bus_addr2);
	if (vdev)
		dma_free_coherent(dma_dev, sizeof(struct qtn_vlan_dev), vdev, bus_addr);
	spin_unlock_bh(&lock);

	return NULL;
}
EXPORT_SYMBOL(switch_alloc_vlan_dev);

void switch_free_vlan_dev(struct qtn_vlan_dev *vdev)
{
	struct qtn_vlan_user_interface *vintf = (struct qtn_vlan_user_interface *)vdev->user_data;
	struct device *dma_dev = qtn_platform_dma_device();
	dma_addr_t vdev_dma = (dma_addr_t)vdev->bus_addr;
	dma_addr_t vintf_dma = (dma_addr_t)vintf->bus_addr;
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	u8 idx = vdev->idx;
	if (om_vlan_wire_active) {
		vdev_dma = om_vdev_dma[idx];
		vintf_dma = om_vintf_dma[idx];
	}
#endif

	if (WARN_ON_ONCE(!dma_dev))
		return;

	spin_lock_bh(&lock);
	/* vlan_info_tbl[info->idx] = NULL; */
	arc_write_uncached_32((uint32_t *)&vdev_tbl_lhost[vdev->idx], (uint32_t)NULL);
	arc_write_uncached_32((uint32_t *)&vdev_tbl_bus[vdev->idx], (uint32_t)NULL);
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	if (om_vlan_wire_active)
		WRITE_ONCE(om_vdev_tbl_muc[vdev->idx], 0);
#endif

	if (qtn_vlan_port_indexable(vdev->port)) {
		arc_write_uncached_32((uint32_t *)&vport_tbl_lhost[vdev->port], (uint32_t)NULL);
		arc_write_uncached_32((uint32_t *)&vport_tbl_bus[vdev->port], (uint32_t)NULL);
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
		if (om_vlan_wire_active)
			WRITE_ONCE(om_vport_tbl_muc[vdev->port], 0);
#endif
	}
	dma_wmb();
	spin_unlock_bh(&lock);

	dma_free_coherent(dma_dev, sizeof(struct qtn_vlan_dev), vdev, vdev_dma);
	dma_free_coherent(dma_dev, sizeof(struct qtn_vlan_user_interface), vintf, vintf_dma);
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	if (om_vlan_wire_active) {
		om_vdev_dma[idx] = 0;
		om_vintf_dma[idx] = 0;
	}
#endif
}
EXPORT_SYMBOL(switch_free_vlan_dev);

void switch_free_vlan_dev_by_idx(uint8_t idx)
{
	BUG_ON(idx >= VLAN_INTERFACE_MAX);

	switch_free_vlan_dev(vdev_tbl_lhost[idx]);
}
EXPORT_SYMBOL(switch_free_vlan_dev_by_idx);

#ifdef CONFIG_TOPAZ_DBDC_HOST
static enum topaz_tqe_port g_topaz_tqe_pcie_rel_port = TOPAZ_TQE_DUMMY_PORT;
void tqe_register_pcie_rel_port(const enum topaz_tqe_port tqe_port)
{
	g_topaz_tqe_pcie_rel_port = tqe_port;
}
EXPORT_SYMBOL(tqe_register_pcie_rel_port);
#endif

struct qtn_vlan_dev*
switch_vlan_dev_get_by_port(uint8_t port)
{
#ifdef CONFIG_TOPAZ_DBDC_HOST
	uint8_t dev_id = EXTRACT_DEV_ID_FROM_PORT_ID(port);

	port = EXTRACT_PORT_ID_FROM_PORT_ID(port);

	if (port == g_topaz_tqe_pcie_rel_port)
		return vdev_tbl_lhost[QFP_VDEV_IDX(dev_id)];
#endif
	return vport_tbl_lhost[port];
}
EXPORT_SYMBOL(switch_vlan_dev_get_by_port);

struct qtn_vlan_dev*
switch_vlan_dev_get_by_idx(uint8_t idx)
{
	return vdev_tbl_lhost[idx];
}
EXPORT_SYMBOL(switch_vlan_dev_get_by_idx);

typedef void (*_fn_vlan_member)(struct qtn_vlan_dev *vdev,
			uint16_t vid, uint8_t tag);
static int switch_vlan_member_comm(struct qtn_vlan_dev *vdev, uint16_t vid,
		uint8_t tag, _fn_vlan_member handler)
{
	if (vid == QVLAN_VID_ALL) {
		for (vid = 0; vid < QVLAN_VID_MAX; vid++)
			handler(vdev, vid, tag);
	} else if (vid < QVLAN_VID_MAX) {
		handler(vdev, vid, tag);
	} else {
		return -EINVAL;
	}

	return 0;
}

static void _vlan_add_member(struct qtn_vlan_dev *vdev, uint16_t vid, uint8_t tag)
{
	spin_lock_bh(&lock);
	switch_vlan_add(vdev, vid, tag);
	spin_unlock_bh(&lock);
}

int switch_vlan_add_member(struct qtn_vlan_dev *vdev, uint16_t vid, uint8_t tag)
{
	return switch_vlan_member_comm(vdev, vid, tag, _vlan_add_member);
}
EXPORT_SYMBOL(switch_vlan_add_member);

static void _vlan_del_member(struct qtn_vlan_dev *vdev, uint16_t vid, uint8_t arg)
{
	spin_lock_bh(&lock);
	switch_vlan_del(vdev, vid);
	spin_unlock_bh(&lock);
}

int switch_vlan_del_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	return switch_vlan_member_comm(vdev, vid, 0, _vlan_del_member);
}
EXPORT_SYMBOL(switch_vlan_del_member);

static void _vlan_tag_member(struct qtn_vlan_dev *vdev, uint16_t vid, uint8_t arg)
{
	int tagrx;
	spin_lock_bh(&lock);
	if (!qtn_vlan_is_member(vdev, vid))
		goto out;

	__switch_vlan_tag_member(vdev, vid);
	tagrx = switch_vlan_manage_tagrx(vdev, vid, 1, 0);
	switch_vlan_set_tagrx(&qtn_vlan_info, vid, tagrx);
out:
	spin_unlock_bh(&lock);
}

int switch_vlan_tag_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	return switch_vlan_member_comm(vdev, vid, 0, _vlan_tag_member);
}
EXPORT_SYMBOL(switch_vlan_tag_member);

static void _vlan_untag_member(struct qtn_vlan_dev *vdev, uint16_t vid, uint8_t arg)
{
	int tagrx;
	spin_lock_bh(&lock);
	if (!qtn_vlan_is_member(vdev, vid))
		goto out;

	__switch_vlan_untag_member(vdev, vid);
	tagrx = switch_vlan_manage_tagrx(vdev, vid, 0, 0);
	switch_vlan_set_tagrx(&qtn_vlan_info, vid, tagrx);
out:
	spin_unlock_bh(&lock);
}

int switch_vlan_untag_member(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	return switch_vlan_member_comm(vdev, vid, 0, _vlan_untag_member);
}
EXPORT_SYMBOL(switch_vlan_untag_member);

int switch_vlan_set_pvid(struct qtn_vlan_dev *vdev, uint16_t vid)
{
	if (vid >= QVLAN_VID_MAX)
		return -EINVAL;

	spin_lock_bh(&lock);

	switch_vlan_del(vdev, vdev->pvid);
	switch_vlan_add(vdev, vid, 0);

	vdev->pvid = vid;

	spin_unlock_bh(&lock);

	return 0;
}
EXPORT_SYMBOL(switch_vlan_set_pvid);

int switch_vlan_set_mode(struct qtn_vlan_dev *vdev, uint8_t mode)
{
	if (mode >= QVLAN_MODE_MAX)
		return -EINVAL;

	spin_lock_bh(&lock);
	if (qtn_vlan_is_mode(vdev, mode))
		goto out;

	((struct qtn_vlan_user_interface *)vdev->user_data)->mode = mode;
out:
	spin_unlock_bh(&lock);

	return 0;
}
EXPORT_SYMBOL(switch_vlan_set_mode);

static inline void __switch_vlan_clear_dev(struct qtn_vlan_dev *vdev)
{
	memset(&vdev->u, 0, sizeof(vdev->u));
	memset(&vdev->tag_bitmap, 0, sizeof(vdev->tag_bitmap));
	memset(&vdev->ig_pass, 0, sizeof(vdev->ig_pass));
	memset(&vdev->ig_drop, 0, sizeof(vdev->ig_drop));
	memset(&vdev->eg_pass, 0, sizeof(vdev->eg_pass));
	memset(&vdev->eg_drop, 0, sizeof(vdev->eg_drop));
	vdev->pvid = QVLAN_DEF_PVID;
	vdev->flags = 0;
}

void switch_vlan_dyn_enable(struct qtn_vlan_dev *vdev)
{
	spin_lock_bh(&lock);

	__switch_vlan_clear_dev(vdev);
	vdev->flags |= QVLAN_DEV_F_DYNAMIC;

	spin_unlock_bh(&lock);
}
EXPORT_SYMBOL(switch_vlan_dyn_enable);

void switch_vlan_dyn_disable(struct qtn_vlan_dev *vdev)
{
	spin_lock_bh(&lock);

	__switch_vlan_clear_dev(vdev);
	vdev->pvid = QVLAN_DEF_PVID;
	switch_vlan_add(vdev, vdev->pvid, 0);

	spin_unlock_bh(&lock);
}
EXPORT_SYMBOL(switch_vlan_dyn_disable);

int switch_vlan_set_node(struct qtn_vlan_dev *vdev, uint16_t ncidx, uint16_t vlanid)
{
	int ret = 0;

	spin_lock_bh(&lock);

	if (!QVLAN_IS_DYNAMIC(vdev)
			|| ncidx >= QTN_NCIDX_MAX
			|| !qtn_vlan_is_valid(vlanid)
			|| vdev->port != TOPAZ_TQE_WMAC_PORT) {
		ret = -EINVAL;
		goto out;
	}

	vdev->u.node_vlan[ncidx] = vlanid;

out:
	spin_unlock_bh(&lock);
	return ret;
}
EXPORT_SYMBOL(switch_vlan_set_node);

int switch_vlan_clr_node(struct qtn_vlan_dev *vdev, uint16_t ncidx)
{
	int ret = 0;

	spin_lock_bh(&lock);

	if (!QVLAN_IS_DYNAMIC(vdev)
			|| ncidx >= QTN_NCIDX_MAX
			|| vdev->port != TOPAZ_TQE_WMAC_PORT) {
		ret = -EINVAL;
		goto out;
	}

	vdev->u.node_vlan[ncidx] = QVLAN_VID_ALL;

out:
	spin_unlock_bh(&lock);
	return ret;
}
EXPORT_SYMBOL(switch_vlan_clr_node);

static struct sk_buff *switch_vlan_tag_pkt(struct sk_buff *skb, uint16_t vlanid)
{
	struct vlan_ethhdr *veth;
	struct qtn_vlan_pkt old;
	struct qtn_vlan_pkt *new;

	memcpy(&old, qtn_vlan_get_info(skb->data), sizeof(old));

	if (skb_cow_head(skb, VLAN_HLEN) < 0) {
		kfree_skb(skb);
		return NULL;
	}
	veth = (struct vlan_ethhdr *)skb_push(skb, VLAN_HLEN);

	/* Move the mac addresses to the beginning of the new header. */
	memmove(skb->data, skb->data + VLAN_HLEN, 2 * ETH_ALEN);
	veth->h_vlan_proto = __constant_htons(ETH_P_8021Q);
	veth->h_vlan_TCI = htons(vlanid);

	new = qtn_vlan_get_info(skb->data);
	memcpy(new, &old, sizeof(*new));
	new->vlan_info |= QVLAN_TAGGED;

	return skb;
}

static struct sk_buff *switch_vlan_untag_pkt(struct sk_buff *skb, int copy)
{
	struct sk_buff *skb2;
	struct vlan_ethhdr *veth;
	struct qtn_vlan_pkt *pktinfo;

	if (copy) {
		skb2 = skb_copy(skb, GFP_ATOMIC);
		kfree_skb(skb);
	} else {
		skb2 = skb;
	}

	if (!skb2)
		return NULL;

	veth = (struct vlan_ethhdr *)(skb2->data);
	memmove((uint8_t *)veth - QVLAN_PKTCTRL_LEN + VLAN_HLEN,
		(uint8_t *)veth - QVLAN_PKTCTRL_LEN,
		QVLAN_PKTCTRL_LEN + 2 * ETH_ALEN);

	skb_pull(skb2, VLAN_HLEN);

	pktinfo = qtn_vlan_get_info(skb2->data);
	pktinfo->vlan_info &= ~QVLAN_TAGGED;

	return skb2;
}

struct net_device *switch_vlan_find_br(struct net_device *ndev)
{
	struct net_device *brdev = NULL;
	struct net_device *upper;

	rcu_read_lock();
	upper = netdev_master_upper_dev_get_rcu(ndev);
	if (upper && !netif_is_bridge_master(upper))
		upper = netdev_master_upper_dev_get_rcu(upper);
	if (upper && netif_is_bridge_master(upper)) {
		dev_hold(upper);
		brdev = upper;
	}
	rcu_read_unlock();

	return brdev;
}

/*
 * supposed to be called after eth_type_trans and before netif_receive_skb
 * VLAN ingress handling should be done already
 */
struct sk_buff *switch_vlan_to_proto_stack(struct sk_buff *skb, int copy)
{
	struct qtn_vlan_pkt *pkt;
	uint16_t vlan_id;
	struct net_device *brdev;
	int tag_in_frame;
	int should_tag;

	BUG_ON(!skb_mac_header_was_set(skb));

	if (!vlan_enabled)
		return skb;

	if (skb->protocol == __constant_htons(ETH_P_PAE))
		return skb;

	M_FLAG_SET(skb, M_ORIG_OUTSIDE);

	pkt = qtn_vlan_get_info(skb_mac_header(skb));

	tag_in_frame = !!(pkt->vlan_info & QVLAN_TAGGED);
	vlan_id = (pkt->vlan_info & QVLAN_MASK_VID);

	brdev = switch_vlan_find_br(skb->dev);
	if (likely(brdev)) {
		rcu_read_lock();
		should_tag = !!__vlan_find_dev_deep_rcu(brdev,
				__constant_htons(ETH_P_8021Q), vlan_id);
		rcu_read_unlock();
		dev_put(brdev);
	} else {
		return skb;
	}

	if (tag_in_frame != should_tag) {
		skb_push(skb, ETH_HLEN);
		if (should_tag)
			skb = switch_vlan_tag_pkt(skb, vlan_id);
		else
			skb = switch_vlan_untag_pkt(skb, copy);

		if (!skb)
			return NULL;

		skb->protocol = eth_type_trans(skb, skb->dev);
	}

	return skb;
}
EXPORT_SYMBOL(switch_vlan_to_proto_stack);

static struct sk_buff *switch_vlan_add_pktinfo(struct sk_buff *skb)
{
	struct qtn_vlan_pkt *pktinfo;

	if (skb_headroom(skb) < QVLAN_PKTCTRL_LEN) {
		struct sk_buff *skb2;

		skb2 = skb_copy_expand(skb, QVLAN_PKTCTRL_LEN * 2, skb_tailroom(skb), GFP_ATOMIC);
		if (!skb2) {
			kfree_skb(skb);
			return NULL;
		}

		kfree_skb(skb);
		skb = skb2;
	}

	pktinfo = qtn_vlan_get_info(skb->data);
	pktinfo->magic = QVLAN_PKT_MAGIC;

	M_FLAG_SET(skb, M_VLAN_TAGGED);
	return skb;
}

struct sk_buff *switch_vlan_from_proto_stack(struct sk_buff *skb, struct qtn_vlan_dev *outdev, uint16_t ncidx, int copy)
{
	struct qtn_vlan_pkt *pktinfo;
	struct vlan_ethhdr *veth;
	uint16_t vlanid;
	int tag_in_frame;
	int should_tag;

	if (!vlan_enabled)
		return skb;

	if (!M_FLAG_ISSET(skb, M_ORIG_OUTSIDE)) {
		/*
		 * The packet is generated by the device.
		 * A qtn_vlan_pkt structure is needed.
		 */
		skb = switch_vlan_add_pktinfo(skb);
		if (!skb)
			return NULL;

		pktinfo = qtn_vlan_get_info(skb->data);

		if (M_FLAG_ISSET(skb, M_ORIG_BR)) {
			veth = (struct vlan_ethhdr *)(skb->data);

			if (veth->h_vlan_proto == __constant_htons(ETH_P_8021Q)) {
				vlanid = ntohs(veth->h_vlan_TCI) & VLAN_VID_MASK;
				pktinfo->vlan_info = (QVLAN_TAGGED | vlanid);
			} else {
				pktinfo->vlan_info = QVLAN_SKIP_CHECK;
			}
		} else {
			pktinfo->vlan_info = QVLAN_SKIP_CHECK;
		}
	}

	pktinfo = qtn_vlan_get_info(skb->data);
	if (pktinfo->vlan_info & QVLAN_SKIP_CHECK)
		return skb;

	tag_in_frame = !!(pktinfo->vlan_info & QVLAN_TAGGED);
	vlanid = pktinfo->vlan_info & QVLAN_MASK_VID;

	if (QVLAN_IS_DYNAMIC(outdev)) {
		if (outdev->u.node_vlan[ncidx] != vlanid) {
			qtn_vlan_inc_stats(&outdev->eg_drop);
			goto drop_out;
		}
		should_tag = 0;
	} else {
		if (!qtn_vlan_is_member(outdev, vlanid)) {
			qtn_vlan_inc_stats(&outdev->eg_drop);
			goto drop_out;
		}
		should_tag = qtn_vlan_is_tagged_member(outdev, vlanid);
	}

	if (tag_in_frame != should_tag) {
		if (should_tag)
			skb = switch_vlan_tag_pkt(skb, vlanid);
		else
			skb = switch_vlan_untag_pkt(skb, copy);
        }

	return skb;
drop_out:
	kfree_skb(skb);
	return NULL;
}
EXPORT_SYMBOL(switch_vlan_from_proto_stack);

static int switch_vlan_stats_rd(char *page, char **start, off_t offset,
		int count, int *eof, void *data)
{
	char *p = page;
	struct qtn_vlan_dev *vdev;
	struct net_device *ndev;
	int i;

	spin_lock_bh(&lock);

	for (i = 0; i < VLAN_INTERFACE_MAX; i++) {
		vdev = vdev_tbl_lhost[i];
		if (!vdev)
			continue;

		ndev = dev_get_by_index(&init_net, vdev->ifindex);
		if (unlikely(!ndev))
			continue;

		p += sprintf(p, "%s\ti-pass\t\te-pass\t\ti-drop\t\te-drop\t\tmagic-invalid\n", ndev->name);
		p += sprintf(p, "Lhost\t%u\t\t%u\t\t%u\t\t%u\t\t%u\n", vdev->ig_pass.lhost, vdev->eg_pass.lhost,
				vdev->ig_drop.lhost, vdev->eg_drop.lhost, vdev->magic_invalid.lhost);
		p += sprintf(p, "AuC\t%u\t\t%u\t\t%u\t\t%u\t\t%u\n", vdev->ig_pass.auc, vdev->eg_pass.auc,
				vdev->ig_drop.auc, vdev->eg_drop.auc, vdev->magic_invalid.auc);
		p += sprintf(p, "MuC\t%u\t\t%u\t\t%u\t\t%u\t\t%u\n", vdev->ig_pass.muc, vdev->eg_pass.muc,
				vdev->ig_drop.muc, vdev->eg_drop.muc, vdev->magic_invalid.muc);

		dev_put(ndev);
	}

	spin_unlock_bh(&lock);

	*eof = 1;
	return p - page;
}

void switch_vlan_dev_reset(struct qtn_vlan_dev *vdev, uint8_t mode)
{
	uint32_t i;

	spin_lock_bh(&lock);
	for (i = 0; i < QVLAN_VID_MAX; i++) {
		if (qtn_vlan_is_member(vdev, i))
			switch_vlan_del(vdev, i);
	}

	memset(vdev->u.member_bitmap, 0, sizeof(vdev->u.member_bitmap));
	memset(vdev->tag_bitmap, 0, sizeof(vdev->tag_bitmap));
	spin_unlock_bh(&lock);

	switch_vlan_set_pvid(vdev, QVLAN_DEF_PVID);
	switch_vlan_set_mode(vdev, mode);
}
EXPORT_SYMBOL(switch_vlan_dev_reset);

void switch_vlan_reset(void)
{
	uint32_t i;

	for (i = 0; i < VLAN_INTERFACE_MAX; i++) {
		if (vdev_tbl_lhost[i])
			switch_vlan_dev_reset(vdev_tbl_lhost[i], QVLAN_MODE_ACCESS);
	}
}
EXPORT_SYMBOL(switch_vlan_reset);

static int __init switch_vlan_module_init(void)
{
	int ret = om_vlan_wire_init();
	if (ret)
		return ret;
#ifndef OPENMITRASTAR_NO_LEGACY_PROC
	if (!create_proc_read_entry(SWITCH_VLAN_PROC, 0,
			NULL, switch_vlan_stats_rd, 0)) {
		om_vlan_wire_exit();
		return -EEXIST;
	}
#endif

	return 0;
}

static void __exit switch_vlan_module_exit(void)
{
#ifndef OPENMITRASTAR_NO_LEGACY_PROC
	remove_proc_entry(SWITCH_VLAN_PROC, 0);
#endif
	om_vlan_wire_exit();
}

module_init(switch_vlan_module_init);
module_exit(switch_vlan_module_exit);

MODULE_DESCRIPTION("VLAN control panel");
MODULE_AUTHOR("Quantenna");
MODULE_LICENSE("GPL");
