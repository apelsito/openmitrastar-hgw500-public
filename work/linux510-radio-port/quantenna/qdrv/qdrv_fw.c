/**
  Copyright (c) 2015 Quantenna Communications Inc
  All Rights Reserved

  This program is free software; you can redistribute it and/or
  modify it under the terms of the GNU General Public License
  as published by the Free Software Foundation; either version 2
  of the License, or (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

 **/

#ifndef AUTOCONF_INCLUDED
#include <linux/config.h>
#endif
#include <linux/version.h>

#include <linux/device.h>
#include <linux/dma-mapping.h>
#include <linux/firmware.h>
#include <linux/elf.h>
#include <linux/errno.h>
#include <asm/io.h>
#include <asm/hardware.h>
#include <common/ruby_mem.h>
#include "qdrv_debug.h"
#include "qdrv_fw.h"
#include "qdrv_bld.h"

#define QDRV_FWINFO_VADDR	0xffff0000U
#define QDRV_FWINFO_TYPE_RELEASE	1U

struct qdrv_fwinfo {
	char magic[8];
	__le32 type;
	__le32 version;
} __packed;

/*
 * Releases newer than the public .62.1 tree add a synthetic PT_LOAD segment
 * at 0xffff0000.  It is metadata, not a load address.  Treating it as a real
 * AuC/MuC destination reaches the out-of-range address conversion path.  The
 * OEM .89 loader skips this segment and rejects a version mismatch before any
 * firmware payload is installed; preserve that fail-closed property here.
 */
static int qdrv_fw_check_info(const Elf32_Phdr *phdr, const char *data)
{
	const struct qdrv_fwinfo *info;
	u32 type;
	u32 version;

	if (phdr->p_vaddr != QDRV_FWINFO_VADDR)
		return 0;

	if (phdr->p_filesz < sizeof(*info)) {
		printk(KERN_ERR "qdrv: truncated FWINFO segment (%u bytes)\n",
			phdr->p_filesz);
		return -EINVAL;
	}

	info = (const struct qdrv_fwinfo *)data;
	if (memcmp(info->magic, "FWINFO", 6) != 0) {
		printk(KERN_ERR "qdrv: invalid FWINFO magic\n");
		return -EINVAL;
	}

	type = le32_to_cpu(info->type);
	version = le32_to_cpu(info->version);
	if (type != QDRV_FWINFO_TYPE_RELEASE) {
		printk(KERN_ERR "qdrv: unsupported FWINFO type 0x%x\n", type);
		return -EINVAL;
	}
	if (version != QDRV_BLD_VER) {
		printk(KERN_ERR
			"qdrv: firmware version 0x%x does not match host 0x%x\n",
			version, QDRV_BLD_VER);
		return -EPROTO;
	}

	return 1;
}

static int
auc_is_ccm_addr(unsigned long addr)
{
	return
		__in_mem_range(addr, TOPAZ_AUC_IMEM_ADDR, TOPAZ_AUC_IMEM_SIZE) ||
		__in_mem_range(addr, TOPAZ_AUC_DMEM_ADDR, TOPAZ_AUC_DMEM_SIZE);
}

static void
auc_write_ccm_uint8(void *dst, uint8_t val)
{
	unsigned long addr = (unsigned long)dst;
	unsigned long addr_align = addr & ~0x3;
	unsigned long val_shift = (addr & 0x3) * BITS_PER_BYTE;
	unsigned mem_val = readl(addr_align);

	mem_val = mem_val & ~(0xFF << val_shift);
	mem_val = mem_val | (val << val_shift);

	writel(mem_val, addr_align);
}

static void auc_memzero_ccm(void *dst, unsigned long size)
{
	char *dst_c = (char *)dst;

	while (size > 0) {
		auc_write_ccm_uint8(dst_c, 0);
		--size;
		++dst_c;
	}
}

static void auc_memcpy_ccm(void *dst, const void *src, unsigned long size)
{
	char *dst_c = (char *)dst;
	const char *src_c = (const char *)src;

	while (size > 0) {
		auc_write_ccm_uint8(dst_c, readb(src_c));
		--size;
		++dst_c;
		++src_c;
	}
}

void qdrv_fw_auc_memzero(void *dst, unsigned long size, unsigned long dst_phys_addr)
{
	if (auc_is_ccm_addr(dst_phys_addr)) {
		auc_memzero_ccm(dst, size);
	} else {
		memset(dst, 0, size);
	}
}

static
void qdrv_fw_auc_memcpy(void *dst, const void *src, unsigned long size, unsigned long dst_phys_addr)
{
	if (auc_is_ccm_addr(dst_phys_addr)) {
		auc_memcpy_ccm(dst, src, size);
	} else {
		memcpy(dst, src, size);
	}
}

unsigned long
qdrv_fw_auc_to_host_addr(unsigned long auc_addr)
{
	void *ret = bus_to_virt(auc_addr);
	if (RUBY_BAD_VIRT_ADDR == ret) {
		panic("Converting out of range AuC address 0x%lx to host address\n", auc_addr);
	}
	return virt_to_phys(ret);
}

static unsigned long
qdrv_fw_muc_to_host_addr(unsigned long muc_addr)
{
	void *ret = (void*)muc_to_lhost(muc_addr);
	if (RUBY_BAD_VIRT_ADDR == ret) {
		panic("Converting out of range MuC address 0x%lx to host address\n", muc_addr);
	}
	return virt_to_phys(ret);
}

