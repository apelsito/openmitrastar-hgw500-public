"""Source-only final HBM ref transition using typed bounded requestor token.

Original exported void function is preserved in the baseline. New typed helper
admits prior DONE before resetting counters; postpublication uncertainty never
rolls counters back/retries/free/reset. No module or hardware eligibility.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=r'''/* SOURCE-ONLY final-reference transition. Finalref publication is one-way.
 * All generation/lifecycle/module ownership integration remains mandatory.
 */
static enum omhbm_result omhbm_final_ref_try(void *const buf_bus)
{
	const int8_t pool=topaz_hbm_payload_get_pool_bus(buf_bus);
	uint32_t *buffer;
	uint32_t *meta;
	uint32_t *enqueuep;
	uint32_t *freep;
	uint32_t ec,fc;
	void *aligned;
	struct omhbm_token token;
	unsigned long flags;
	enum omhbm_result result;
	if (pool!=TOPAZ_HBM_BUF_WMAC_RX_POOL && pool!=TOPAZ_HBM_BUF_EMAC_RX_POOL)
		return OMHBM_REFUSED;
	buffer=bus_to_virt((uintptr_t)buf_bus);
	meta=topaz_hbm_buf_get_meta(buffer);
	enqueuep=meta-HBM_HR_OFFSET_ENQ_CNT;
	freep=meta-HBM_HR_OFFSET_FREE_CNT;
	local_irq_save(flags);
	ec=arc_read_uncached_32(enqueuep);
	fc=arc_read_uncached_32(freep);
	/* Reject malformed/duplicate states, not wrap increment into a falsefree. */
	if (!ec || fc>=ec || fc==~0U) { result=OMHBM_REFUSED;goto out; }
	if (fc+1<ec) {
		arc_write_uncached_32(freep,fc+1);
		result=OMHBM_OK;
		goto out;
	}
	/* Lastreference: PRIORbankDONE must be admitted beforecounter reset/free. */
	if (!omhbm_admit(&token)) { result=OMHBM_REFUSED;goto out; }
	if (TOPAZ_HBM_BUF_MAGIC_CHK_ALLPOOL || pool==TOPAZ_HBM_BUF_WMAC_RX_POOL) {
		int bad=hbm_buf_check_buf_magic(buffer);
		if (bad && !topaz_hbm_handle_buf_err(buffer,pool)) {
			(void)omhbm_cancel(&token);
			result=OMHBM_REFUSED;
			goto out;
		}
	}
	aligned=topaz_hbm_payload_store_align_bus(buf_bus,pool,1);
	/* Publication transition: reset duplicates is originalcompatible, butmark
	 * a completedref beforebankwrite to preventanother softwarecaller free. */
	arc_write_uncached_32(freep,ec);
	result=omhbm_release(&token,(u8)pool,aligned);
	if (result==OMHBM_OK) {
		/* A fresh pool generation must reinitialize ec/fc; do not reset fc to0
		 * here because an old duplicate completion would cause a second free. */
	} else if (result==OMHBM_PUBLISHED_UNKNOWN) {
		/* Keepterminalfc==ec and pendingbuffer: no retry,rollback,freeorreset. */
	}
out:
	local_irq_restore(flags);
	return result;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);(a.output/'typed-final-reference.h').write_text(CORE,newline='\n');result={'schema':'openmitrastar.hbm-final-ref-source/v1','status':'SOURCE_ONLY_FINAL_REFERENCE_NO_ORIGINAL_ABI_PROMOTION','hardware_accessed':False,'firmware_eligible':False,'prebank_admission_before_ref_terminal_transition':True,'postpublication_timeout_no_counter_rollback':True,'duplicate_terminal_ref_refused':True,'explicit_behavior_delta':'Terminalfc==ec retained aftersuccessfulrelease; pool allocation/reinitialization mustestablishnewgeneration beforepayloadreuse. Notdrop-incompatible originalfc resetAPI.','source_sha256':hashlib.sha256(CORE.encode()).hexdigest(),'remaining_gates':['Exactpoolallocation generation resets/foreign hardwaremetadata consumers mustbeproved beforefc==ec productchange.','OriginalvoidAPIcaller typedresult recovery/modulepin context notintegrated.','Allmagic/debug/refcount/WireABI fullmodulebuild andcodequal pending.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
