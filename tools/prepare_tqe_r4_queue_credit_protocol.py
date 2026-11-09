"""SOURCE-only typed queue credit/ownership protocol before multicast ec.

No firmware or device access. Credits are finite (existing total queue limit),
reserved before refs and converted into queued entries only after confirmed CN.
This protocol core does not silently change the original queue-element layout;
full source consumers need a separately qualified header/module closure.
"""
import argparse
import hashlib
import json
from pathlib import Path

CORE=r'''/* Pending protocol core: not an installed/runtime module contract.
 * Source-only credit ledger; no HBM operation or publication occurs here.
 */
#define OMQ_TOTAL_QUEUE_MAX 2048U
struct omq_credit_token { u32 generation; struct module *owner; u32 reserved; };
struct omq_credit_state {
	u32 generation;
	u32 outstanding;
	u32 reserved;
	u32 queued;
	struct module *owner;
	bool active;
	bool quarantined;
};
static struct omq_credit_state omq_state;

static bool omq_token_matches(const struct omq_credit_token *token)
{
	return token && omq_state.active && token->generation &&
		token->generation == omq_state.generation && token->owner == omq_state.owner;
}

static int omq_reserve(struct module *owner, u32 expected, u32 queue_used,
	struct omq_credit_token *token)
{
	unsigned long flags;
	int result = 0;
	if (!owner || !token || !expected || expected > OMQ_TOTAL_QUEUE_MAX)
		return 0;
	token->generation = 0;
	token->owner = NULL;
	token->reserved = 0;
	local_irq_save(flags);
	if (omq_state.active || omq_state.quarantined || queue_used > OMQ_TOTAL_QUEUE_MAX ||
	    expected > OMQ_TOTAL_QUEUE_MAX - queue_used || omq_state.generation == ~0U)
		goto out;
	omq_state.generation++;
	omq_state.owner = owner;
	omq_state.outstanding = expected;
	omq_state.reserved = expected;
	omq_state.queued = 0;
	omq_state.active = true;
	token->generation = omq_state.generation;
	token->owner = owner;
	token->reserved = expected;
	result = 1;
out:
	local_irq_restore(flags);
	return result;
}

/* Convert a reserved credit only for a known prepublication ownership or
 * confirmed NOTSUCCESS; never for a hardware-published uncertain descriptor. */
static int omq_enqueue_credit(const struct omq_credit_token *token, bool published_unknown)
{
	unsigned long flags;
	int result = 0;
	local_irq_save(flags);
	if (!omq_token_matches(token) || !omq_state.reserved || omq_state.quarantined)
		goto out;
	if (published_unknown) {
		omq_state.quarantined = true;
		goto out;
	}
	omq_state.reserved--;
	omq_state.queued++;
	result = 1;
out:
	local_irq_restore(flags);
	return result;
}

/* Completed transmission releases one original multicast ref ownership from
 * software tracking; actual HBM completion/refcount remains hardware-owned. */
static int omq_accept(const struct omq_credit_token *token, bool from_queue)
{
	unsigned long flags;
	int result = 0;
	local_irq_save(flags);
	if (!omq_token_matches(token) || !omq_state.outstanding || omq_state.quarantined)
		goto out;
	if (from_queue) {
		if (!omq_state.queued)
			goto out;
		omq_state.queued--;
	} else {
		if (!omq_state.reserved)
			goto out;
		omq_state.reserved--;
	}
	omq_state.outstanding--;
	if (!omq_state.outstanding)
		omq_state.active = false;
	result = 1;
out:
	local_irq_restore(flags);
	return result;
}

static int omq_retain_unknown(const struct omq_credit_token *token)
{
	unsigned long flags;
	int result = 0;
	local_irq_save(flags);
	if (omq_token_matches(token)) {
		omq_state.quarantined = true;
		result = 1;
	}
	local_irq_restore(flags);
	return result;
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);(a.output/'typed-queue-credit-core.h').write_text(CORE,newline='\n');result={'schema':'openmitrastar.tqe-r4-queue-credit-core/v1','status':'SOURCE_ONLY_FINITE_CREDIT_PROTOCOL_NOT_DRIVER_INTEGRATED','hardware_accessed':False,'firmware_eligible':False,'existing_global_queue_limit':2048,'reservation_pre_ec':True,'confirmed_CN_queueable':True,'published_unknown_never_enqueue':True,'source_sha256':hashlib.sha256(CORE.encode()).hexdigest(),'gates':['CopiedtypedtokenmustpersistinCGQringentry; stackcontextcannotpersistforasyncretry.','Providerbatchvalid must remainuntilqueuedoutstanding==0, notbatchloopend.','Allqueueelement/headerusersfullARCclosure requirediflayoutchanges.','Queueclear/drop requiresboundedHBMcleanuporquarantine, notunchecked release.','Actualoriginalcongestioncallbacks/IRQ/SMP contexts must befixturebound.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