static unsigned long
qdrv_fw_dsp_to_host_addr(unsigned long dsp_addr)
{
	void *ret = bus_to_virt(dsp_addr);
	if (RUBY_BAD_VIRT_ADDR == ret) {
		panic("Converting out of range DSP address 0x%lx to host address\n", dsp_addr);
	}
	return virt_to_phys(ret);
}

enum qdrv_fw_cpu {
	qdrv_fw_muc,
	qdrv_fw_auc,
	qdrv_fw_dsp
};

static void qdrv_fw_install_segment(const Elf32_Phdr *phdr,
		const char *data,
		enum qdrv_fw_cpu cpu)
{
	uint8_t *vaddr;
	unsigned long paddr;

	if (cpu == qdrv_fw_dsp) {
		/* Skip blocks for DSP X/Y memory */
		if ((phdr->p_vaddr >= RUBY_DSP_XYMEM_BEGIN) &&
				(phdr->p_vaddr <= RUBY_DSP_XYMEM_END)) {
			return;
		}
		paddr = phdr->p_vaddr;
	} else {
		paddr = phdr->p_paddr;
		if (!paddr) {
			paddr = phdr->p_vaddr;
		}
	}

	switch (cpu) {
	case qdrv_fw_muc:
		paddr = qdrv_fw_muc_to_host_addr(paddr);
		break;
	case qdrv_fw_auc:
		paddr = qdrv_fw_auc_to_host_addr(paddr);
		break;
	case qdrv_fw_dsp:
		paddr = qdrv_fw_dsp_to_host_addr(paddr);
		break;
	default:
		BUG();
		break;
	}

	DBGPRINTF(DBG_LL_INFO, QDRV_LF_TRACE, "ELF header p_vaddr=%p p_paddr=%p, "
				 "remapping to 0x%lx filesz %d memsz %d\n",
			(void*)phdr->p_vaddr, (void*)phdr->p_paddr,
			paddr, phdr->p_filesz, phdr->p_memsz);

	vaddr = ioremap_nocache(paddr, phdr->p_memsz);

	/* Copy data and clear BSS */
	if (cpu == qdrv_fw_auc) {
		qdrv_fw_auc_memcpy(vaddr, data, phdr->p_filesz, paddr);
		qdrv_fw_auc_memzero(vaddr + phdr->p_filesz, phdr->p_memsz - phdr->p_filesz, paddr);
	} else {
		memcpy(vaddr, data, phdr->p_filesz);
		memset(vaddr + phdr->p_filesz, 0, phdr->p_memsz - phdr->p_filesz);
	}

	iounmap(vaddr);
}

static int qdrv_fw_install(char *data, uint32_t *start_addr, enum qdrv_fw_cpu cpu)
{
	Elf32_Ehdr *ehdr;
	Elf32_Phdr *phdr;
	char *payload;
	int info_ret;
	int i;

	DBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\n");

	ehdr = (Elf32_Ehdr *) data;
	data += sizeof(Elf32_Ehdr);

	phdr = (Elf32_Phdr *) data;
	data += ehdr->e_phnum * sizeof(Elf32_Phdr);
	payload = data;

	*start_addr = (uint32_t)ehdr->e_entry;

	/* Validate every metadata segment before installing any payload. */
	for (i = 0; i < ehdr->e_phnum; i++) {
		info_ret = qdrv_fw_check_info(&phdr[i], payload);
		if (info_ret < 0)
			return info_ret;
		payload += phdr[i].p_filesz;
	}

	for (i = 0; i < ehdr->e_phnum; i++, phdr++) {
		info_ret = qdrv_fw_check_info(phdr, data);
		if (info_ret == 0)
			qdrv_fw_install_segment(phdr, data, cpu);
		data += phdr->p_filesz;
	}

	DBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "<--Exit\n");

	return i;
}

static const char *qdrv_fw_cpu_str[] = {
		[qdrv_fw_muc] = "MuC",
		[qdrv_fw_auc] = "AuC",
		[qdrv_fw_dsp] = "DSP"
};

static
int qdrv_fw_load(struct device *dev,
		char *firmware,
		uint32_t *start_addr,
		enum qdrv_fw_cpu cpu)
{
	const struct firmware *fw;
	int ret;

	DBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\n");

	if (request_firmware(&fw, firmware, dev) < 0) {
		DBGPRINTF_E("Failed to load %s firmware \"%s\"\n",
				qdrv_fw_cpu_str[cpu], firmware);
		DBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "<--Exit\n");
		return -1;
	}

	DBGPRINTF(DBG_LL_INFO, QDRV_LF_TRACE, "Firmware size is %d\n", fw->size);

	ret = qdrv_fw_install((char *)fw->data, start_addr, cpu);
	if (ret <= 0) {
		DBGPRINTF_E("Failed to install %s firmware \"%s\"\n",
				qdrv_fw_cpu_str[cpu], firmware);
	}

	release_firmware(fw);

	DBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "<--Exit\n");

	return ret;
}

int qdrv_fw_load_muc(struct device *dev,
		char *firmware,
		uint32_t *start_addr)
{
	return qdrv_fw_load(dev, firmware, start_addr, qdrv_fw_muc);
}

int qdrv_fw_load_auc(struct device *dev,
		char *firmware,
		uint32_t *start_addr)
{
	return qdrv_fw_load(dev, firmware, start_addr, qdrv_fw_auc);
}

int qdrv_fw_load_dsp(struct device *dev,
		char *firmware,
		uint32_t *start_addr)
{
	return qdrv_fw_load(dev, firmware, start_addr, qdrv_fw_dsp);
}
