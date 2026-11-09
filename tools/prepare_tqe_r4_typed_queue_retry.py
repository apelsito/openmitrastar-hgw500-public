"""Source-only compatible confirmed-CN typed multicast queue retry.

Markers are bounded by actual max fanout135, not by enlarged ownership ledger.
Provider owns persisted typed tokens; callback registration does not create a
reverse module dependency. No hardware or published-uncertain release/reset.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_tqe_bounded_admission_prototype import function

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-typed-batch-source-r4'

API=r'''
struct topaz_congest_q_desc;
struct topaz_congest_queue;
typedef int (*omcgq_batch_xmit_fn)(const struct omcgq_batch_token *,
	union topaz_tqe_cpuif_ppctl *);
int omcgq_batch_xmit_register(struct module *owner, omcgq_batch_xmit_fn fn);
int omcgq_batch_queue_admit(const struct omcgq_batch_token *batch,
	struct topaz_congest_q_desc *queue, union topaz_tqe_cpuif_ppctl *ppctl);
int omcgq_batch_has_queued(void);
int omcgq_batch_retry_acquire(const struct omcgq_batch_token *batch,
	struct omcgq_bank_token *token);
int omcgq_batch_queue_reserve(struct topaz_congest_queue *queue, u32 expected);
void omcgq_batch_queue_cancel_reserve(void);
'''

QUEUES=r'''/* Fixed typed markers: one multicastbatch<=135 pendingoutputs.
 * Original queue ring owns each payloadref; markers persist token, neverstack.
 */
struct omcgq_queue_marker {
	struct topaz_congest_q_desc *queue;
	u32 ring_index;
	struct omcgq_batch_token token;
	bool active;
};
static struct omcgq_queue_marker omcgq_queue_markers[OMCGQ_BATCH_FANOUT_MAX];
static u32 omcgq_queue_pending;
static omcgq_batch_xmit_fn omcgq_typed_xmit;
static struct module *omcgq_typed_owner;
static struct topaz_congest_queue *omcgq_credit_queue;
static u32 omcgq_queue_reserved;
static struct omcgq_queue_marker *omcgq_retry_marker;
static bool omcgq_queue_processing;

int omcgq_batch_retry_acquire(const struct omcgq_batch_token *batch,
	struct omcgq_bank_token *token)
{
	unsigned long flags;
	int acquired = 0;
	if (!token)
		return 0;
	token->generation = 0;
	token->owner = NULL;
	local_irq_save(flags);
	if (!omcgq_retry_marker || !omcgq_retry_marker->active ||
	    !omcgq_batch_matches(batch) || omcgq_reserved || omcgq_quarantined ||
	    omcgq_generation == ~0U ||
	    omcgq_retry_marker->token.generation != batch->generation ||
	    omcgq_retry_marker->token.owner != batch->owner)
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
EXPORT_SYMBOL(omcgq_batch_retry_acquire);

int omcgq_batch_queue_reserve(struct topaz_congest_queue *queue, u32 expected)
{
	unsigned long flags;
	int admitted = 0;
	if (!queue || !expected || expected > OMCGQ_BATCH_FANOUT_MAX)
		return 0;
	local_irq_save(flags);
	if (omcgq_queue_reserved || omcgq_queue_pending || omcgq_batch.active ||
	    omcgq_quarantined || queue->total_qlen > TOPAZ_CONGEST_TOTAL_PKT_MAX ||
	    expected > TOPAZ_CONGEST_TOTAL_PKT_MAX - queue->total_qlen)
		goto out;
	omcgq_credit_queue = queue;
	omcgq_queue_reserved = expected;
	admitted = 1;
out:
	local_irq_restore(flags);
	return admitted;
}
EXPORT_SYMBOL(omcgq_batch_queue_reserve);

void omcgq_batch_queue_cancel_reserve(void)
{
	unsigned long flags;
	local_irq_save(flags);
	if (!omcgq_batch.active && !omcgq_queue_pending) {
		omcgq_queue_reserved = 0;
		omcgq_credit_queue = NULL;
	}
	local_irq_restore(flags);
}
EXPORT_SYMBOL(omcgq_batch_queue_cancel_reserve);

int omcgq_batch_has_queued(void) { return READ_ONCE(omcgq_queue_pending) != 0; }
EXPORT_SYMBOL(omcgq_batch_has_queued);

int omcgq_batch_xmit_register(struct module *owner, omcgq_batch_xmit_fn fn)
{
	unsigned long flags;
	int registered = 0;
	if (!owner || !fn)
		return 0;
	local_irq_save(flags);
	if (!omcgq_typed_xmit && !omcgq_retained && !omcgq_batch.active) {
		/* A stored function pointer is already a lifetime dependency. Pin both
		 * modules before registration can outlive a failed batch admission. */
		if (!try_module_get(owner))
			goto out;
		if (!try_module_get(THIS_MODULE)) {
			module_put(owner);
			goto out;
		}
		omcgq_owner = owner;
		omcgq_retained = true;
		omcgq_typed_xmit = fn;
		omcgq_typed_owner = owner;
		registered = 1;
	} else if (owner == omcgq_typed_owner && fn == omcgq_typed_xmit) {
		registered = 1;
	}
out:
	local_irq_restore(flags);
	return registered;
}
EXPORT_SYMBOL(omcgq_batch_xmit_register);

int omcgq_batch_queue_admit(const struct omcgq_batch_token *batch,
	struct topaz_congest_q_desc *queue, union topaz_tqe_cpuif_ppctl *ppctl)
{
	unsigned long flags;
	u32 slot;
	u32 ring;
	int admitted = 0;
	if (!queue || !ppctl)
		return 0;
	local_irq_save(flags);
	if (!omcgq_batch_matches(batch) || omcgq_quarantined ||
	    omcgq_queue_pending == OMCGQ_BATCH_FANOUT_MAX ||
	    queue->congest_queue != omcgq_credit_queue || !omcgq_queue_reserved ||
	    omcgq_batch.completed >= omcgq_batch.expected)
		goto out;
	for (slot = 0; slot < OMCGQ_BATCH_FANOUT_MAX; slot++)
		if (!omcgq_queue_markers[slot].active)
			break;
	if (slot == OMCGQ_BATCH_FANOUT_MAX)
		goto out;
	ring = queue->tail;
	/* Convert a pre-reserved global credit before the ordinary enqueue. */
	omcgq_queue_reserved--;
	if (topaz_congest_enqueue(queue, ppctl) != NET_XMIT_SUCCESS) {
		omcgq_queue_reserved++;
		goto out;
	}
	omcgq_queue_markers[slot].queue = queue;
	omcgq_queue_markers[slot].ring_index = ring;
	omcgq_queue_markers[slot].token = *batch;
	omcgq_queue_markers[slot].active = true;
	omcgq_queue_pending++;
	omcgq_batch.completed++;
	admitted = 1;
out:
	local_irq_restore(flags);
	return admitted;
}
EXPORT_SYMBOL(omcgq_batch_queue_admit);

static struct omcgq_queue_marker *omcgq_typed_head(struct topaz_congest_q_desc *queue)
{
	u32 slot;
	for (slot = 0; slot < OMCGQ_BATCH_FANOUT_MAX; slot++)
		if (omcgq_queue_markers[slot].active &&
		    omcgq_queue_markers[slot].queue == queue &&
		    omcgq_queue_markers[slot].ring_index == queue->head)
			return &omcgq_queue_markers[slot];
	return NULL;
}

static void omcgq_typed_success(struct omcgq_queue_marker *marker)
{
	if (!marker || !marker->active)
		return;
	marker->active = false;
	if (omcgq_queue_pending)
		omcgq_queue_pending--;
	omcgq_batch.published++;
	if (!omcgq_queue_pending && omcgq_batch.completed == omcgq_batch.expected &&
	    omcgq_batch.published == omcgq_batch.expected && !omcgq_reserved) {
		memset(&omcgq_held[omcgq_batch.ledger_slot], 0, sizeof(omcgq_held[0]));
		omcgq_held_count--;
		omcgq_batch.active = false;
		omcgq_queue_reserved = 0;
		omcgq_credit_queue = NULL;
	}
}

'''

XMIT=r'''static int omtqe_typed_queue_xmit(const struct omcgq_batch_token *batch,
	union topaz_tqe_cpuif_ppctl *ppctl)
{
	struct omcgq_bank_token token;
	unsigned long flags;
	unsigned int count;
	int ready = 0;
	if (!omcgq_batch_retry_acquire(batch, &token))
		return OMTQE_OWNERSHIP_REFUSED;
	local_irq_save(flags);
	for (count = 0; count < OMTQE_READY_READ_MAX; count++) {
		if (!topaz_tqe_cpuif_tx_nready()) { ready = 1; break; }
		cpu_relax();
	}
	if (!ready)
		(void)omcgq_bank_quarantine(&token, NULL, false);
	local_irq_restore(flags);
	return ready ? omtqe_lhost_submit_reserved(&token, ppctl) : OMTQE_OWNERSHIP_REFUSED;
}

'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);q=(PARENT/'topaz_congest_queue.c').read_text();t=(PARENT/'switch_tqe.c').read_text();h=(PARENT/'openmitrastar_tqe_bounded_ownership.h').read_text().replace('#endif',API+'#endif',1)
 # Insert typed marker state afterbatchstate so all providerfunctions have types.
 pos=q.index('static bool omcgq_batch_matches');q=q[:pos]+QUEUES+q[pos:]
 # Forwardmatchingprototype beforequeueadmitdefinition.
 q=q.replace('struct omcgq_queue_marker {','static bool omcgq_batch_matches(const struct omcgq_batch_token *batch);\nstruct omcgq_queue_marker {',1)
 # Everyordinaryqueueproducerrespects credits reservedfor this batch. Capacity
 # failure maystilloccur atperqueue/poolpolicy; thatpath retainsratherthanfree.
 old=function(q,'__attribute__((section(".sram.text"))) int topaz_congest_enqueue(')
 new=old.replace('\tif ((queue->qlen >= TOPAZ_CONGEST_PKT_MAX) ||','\tif (queue->congest_queue == omcgq_credit_queue &&\n\t    queue->congest_queue->total_qlen + omcgq_queue_reserved >= TOPAZ_CONGEST_TOTAL_PKT_MAX)\n\t\treturn NET_XMIT_CN;\n\tif ((queue->qlen >= TOPAZ_CONGEST_PKT_MAX) ||',1)
 q=q.replace(old,new,1)
 old=function(q,'int omcgq_batch_finish(');new=old.replace('\tif (omcgq_batch_matches(batch)) {','\tif (omcgq_batch_matches(batch)) {\n\t\tif (omcgq_queue_pending && !omcgq_quarantined) {\n\t\t\taccepted = 1;\n\t\t\tgoto out; /* queued tokens remain valid untillastretry succeeds */\n\t\t}',1).replace('\t\tomcgq_batch.active = false;','\t\tomcgq_batch.active = false;\n\t\tif (!omcgq_queue_pending) {\n\t\t\tomcgq_queue_reserved = 0;\n\t\t\tomcgq_credit_queue = NULL;\n\t\t}',1).replace('\tlocal_irq_restore(flags);','out:\n\tlocal_irq_restore(flags);',1);q=q.replace(old,new,1)
 old=function(q,'__attribute__((section(".sram.text"))) int topaz_congest_queue_xmit(');new=old.replace('\tint ret;','\tstruct omcgq_queue_marker *typed;\n\tunsigned long retry_irq_flags;\n\tint ret;',1).replace('\tcongest_queue->xmit_entry++;','\tlocal_irq_save(retry_irq_flags);\n\tif (omcgq_queue_processing) {\n\t\tlocal_irq_restore(retry_irq_flags);\n\t\treturn 1; /* defer nestedqueueconsumer beforetouching samehead */\n\t}\n\tomcgq_queue_processing = true;\n\tlocal_irq_restore(retry_irq_flags);\n\tcongest_queue->xmit_entry++;',1).replace('\t\tret = congest_queue->xmit_func(pp_cntl);','\t\ttyped = omcgq_typed_head(queue);\n\t\tif (typed && omcgq_typed_xmit) {\n\t\t\tlocal_irq_save(retry_irq_flags);\n\t\t\tomcgq_retry_marker = typed;\n\t\t\tret = omcgq_typed_xmit(&typed->token, pp_cntl);\n\t\t\tomcgq_retry_marker = NULL;\n\t\t\tlocal_irq_restore(retry_irq_flags);\n\t\t} else {\n\t\t\tret = congest_queue->xmit_func(pp_cntl);\n\t\t}',1).replace('\t\t/* Transmit successfully */','\t\tif (typed)\n\t\t\tomcgq_typed_success(typed);\n\t\t/* Transmit successfully */',1)
 # Make typedowner/credit/ringhead accounting one transaction before interrupts
 # can admit another batch. Ordinaryhead behavior remains its original path.
 new=new.replace('\t\tif (typed)\n\t\t\tomcgq_typed_success(typed);\n\t\t/* Transmit successfully */\n\t\ttopaz_congest_dequeue(queue);','\t\t/* Typed owner/credit/head state is committed atomically. */\n\t\tif (typed) {\n\t\t\tlocal_irq_save(retry_irq_flags);\n\t\t\tomcgq_typed_success(typed);\n\t\t\ttopaz_congest_dequeue(queue);\n\t\t\tlocal_irq_restore(retry_irq_flags);\n\t\t} else {\n\t\t\ttopaz_congest_dequeue(queue);\n\t\t}',1)
 # Everyexit aftertakingconsumerlease releasesit afterheadbookkeeping; nested
 # IRQ consumers defer rather than re-submit the same publishedhead.
 new=new.replace('\t\t\treturn 0; /* keep head:','\t\t\tgoto release_processing; /* keep head:',1).replace('\t\t\treturn 0;\n\t\t}\n\t}', '\t\t\tgoto release_processing;\n\t\t}\n\t}',1).replace('\treturn re_sched;','release_processing:\n\tlocal_irq_save(retry_irq_flags);\n\tomcgq_queue_processing = false;\n\tlocal_irq_restore(retry_irq_flags);\n\treturn re_sched;',1)
 q=q.replace(old,new,1)
 old=function(q,'noinline static void topaz_congest_queue_clear(');new=old.replace('\tqueue->congest_drop += queue->qlen','\tif (omcgq_typed_head(queue)) {\n\t\tomcgq_quarantined = true;\n\t\treturn; /* no unboundedHBMcleanup of typedowner */\n\t}\n\tqueue->congest_drop += queue->qlen',1).replace('\twhile(queue->qlen) {','\twhile(queue->qlen) {\n\t\tif (omcgq_typed_head(queue)) {\n\t\t\tomcgq_quarantined = true;\n\t\t\treturn; /* precedinguntypedhead mayhaveadvancedonto typedowner */\n\t\t}',1);q=q.replace(old,new,1)
 # Definecallback beforewrapper so constructor canregister exactfunction.
 pos=t.index('/* Local callback context:');t=t[:pos]+XMIT+t[pos:]
 old=function(t,'static void omtqe_push_mcast_batch(');needle='\t/* Existing normal queues cannot encode this batch token.';start=old.index(needle);end=old.index('\t(void)omcgq_batch_complete',start);queuepath='\tif (result == NET_XMIT_CN && context->queue) {\n\t\tstruct topaz_congest_queue *cgq = context->queue;\n\t\tstruct topaz_congest_q_desc *queued = topaz_queue_congested(cgq, node, tid) ? topaz_get_congest_queue(cgq, node, tid) : topaz_congest_alloc_queue(cgq, node, tid);\n\t\tif (queued && omcgq_batch_queue_admit(&context->batch, queued, &ppctl)) {\n\t\t\ttasklet_schedule(&cgq->congest_tx);\n\t\t\treturn;\n\t\t}\n\t}\n';new=old[:start]+queuepath+old[start:end]+old[end:];t=t.replace(old,new,1)
 # Register providerownedcallback beforemulticastrefcountadmission.
 old=function(t,'static uint32_t __sram_text tqe_push_mc_ports(');new=old.replace('\tif (!omcgq_batch_admit(THIS_MODULE,','\tif (!omcgq_batch_xmit_register(THIS_MODULE, omtqe_typed_queue_xmit))\n\t\treturn 0;\n\tif (queue && !omcgq_batch_queue_reserve(queue, push_count))\n\t\treturn 0;\n\tif (!omcgq_batch_admit(THIS_MODULE,',1)
 new=new.replace('&context.batch))\n\t\treturn 0;','&context.batch)) {\n\t\tomcgq_batch_queue_cancel_reserve();\n\t\treturn 0;\n\t}',1);t=t.replace(old,new,1)
 for name,text in(('switch_tqe.c',t),('topaz_congest_queue.c',q),('openmitrastar_tqe_bounded_ownership.h',h)):(a.output/name).write_text(text,newline='\n')
 result={'schema':'openmitrastar.tqe-r4-typedqueue-source/v1','status':'SOURCE_ONLY_TYPED_QUEUE_RETRY_PENDING_CAPACITY_AND_LIFECYCLE_FIXTURES','hardware_accessed':False,'firmware_eligible':False,'marker_bound':135,'ledger_capacity_unchanged':256,'typed_tokens_persist_provider_owned':True,'confirmed_CN_retries_via_original_queue':True,'published_unknown_never_retried':True,'global_credits_reserved_before_ec':True,'files':{n:sha(a.output/n)for n in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h')},'remaining_gates':['Perqueue/poolcapacitypolicyrefusal retainsowner; exactqueuecallbackfixture needed.','Actualqueuexmit/clear callbackinterleaving andmarker consumption fixtures.','Matchingheaders/prototypes allsourceusers compile closure andABI.' ]};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
