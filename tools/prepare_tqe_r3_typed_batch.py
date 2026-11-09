"""Finite typed multicast ownership admission without arbitrary ledger growth.

One multicast payload is one retained owner, with bounded expected output refs.
Batch pins/catalog slot are reserved before ec mutation; typed callback context
keeps nested normal writers from borrowing batch ownership. No release/reset.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_tqe_bounded_admission_prototype import function

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-source-r2'

API=r'''
struct omcgq_batch_token { u32 generation; struct module *owner; };
int omcgq_batch_admit(struct module *owner, const union topaz_tqe_cpuif_ppctl *payload,
	u32 expected, struct omcgq_batch_token *batch);
int omcgq_batch_valid(const struct omcgq_batch_token *batch);
int omcgq_batch_acquire(const struct omcgq_batch_token *batch,
	struct omcgq_bank_token *token);
int omcgq_batch_complete(const struct omcgq_batch_token *batch, bool published);
int omcgq_batch_finish(const struct omcgq_batch_token *batch);
'''

PROVIDER=r'''/* Typed batch reserves one PAYLOAD owner, not one descriptor per output.
 * Source fanout is bounded to128WMAC nodes plus7otherports; expectedrefs stay
 * attached to this one owner across partial submission or queue retention.
 */
#define OMCGQ_BATCH_FANOUT_MAX 135U
struct omcgq_batch_state {
	struct omcgq_batch_token token;
	u32 expected;
	u32 completed;
	u32 published;
	u32 ledger_slot;
	bool active;
};
static struct omcgq_batch_state omcgq_batch;
static u32 omcgq_batch_generation;

static bool omcgq_batch_matches(const struct omcgq_batch_token *batch)
{
	return batch && omcgq_batch.active && batch->generation &&
		batch->generation == omcgq_batch.token.generation &&
		batch->owner == omcgq_batch.token.owner;
}

int omcgq_batch_admit(struct module *owner, const union topaz_tqe_cpuif_ppctl *payload,
	u32 expected, struct omcgq_batch_token *batch)
{
	unsigned long flags;
	int accepted = 0;
	if (!owner || !payload || !batch || !expected || expected > OMCGQ_BATCH_FANOUT_MAX)
		return 0;
	batch->generation = 0;
	batch->owner = NULL;
	local_irq_save(flags);
	if (omcgq_batch.active || omcgq_reserved || omcgq_quarantined ||
	    omcgq_held_count == OMCGQ_HELD_MAX || omcgq_batch_generation == ~0U ||
	    (omcgq_owner && omcgq_owner != owner))
		goto out;
	/* Pin before caller changes the payload's ec/freecount ownership. */
	if (!omcgq_retained) {
		if (!try_module_get(owner))
			goto out;
		if (!try_module_get(THIS_MODULE)) {
			module_put(owner);
			goto out;
		}
		omcgq_owner = owner;
		omcgq_retained = true;
	}
	omcgq_batch_generation++;
	omcgq_batch.token.generation = omcgq_batch_generation;
	omcgq_batch.token.owner = owner;
	omcgq_batch.expected = expected;
	omcgq_batch.completed = 0;
	omcgq_batch.published = 0;
	omcgq_batch.ledger_slot = omcgq_held_count;
	omcgq_batch.active = true;
	/* A fixed slot is reserved now; timeout will never need new capacity. */
	omcgq_held[omcgq_held_count].descriptor = *payload;
	omcgq_held[omcgq_held_count].references = expected;
	omcgq_held[omcgq_held_count].published = false;
	omcgq_held_count++;
	*batch = omcgq_batch.token;
	accepted = 1;
out:
	local_irq_restore(flags);
	return accepted;
}
EXPORT_SYMBOL(omcgq_batch_admit);

int omcgq_batch_valid(const struct omcgq_batch_token *batch)
{
	unsigned long flags;
	int valid;
	local_irq_save(flags);
	valid = omcgq_batch_matches(batch);
	local_irq_restore(flags);
	return valid;
}
EXPORT_SYMBOL(omcgq_batch_valid);

int omcgq_batch_acquire(const struct omcgq_batch_token *batch,
	struct omcgq_bank_token *token)
{
	unsigned long flags;
	int acquired = 0;
	if (!token)
		return 0;
	token->generation = 0;
	token->owner = NULL;
	local_irq_save(flags);
	if (!omcgq_batch_matches(batch) || omcgq_batch.completed >= omcgq_batch.expected ||
	    omcgq_reserved || omcgq_quarantined ||
	    omcgq_generation == ~0U)
		goto out;
	omcgq_generation++;
	omcgq_reserved = true;
	token->generation = omcgq_generation;
	token->owner = batch->owner;
	acquired = 1;
out:
	local_irq_restore(flags);
	return acquired;
}
EXPORT_SYMBOL(omcgq_batch_acquire);

int omcgq_batch_complete(const struct omcgq_batch_token *batch, bool published)
{
	unsigned long flags;
	int accepted = 0;
	local_irq_save(flags);
	if (omcgq_batch_matches(batch) && omcgq_batch.completed < omcgq_batch.expected) {
		omcgq_batch.completed++;
		if (published)
			omcgq_batch.published++;
		else
			omcgq_quarantined = true; /* Never recycle owned refs after refusal. */
		omcgq_held[omcgq_batch.ledger_slot].published |= published;
		accepted = 1;
	}
	local_irq_restore(flags);
	return accepted;
}
EXPORT_SYMBOL(omcgq_batch_complete);

int omcgq_batch_finish(const struct omcgq_batch_token *batch)
{
	unsigned long flags;
	int accepted = 0;
	local_irq_save(flags);
	if (omcgq_batch_matches(batch)) {
		/* Successful batch transfers all expected refs; recycle only its unused
		 * catalog slot. On quarantine retain the one owner with ALLexpectedrefs. */
		if (!omcgq_quarantined && !omcgq_reserved &&
		    omcgq_batch.completed == omcgq_batch.expected &&
		    omcgq_batch.published == omcgq_batch.expected) {
			memset(&omcgq_held[omcgq_batch.ledger_slot], 0, sizeof(omcgq_held[0]));
			omcgq_held_count--;
		} else {
			/* Missing callback/unfinished bank must remain a held owner and
			 * refuse all later writers, even when no poll timeout was observed. */
			omcgq_quarantined = true;
		}
		omcgq_batch.active = false;
		accepted = 1;
	}
	local_irq_restore(flags);
	return accepted;
}
EXPORT_SYMBOL(omcgq_batch_finish);

'''

WRAPPER=r'''/* Local callback context: queue and batch token never enter firmware ABI. */
struct omtqe_mcast_context {
	void *queue;
	struct omcgq_batch_token batch;
};

static void omtqe_push_mcast_batch(const void *token1, void *token2,
	uint8_t port, uint8_t node, uint8_t tid)
{
	const union topaz_tqe_cpuif_descr *desc = token1;
	struct omtqe_mcast_context *context = token2;
	union topaz_tqe_cpuif_ppctl ppctl;
	struct omcgq_bank_token token;
	int result = OMTQE_OWNERSHIP_REFUSED;
	if (!context || !omcgq_batch_valid(&context->batch))
		return;
	topaz_tqe_cpuif_ppctl_init(&ppctl, port, &node, 1, tid,
		1, 1, TOPAZ_HBM_EMAC_TX_DONE_POOL, context->queue ? 0 : 1, 0);
	ppctl.data.pkt = desc->data.pkt;
	ppctl.data.length = desc->data.length;
	ppctl.data.buff_ptr_offset = desc->data.buff_ptr_offset;
	if (!omtqe_lhost_quarantined() && vlan_enabled && TOPAZ_TQE_PORT_IS_EMAC(port)) {
		struct qtn_vlan_dev *vdev = vport_tbl_lhost[port];
		if (!qtn_vlan_egress(vdev, 0, bus_to_virt((uintptr_t)desc->data.pkt))) {
			/* Retain this batch owner instead of invoking the legacy unbounded
			 * HBM final-ref cleanup. Refused policy is explicit, never forwarded. */
			if (omcgq_batch_acquire(&context->batch, &token))
				(void)omcgq_bank_quarantine(&token, NULL, false);
			(void)omcgq_batch_complete(&context->batch, false);
			return;
		}
	}
	if (!omtqe_lhost_quarantined() && omcgq_batch_acquire(&context->batch, &token)) {
		/* Batch-owned admission: bounded poll BEFORE publishing, no normal
		 * callback can borrow this token or consume another ledger slot. */
		unsigned long flags;
		unsigned int count;
		int ready = 0;
		local_irq_save(flags);
		for (count = 0; count < OMTQE_READY_READ_MAX; count++) {
			if (!topaz_tqe_cpuif_tx_nready()) { ready = 1; break; }
			cpu_relax();
		}
		if (!ready)
			(void)omcgq_bank_quarantine(&token, NULL, false);
		local_irq_restore(flags);
		if (ready)
			result = omtqe_lhost_submit_reserved(&token, &ppctl);
	}
	/* Existing normal queues cannot encode this batch token. The first source
	 * variant intentionally avoids requeue/retry and retains on any refusal. */
	if (result != NET_XMIT_SUCCESS && !omtqe_lhost_quarantined()) {
		if (omcgq_batch_acquire(&context->batch, &token))
			(void)omcgq_bank_quarantine(&token, NULL, false);
	}
	(void)omcgq_batch_complete(&context->batch, result == NET_XMIT_SUCCESS);
}

'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 cgq=(PARENT/'topaz_congest_queue.c').read_text();marker='int omcgq_bank_acquire(';start=cgq.index(marker);body=function(cgq,marker);updated=body.replace('if (omcgq_reserved || omcgq_quarantined ||','if (omcgq_batch.active || omcgq_reserved || omcgq_quarantined ||',1)
 # Forwardbatch-state declaration must precede normal bankacquire.
 state=PROVIDER[:PROVIDER.index('static bool omcgq_batch_matches')];logic=PROVIDER[PROVIDER.index('static bool omcgq_batch_matches'):]
 cgq=cgq[:start]+state+cgq[start:];cgq=cgq.replace(body,updated,1)
 marker='struct topaz_congest_queue *g_congest_queue_ptr = NULL;';cgq=cgq.replace(marker,logic+marker,1)
 # Duringtypedbatch quarantine, use only pre-reserved payloadowner record.
 old=function(cgq,'int omcgq_bank_quarantine(');new=old.replace('recorded = omcgq_record_held(desc, published);','recorded = omcgq_batch.active ? 1 : omcgq_record_held(desc, published);\n\t\tif (omcgq_batch.active)\n\t\t\tomcgq_held[omcgq_batch.ledger_slot].published |= published;',1);cgq=cgq.replace(old,new,1)
 tqe=(PARENT/'switch_tqe.c').read_text();old=function(tqe,'static uint32_t __sram_text tqe_push_mc_ports(');new=old.replace('\tuint32_t push_count;','\tstruct omtqe_mcast_context context;\n\tunion topaz_tqe_cpuif_ppctl payload_owner;\n\tuint32_t push_count;',1)
 marker='\ttqe_buf_set_refcounts((uint8_t *)buf_virt_rx + offset, push_count, 0);';prep='\tmemset(&payload_owner, 0, sizeof(payload_owner));\n\tpayload_owner.data.pkt = desc->data.pkt;\n\tpayload_owner.data.length = desc->data.length;\n\tpayload_owner.data.buff_ptr_offset = desc->data.buff_ptr_offset;\n\tcontext.queue = queue;\n\tif (!omcgq_batch_admit(THIS_MODULE, &payload_owner, push_count, &context.batch))\n\t\treturn 0;\n';assert old.count(marker)==1;new=new.replace(marker,prep+marker,1)
 new=new.replace('topaz_fwt_sw_mcast_do_per_node(tqe_push_mcast,','topaz_fwt_sw_mcast_do_per_node(omtqe_push_mcast_batch,',1).replace('&mcast_ent, desc, queue, in_node, port, tid);','&mcast_ent, desc, &context, in_node, port, tid);',1).replace('tqe_push_mcast(desc, NULL, port, 0, 0);','omtqe_push_mcast_batch(desc, &context, port, 0, 0);',1)
 new=new.replace('\treturn push_count;','\t(void)omcgq_batch_finish(&context.batch);\n\treturn push_count;',1);tqe=tqe.replace(old,WRAPPER+new,1)
 api=(PARENT/'openmitrastar_tqe_bounded_ownership.h').read_text().replace('#endif',API+'#endif',1)
 for name,text in(('switch_tqe.c',tqe),('topaz_congest_queue.c',cgq),('openmitrastar_tqe_bounded_ownership.h',api)):(a.output/name).write_text(text,newline='\n')
 result={'schema':'openmitrastar.tqe-r3-typed-batch/v1','status':'SOURCE_ONLY_TYPED_BATCH_FINITE_OWNERSHIP_PENDING_FIXTURES','hardware_accessed':False,'firmware_eligible':False,'ledger_capacity_unchanged':256,'one_catalog_record_per_multicast_payload':True,'fanout_limit':135,'batch_owner_pinned_before_ec':True,'typed_context_before_reference_mutation':True,'parent_sha256':sha(PARENT/'result.json'),'files':{n:sha(a.output/n)for n in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h')},'explicit_behavior_changes':['Typedmulticastfirstvariantbypassesoriginalcongestionrequeue; anyunsuccessfuloutputquarantinesbatch andretainsoneowner.','VLANdeniedoutputneverforwarded; retainsonepre-recordedowner insteadunboundedHBMdropcleanup.'],'limits':['NormalCPUlocalwritersblockduringbatch viaowner-token;foreignfirmware bankwritersstillunknown.','Noautomaticrelease/reset/recovery; firstpinsreboot-only.','Typedbatchfixture/completepair/delta andVLANpolicyclosure pending.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
