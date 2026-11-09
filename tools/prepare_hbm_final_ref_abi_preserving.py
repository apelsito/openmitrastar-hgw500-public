"""Source-only bounded last-reference transition preserving original ec/fc ABI.

Pre-admits DONE before reset ec1/fc0, retains one-way publication uncertainty and
refuses further typed operations under requestor quarantine. Original module and
void API remain untouched until complete caller/lifetime/generation qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

CORE=r'''/* SOURCE-ONLY last-reference helper; exact originalrecyclemetadata preserved.
 * TypedAPIonly: anypublishedUNKNOWN mustdisable/retain alloriginalcallers before
 * integration; originalvoid APIs bypassing quarantine are notqualified.
 */
static enum omhbm_result omhbm_final_ref_preserve_abi(void *const buf_bus)
{
	const int8_t pool=topaz_hbm_payload_get_pool_bus(buf_bus);
	uint32_t *buffer,*meta,*enqueuep,*freep;
	uint32_t ec,fc;
	struct omhbm_token token;
	void *aligned;
	unsigned long flags;
	enum omhbm_result result;
	if (pool!=TOPAZ_HBM_BUF_WMAC_RX_POOL && pool!=TOPAZ_HBM_BUF_EMAC_RX_POOL)
		return OMHBM_REFUSED;
	buffer=bus_to_virt((uintptr_t)buf_bus);meta=topaz_hbm_buf_get_meta(buffer);
	if (!meta)
		return OMHBM_REFUSED;
	enqueuep=meta-HBM_HR_OFFSET_ENQ_CNT;freep=meta-HBM_HR_OFFSET_FREE_CNT;
	local_irq_save(flags);
	if (omhbm_quarantined) { result=OMHBM_REFUSED;goto out; }
	ec=arc_read_uncached_32(enqueuep);fc=arc_read_uncached_32(freep);
	if (!ec || fc>=ec || fc==~0U) { result=OMHBM_REFUSED;goto out; }
	if (fc+1<ec) {
		arc_write_uncached_32(freep,fc+1);result=OMHBM_OK;goto out;
	}
	if (!omhbm_admit(&token)) { result=OMHBM_REFUSED;goto out; }
	if (TOPAZ_HBM_BUF_MAGIC_CHK_ALLPOOL || pool==TOPAZ_HBM_BUF_WMAC_RX_POOL) {
		int bad=hbm_buf_check_buf_magic(buffer);
		if (bad && !topaz_hbm_handle_buf_err(buffer,pool)) {
			(void)omhbm_cancel(&token);result=OMHBM_REFUSED;goto out;
		}
	}
	aligned=topaz_hbm_payload_store_align_bus(buf_bus,pool,1);
	/* KeeporiginalrecycleABI. Admission is alreadyheld, noearlierbankwaitcan
	 * happen afterthiscounterreset. Postpublication timeout cannotrollitback. */
	if (ec!=1) {
		arc_write_uncached_32(enqueuep,1);
		arc_write_uncached_32(freep,0);
	}
	result=omhbm_release(&token,(u8)pool,aligned);
out:
	local_irq_restore(flags);
	return result;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);(a.output/'typed-final-ref-preserve-abi.h').write_text(CORE,newline='\n');result={'schema':'openmitrastar.hbm-finalref-abi-source/v1','status':'SOURCE_ONLY_TYPED_ABI_PRESERVING_FINALREF_PENDING_CALLER_FENCE','hardware_accessed':False,'firmware_eligible':False,'original_recycle_ec1_fc0_kept':True,'prebank_admission_before_metadatareset':True,'postunknown_no_counterrollback':True,'source_sha256':hashlib.sha256(CORE.encode()).hexdigest(),'remaining_gates':['AlloriginalvoidHBMcallers mustrespectnewquarantine; otherwisetypedrefusalnotglobalfence.','OnepublishedHBMoperation/lifetime/token mustbeproviderownedandmodulepinned.','Singlebufferduplicatecompletion ABA unchanged originalABI; generationledger requiresallallocators/foreign consumers.','FullbaselineHBMmodulecompile/headeruserclosure/codequal andphysicalgate separate.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
