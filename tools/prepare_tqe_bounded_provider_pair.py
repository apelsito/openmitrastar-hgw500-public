"""Build source-only CGQ-owned bounded TQE ownership protocol, no device access.

CGQ is the existing provider of TQE. The typed token/ledger API never imports
TQE; first bank admission pins both modules permanently (reboot-only). This
candidate deliberately retains uncertain payloads, never releases or resets.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

from prepare_tqe_bounded_admission_prototype import function

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "outputs/rea/driver5g-ops-20261022-tqe-bounded-local-ownership-source-r4"

API = r'''#ifndef OPENMITRASTAR_TQE_BOUNDED_OWNERSHIP_H
#define OPENMITRASTAR_TQE_BOUNDED_OWNERSHIP_H
#include <linux/types.h>
struct module;
union topaz_tqe_cpuif_ppctl;
/* Private provider-owned token, never a netdev/XMIT return code. */
struct omcgq_bank_token { u32 generation; struct module *owner; };
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
int omcgq_bank_acquire(struct module *owner, struct omcgq_bank_token *token);
int omcgq_bank_token_valid(const struct omcgq_bank_token *token);
int omcgq_bank_cancel(const struct omcgq_bank_token *token);
int omcgq_bank_quarantine(const struct omcgq_bank_token *token,
	const union topaz_tqe_cpuif_ppctl *desc, bool published);
int omcgq_bank_retain(const union topaz_tqe_cpuif_ppctl *desc, bool published);
int omcgq_bank_quarantined(void);
int omcgq_bank_retained(void);
#endif
'''

PROVIDER = r'''/* SOURCE-ONLY provider owns bank state and all retained descriptions.
 * No recovery/release/reset API: first ownership pins both modules until reboot.
 * Entry count is bounded; saturated retention never overwrites previous records.
 * A missing slot is counted explicitly, not reported as complete ownership proof.
 */
#ifdef CONFIG_MODULE_FORCE_UNLOAD
#error "Bounded ownership provider requires forced module unload disabled"
#endif
#if defined(CONFIG_SMP) || defined(CONFIG_PREEMPT) || defined(CONFIG_PREEMPT_VOLUNTARY) || defined(CONFIG_TOPAZ_PCIE_TARGET)
#error "Bounded ownership provider requires UP/PREEMPT_NONE/non-PCIe"
#endif
#define OMCGQ_HELD_MAX 256U
struct omcgq_held_record {
	union topaz_tqe_cpuif_ppctl descriptor;
	u32 references;
	bool published;
};
static struct omcgq_held_record omcgq_held[OMCGQ_HELD_MAX];
static u32 omcgq_held_count;
static u32 omcgq_unrecorded;
static u32 omcgq_generation;
static bool omcgq_reserved;
static bool omcgq_quarantined;
static bool omcgq_retained;
static struct module *omcgq_owner;

int omcgq_bank_quarantined(void) { return READ_ONCE(omcgq_quarantined); }
EXPORT_SYMBOL(omcgq_bank_quarantined);
int omcgq_bank_retained(void) { return READ_ONCE(omcgq_retained); }
EXPORT_SYMBOL(omcgq_bank_retained);

static bool omcgq_token_matches(const struct omcgq_bank_token *token)
{
	return token && omcgq_reserved && token->generation &&
		token->generation == omcgq_generation && token->owner == omcgq_owner;
}

int omcgq_bank_acquire(struct module *owner, struct omcgq_bank_token *token)
{
	unsigned long flags;
	int acquired = 0;
	if (!token || !owner)
		return 0;
	token->generation = 0;
	token->owner = NULL;
	local_irq_save(flags);
	if (omcgq_reserved || omcgq_quarantined ||
	    (omcgq_owner && omcgq_owner != owner) || omcgq_generation == ~0U)
		goto out;
	if (!omcgq_retained) {
		/* Acquire lifetime references BEFORE any skb/HBM mutation or TXSTART.
		 * Never rely on returning early from module_exit to prevent unloading. */
		if (!try_module_get(owner))
			goto out;
		if (!try_module_get(THIS_MODULE)) {
			module_put(owner);
			goto out;
		}
		omcgq_owner = owner;
		omcgq_retained = true;
	}
	omcgq_generation++;
	omcgq_reserved = true;
	token->generation = omcgq_generation;
	token->owner = owner;
	acquired = 1;
out:
	local_irq_restore(flags);
	return acquired;
}
EXPORT_SYMBOL(omcgq_bank_acquire);

int omcgq_bank_token_valid(const struct omcgq_bank_token *token)
{
	unsigned long flags;
	int valid;
	local_irq_save(flags);
	valid = !omcgq_quarantined && omcgq_token_matches(token);
	local_irq_restore(flags);
	return valid;
}
EXPORT_SYMBOL(omcgq_bank_token_valid);

int omcgq_bank_cancel(const struct omcgq_bank_token *token)
{
	unsigned long flags;
	int cancelled = 0;
	local_irq_save(flags);
	if (omcgq_token_matches(token)) {
		omcgq_reserved = false;
		cancelled = 1;
	}
	local_irq_restore(flags);
	return cancelled;
}
EXPORT_SYMBOL(omcgq_bank_cancel);

static int omcgq_record_held(const union topaz_tqe_cpuif_ppctl *desc, bool published)
{
	u32 i;
	if (!desc)
		return 1; /* known prepublication refusal can have no consumed payload */
	for (i = 0; i < omcgq_held_count; i++) {
		if (omcgq_held[i].published == published &&
		    !memcmp(&omcgq_held[i].descriptor, desc, sizeof(*desc))) {
			if (omcgq_held[i].references != ~0U)
				omcgq_held[i].references++;
			else if (omcgq_unrecorded != ~0U)
				omcgq_unrecorded++;
			return 1;
		}
	}
	if (omcgq_held_count == OMCGQ_HELD_MAX) {
		if (omcgq_unrecorded != ~0U)
			omcgq_unrecorded++;
		return 0;
	}
	omcgq_held[omcgq_held_count].descriptor = *desc;
	omcgq_held[omcgq_held_count].references = 1;
	omcgq_held[omcgq_held_count].published = published;
	omcgq_held_count++;
	return 1;
}

int omcgq_bank_quarantine(const struct omcgq_bank_token *token,
	const union topaz_tqe_cpuif_ppctl *desc, bool published)
{
	unsigned long flags;
	int recorded = 0;
	local_irq_save(flags);
	if (omcgq_token_matches(token)) {
		omcgq_quarantined = true;
		omcgq_reserved = false;
		recorded = omcgq_record_held(desc, published);
	}
	local_irq_restore(flags);
	return recorded;
}
EXPORT_SYMBOL(omcgq_bank_quarantine);

int omcgq_bank_retain(const union topaz_tqe_cpuif_ppctl *desc, bool published)
{
	unsigned long flags;
	int recorded = 0;
	local_irq_save(flags);
	if (omcgq_retained && omcgq_quarantined)
		recorded = omcgq_record_held(desc, published);
	local_irq_restore(flags);
	return recorded;
}
EXPORT_SYMBOL(omcgq_bank_retain);

'''

TQE_CORE = r'''/* SOURCE-ONLY bounded TQE hardware polling; CGQ provider owns lifetimes.
 * Token reservation spans HBM work with IRQ restored. Local IRQ exclusion only
 * covers finite MMIO polling/publication. Foreign bank writers remain unknown.
 */
#define OMTQE_READY_READ_MAX 1024U
#define OMTQE_COMPLETE_READ_MAX 1024U
static int omtqe_lhost_quarantined(void) { return omcgq_bank_quarantined(); }

static int omtqe_lhost_reserve(struct omcgq_bank_token *token)
{
	unsigned long flags;
	unsigned int count;
	int ready = 0;
	if (!omcgq_bank_acquire(THIS_MODULE, token))
		return 0;
	local_irq_save(flags);
	for (count = 0; count < OMTQE_READY_READ_MAX; count++) {
		if (!topaz_tqe_cpuif_tx_nready()) {
			ready = 1;
			break;
		}
		cpu_relax();
	}
	if (!ready)
		(void)omcgq_bank_quarantine(token, NULL, false);
	local_irq_restore(flags);
	return ready;
}

static void omtqe_lhost_cancel_reservation(const struct omcgq_bank_token *token)
{
	(void)omcgq_bank_cancel(token);
}

static int omtqe_lhost_submit_reserved(const struct omcgq_bank_token *token,
	const union topaz_tqe_cpuif_ppctl *ppctl)
{
	unsigned long flags;
	unsigned int count;
	int result = OMTQE_OWNERSHIP_UNCERTAIN;
	local_irq_save(flags);
	if (!omcgq_bank_token_valid(token)) {
		(void)omcgq_bank_retain(ppctl, false);
		goto out;
	}
	topaz_tqe_cpuif_tx_start(ppctl);
	wmb();
	for (count = 0; count < OMTQE_COMPLETE_READ_MAX; count++) {
		if (!topaz_tqe_cpuif_tx_nready()) {
			result = (qtn_mproc_sync_mem_read(TOPAZ_TQE_CPUIF_TXSTART(0)) &
				TOPAZ_TQE_CPUIF_TX_START_NOT_SUCCESS) ? NET_XMIT_CN : NET_XMIT_SUCCESS;
			(void)omcgq_bank_cancel(token);
			goto out;
		}
		cpu_relax();
	}
	(void)omcgq_bank_quarantine(token, ppctl, true);
out:
	local_irq_restore(flags);
	return result;
}

static int omtqe_lhost_submit(const union topaz_tqe_cpuif_ppctl *ppctl)
{
	struct omcgq_bank_token token;
	if (!omtqe_lhost_reserve(&token)) {
		(void)omcgq_bank_retain(ppctl, false);
		return OMTQE_OWNERSHIP_REFUSED;
	}
	return omtqe_lhost_submit_reserved(&token, ppctl);
}

'''


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    tqe = (PARENT/'switch_tqe.c').read_text()
    cgq = (PARENT/'topaz_congest_queue.c').read_text()
    begin = tqe.index('/* SOURCE-ONLY bounded local bank ownership.')
    end = tqe.index('int topaz_tqe_xmit(', begin)
    tqe = tqe[:begin] + TQE_CORE + tqe[end:]
    tx = function(tqe, 'int tqe_tx(')
    ntx = tx.replace('\tunsigned int data_len = skb->len;', '\tstruct omcgq_bank_token token;\n\tunsigned int data_len = skb->len;', 1)
    ntx = ntx.replace('omtqe_lhost_reserve()', 'omtqe_lhost_reserve(&token)')
    ntx = ntx.replace('omtqe_lhost_cancel_reservation()', 'omtqe_lhost_cancel_reservation(&token)')
    ntx = ntx.replace('tqe_tx_buf(ppctl, buf_virt, data_len, pool);', 'tqe_tx_buf(&token, ppctl, buf_virt, data_len, pool);')
    tqe = tqe.replace(tx, ntx, 1)
    buf = function(tqe, 'static int tqe_tx_buf(')
    nbuf = buf.replace('static int tqe_tx_buf(union', 'static int tqe_tx_buf(const struct omcgq_bank_token *token, union', 1).replace('omtqe_lhost_submit_reserved(ppctl)', 'omtqe_lhost_submit_reserved(token, ppctl)')
    tqe = tqe.replace(buf, nbuf, 1)
    # Preserve each pending multicast output in the provider ledger before return.
    mc = function(tqe, 'static void __sram_text tqe_push_mcast(')
    nmc = mc.replace('\tif (omtqe_lhost_quarantined())\n\t\treturn; /* counted ref retained; never enter VLAN/HBM/queue cleanup */\n', '', 1)
    marker = '\tppctl.data.buff_ptr_offset = desc->data.buff_ptr_offset;'
    # This early path must precede VLAN/HBM callbacks. Build only a local stack
    # descriptor for the retained ledger; never run egress/drop on quarantine.
    anchor='\t/*\n\t * VLAN egress check -- multicast forwarding'
    early='\tif (omtqe_lhost_quarantined()) {\n\t\ttopaz_tqe_cpuif_ppctl_init(&ppctl, port, &node, 1, tid,\n\t\t\tportal, 1, TOPAZ_HBM_EMAC_TX_DONE_POOL, tqe_free, misc_user);\n\t\tppctl.data.pkt = desc->data.pkt;\n\t\tppctl.data.length = desc->data.length;\n\t\tppctl.data.buff_ptr_offset = desc->data.buff_ptr_offset;\n\t\t(void)omcgq_bank_retain(&ppctl, false);\n\t\treturn;\n\t}\n'
    assert nmc.count(anchor)==1
    nmc=nmc.replace(anchor,early+anchor,1)
    tqe = tqe.replace(mc, nmc, 1)
    process = function(tqe, 'void topaz_tqe_congest_queue_process(')
    nprocess = process.replace('\tif (omtqe_lhost_quarantined())\n\t\treturn; /* pre-owned multicast ref stays retained; no enqueue/free */', '\tif (omtqe_lhost_quarantined()) {\n\t\t(void)omcgq_bank_retain(ppctl, false);\n\t\treturn;\n\t}')
    tqe = tqe.replace(process, nprocess, 1)
    # Both module contexts remain pinned once ownership is first admitted.
    exitbody = function(tqe, 'static void __exit tqe_netdev_exit(')
    newexit = exitbody.replace('\tif (dev == NULL)', '\tif (omcgq_bank_retained())\n\t\treturn; /* lifetime refs prevent normal exit; no hardware teardown */\n\tif (dev == NULL)', 1)
    tqe = tqe.replace(exitbody, newexit, 1)
    cgq = cgq.replace('omtqe_lhost_quarantined()', 'omcgq_bank_quarantined()')
    marker = 'struct topaz_congest_queue *g_congest_queue_ptr = NULL;'
    assert cgq.count(marker)==1
    cgq = cgq.replace(marker, PROVIDER+marker, 1)
    exitbody = function(cgq, 'void topaz_congest_queue_exit(')
    newexit = exitbody.replace('\tif (queue == NULL)', '\tif (omcgq_bank_retained())\n\t\treturn; /* retain container/tasklet context; modules pinned to reboot */\n\tif (queue == NULL)', 1)
    cgq = cgq.replace(exitbody,newexit,1)
    assert 'omtqe_lhost_quarantined' not in cgq
    a.output.mkdir(parents=True,exist_ok=False)
    for name,text in [('switch_tqe.c',tqe),('topaz_congest_queue.c',cgq),('openmitrastar_tqe_bounded_ownership.h',API)]:
        (a.output/name).write_text(text,newline='\n')
    result={'schema':'openmitrastar.tqe-bounded-provider-pair/v1','status':'SOURCE_ONLY_PROVIDER_PAIR_PENDING_FIXTURES_AND_COMPLETE_BUILD','hardware_accessed':False,'firmware_eligible':False,'provider':'topaz_congest_queue','consumer':'switch_tqe','provider_imports_consumer':False,'ledger_capacity':256,'typed_owner_token':True,'first_admission_module_pins':'both consumer and provider; reboot-only; no release API','input_parent_sha256':sha(PARENT/'result.json'),'files':{name:sha(a.output/name)for name in ('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h')},'limits':['Ledger saturation counts unrecorded refs but never overwrites; incomplete catalog remains NO_GO.','No release/recovery/reset qualified; pins and payload retention are reboot-only.','Foreign bank writes, HBM whole-function waits and physical acceptance remain UNRUN.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
