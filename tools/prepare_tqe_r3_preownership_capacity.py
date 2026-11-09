"""Source-only finite ownership-capacity admission before multicast refcounts.

No ledger enlargement: 256 existing records and the actual <=135 fanout bound.
Admission for the selected multicast owner happens before ec/freecount mutation;
capacity refusal returns ordinary caller ownership without cleanup/reset. This
candidate does not claim final recovery or foreign-processor arbitration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_tqe_bounded_admission_prototype import function

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-source-r2'

CAPACITY = r'''/* Source-only preownership catalog reservation. Capacity is unchanged.
 * A nested batch cannot create additional refs while this owner is admitted.
 * At most128WMACnodes+7non-WMACports =135outputs; reserve each before mutation.
 */
#define OMCGQ_MULTICAST_FANOUT_MAX 135U
static bool omcgq_batch_active;
static u32 omcgq_batch_credits;
static u32 omcgq_batch_generation;
static struct module *omcgq_batch_owner;

int omcgq_batch_begin(struct module *owner, u32 refs, u32 *generation)
{
	unsigned long flags;
	int admitted = 0;
	if (!generation || !owner || !refs || refs > OMCGQ_MULTICAST_FANOUT_MAX)
		return 0;
	*generation = 0;
	local_irq_save(flags);
	if (omcgq_batch_active || omcgq_reserved || omcgq_quarantined ||
	    omcgq_held_count > OMCGQ_HELD_MAX ||
	    refs > OMCGQ_HELD_MAX - omcgq_held_count || omcgq_batch_generation == ~0U)
		goto out;
	/* First real TQE submit still acquires module pins before publication.
	 * Batch begin must not create hardware ownership or modify HBM refs. */
	omcgq_batch_generation++;
	omcgq_batch_credits = refs;
	omcgq_batch_active = true;
	omcgq_batch_owner = owner;
	*generation = omcgq_batch_generation;
	admitted = 1;
out:
	local_irq_restore(flags);
	return admitted;
}
EXPORT_SYMBOL(omcgq_batch_begin);

int omcgq_batch_end(struct module *owner, u32 generation)
{
	unsigned long flags;
	int ended = 0;
	local_irq_save(flags);
	if (omcgq_batch_active && owner == omcgq_batch_owner && generation &&
	    generation == omcgq_batch_generation) {
		omcgq_batch_active = false;
		omcgq_batch_owner = NULL;
		omcgq_batch_credits = 0;
		ended = 1;
	}
	local_irq_restore(flags);
	return ended;
}
EXPORT_SYMBOL(omcgq_batch_end);
'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 for name in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h'):shutil.copyfile(PARENT/name,a.output/name)
 cgq=a.output/'topaz_congest_queue.c';text=cgq.read_text();marker='struct topaz_congest_queue *g_congest_queue_ptr = NULL;';assert text.count(marker)==1;text=text.replace(marker,CAPACITY+'\n'+marker,1);cgq.write_text(text,newline='\n')
 api=a.output/'openmitrastar_tqe_bounded_ownership.h';text=api.read_text();text=text.replace('#endif','int omcgq_batch_begin(struct module *owner, u32 refs, u32 *generation);\nint omcgq_batch_end(struct module *owner, u32 generation);\n#endif',1);api.write_text(text,newline='\n')
 tqe=a.output/'switch_tqe.c';text=tqe.read_text();old=function(text,'static uint32_t __sram_text tqe_push_mc_ports(');new=old.replace('\tuint32_t push_count;','\tuint32_t batch_generation;\n\tuint32_t push_count;',1)
 marker='\ttqe_buf_set_refcounts((uint8_t *)buf_virt_rx + offset, push_count, 0);'
 assert new.count(marker)==1
 new=new.replace(marker,'\t/* Refuse before ANY HBM refcount mutation when finite catalog unavailable. */\n\tif (!omcgq_batch_begin(THIS_MODULE, push_count, &batch_generation))\n\t\treturn 0;\n'+marker,1)
 new=new.replace('\treturn push_count;','\t(void)omcgq_batch_end(THIS_MODULE, batch_generation);\n\treturn push_count;',1)
 text=text.replace(old,new,1);tqe.write_text(text,newline='\n')
 result={'schema':'openmitrastar.tqe-r3-preownership-capacity/v1','status':'SOURCE_ONLY_FINITE_BATCH_ADMISSION_INCOMPLETE_WRITER_INTEGRATION','hardware_accessed':False,'firmware_eligible':False,'ledger_capacity_unchanged':256,'multicast_fanout_bound':135,'admission_before_multicast_ec_mutation':True,'nested_batch_refused':True,'parent_sha256':sha(PARENT/'result.json'),'files':{n:sha(a.output/n)for n in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h')},'remaining_blockers':['Providerbank_acquire musthonorbatchowner/contexttoken fornonbatchnestedwriters; currentmoduleAPI doesnotknowcallbackcallerbatchtoken.','Batchcredits notconsumedbyretention paths; incompleteintegration NO_GO, no binary built.','Pre-refcount batchowner pinned beforeHBMownership needsconsumer/providerrefs acquiredatbegin orstructuralstartpin.','RealHBMrefcountcleanupfinalrelease waitunbounded; foreignbank0writers/recovery remainunknown.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
