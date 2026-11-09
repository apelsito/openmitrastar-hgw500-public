"""Source-only bounded HBM requestor transaction; original void APIs untouched.

Exact hardware primitives are reused, with pre-admission before refcount mutation
and fail-closed postpublication uncertainty. No unsafe timeout free/reset/retry.
Full original HBM module/source integration needs a separate provenance gate.
"""
import argparse
import hashlib
import json
from pathlib import Path

CORE=r'''/* SOURCE-ONLY requestor0 operation token; not a replacement voidHBM API.
 * Pre-admission refusal leaves payload/refcounts untouched. After REQUEST/RELEASE
 * writes a timeout latches quarantine and forbids reuse, release, reset or retry.
 * MMIO stall latency and foreignprocessorwrites remain outside this read budget.
 */
#define OMHBM_READ_MAX 1024U
struct omhbm_token { u32 generation; };
enum omhbm_result { OMHBM_REFUSED=0, OMHBM_OK=1, OMHBM_PUBLISHED_UNKNOWN=2 };
static u32 omhbm_generation;
static bool omhbm_reserved;
static bool omhbm_quarantined;
static bool omhbm_pending_release;
static void *omhbm_pending_buffer;
static u8 omhbm_pending_pool;

static bool omhbm_token_valid(const struct omhbm_token *token)
{
	return token && token->generation && token->generation == omhbm_generation &&
		omhbm_reserved && !omhbm_quarantined;
}

static int omhbm_admit(struct omhbm_token *token)
{
	unsigned long flags;
	u32 count;
	int admitted=0;
	if (!token)
		return 0;
	token->generation=0;
	local_irq_save(flags);
	if (omhbm_reserved || omhbm_quarantined || omhbm_generation==~0U)
		goto out;
	for (count=0;count<OMHBM_READ_MAX;count++) {
		if (__topaz_hbm_is_done()) {
			omhbm_generation++;
			omhbm_reserved=true;
			token->generation=omhbm_generation;
			admitted=1;
			goto out;
		}
		cpu_relax();
	}
	/* Existingpendingoperation belongs to somebodyelse; neverresetit. */
	omhbm_quarantined=true;
out:
	local_irq_restore(flags);
	return admitted;
}

static int omhbm_cancel(const struct omhbm_token *token)
{
	unsigned long flags;
	int cancelled=0;
	local_irq_save(flags);
	if (omhbm_token_valid(token)) { omhbm_reserved=false;cancelled=1; }
	local_irq_restore(flags);
	return cancelled;
}

static enum omhbm_result omhbm_wait_owned(const struct omhbm_token *token)
{
	u32 count;
	if (!omhbm_token_valid(token))
		return OMHBM_PUBLISHED_UNKNOWN;
	for (count=0;count<OMHBM_READ_MAX;count++) {
		if (__topaz_hbm_is_done())
			return OMHBM_OK;
		cpu_relax();
	}
	omhbm_quarantined=true;
	om hbm_reserved=false;
	return OMHBM_PUBLISHED_UNKNOWN;
}

static enum omhbm_result omhbm_request(const struct omhbm_token *token,u8 pool,void **buffer)
{
	unsigned long flags;
	enum omhbm_result result;
	if (!buffer)
		return OMHBM_REFUSED;
	*buffer=NULL;
	local_irq_save(flags);
	if (!omhbm_token_valid(token)) { result=OMHBM_REFUSED;goto out; }
	omhbm_pending_release=false;omhbm_pending_pool=pool;omhbm_pending_buffer=NULL;
	__topaz_hbm_request_start(pool);
	result=omhbm_wait_owned(token);
	if (result==OMHBM_OK) { *buffer=__topaz_hbm_rd_buf(pool);omhbm_reserved=false; }
out:
	local_irq_restore(flags);
	return result;
}

static enum omhbm_result omhbm_release(const struct omhbm_token *token,u8 pool,void *buffer)
{
	unsigned long flags;
	enum omhbm_result result;
	local_irq_save(flags);
	if (!omhbm_token_valid(token)) { result=OMHBM_REFUSED;goto out; }
	omhbm_pending_release=true;omhbm_pending_pool=pool;omhbm_pending_buffer=buffer;
	__topaz_hbm_release_buf(buffer,pool);
	result=omhbm_wait_owned(token);
	if (result==OMHBM_OK) { omhbm_reserved=false;omhbm_pending_buffer=NULL; }
out:
	local_irq_restore(flags);
	return result;
}
'''.replace('om hbm_reserved','omhbm_reserved')

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);(a.output/'bounded-hbm-transaction-core.h').write_text(CORE,newline='\n');root=Path(__file__).resolve().parents[1];header=root/'work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h';result={'schema':'openmitrastar.hbm-bounded-transaction-source/v1','status':'SOURCE_ONLY_BOUNDED_REQUESTOR_CORE_NOT_ORIGINAL_API_REPLACEMENT','hardware_accessed':False,'firmware_eligible':False,'read_budget_each_phase':1024,'requestor':'LHOST0','original_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),'core_sha256':hashlib.sha256(CORE.encode()).hexdigest(),'constraints':['Admissiontoken beforeany HBMcounters/freecount resetmutation.','PostREQUESTorRELEASE timeout returnedOWNEDUNKNOWN; quarantine/no free/no retry/no reset.','RealvoidAPIcallers needtypedreturn adaptation andmoduleclosure beforeproduction.','No primitive hardwaretiming/foreignrequestor/MMIObusstall guarantee.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
