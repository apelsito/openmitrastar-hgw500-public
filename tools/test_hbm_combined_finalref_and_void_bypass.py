"""Real HBM primitives + typed finalref; reproduce original void bypass.

This is a source-only counterexample witness, not a qualified global fence.
The weak OEM void put body writes again after typed quarantine when DONE later
appears. The combined typed path never does. No hardware or module mutations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_tqe_bounded_admission_prototype import function
from test_hbm_bounded_transaction_core import PRE

EXTRA=r'''
typedef int8_t int8_t;
#define TOPAZ_HBM_BUF_WMAC_RX_POOL 1
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_BUF_MAGIC_CHK_ALLPOOL 1
#define HBM_HR_OFFSET_ENQ_CNT 1
#define HBM_HR_OFFSET_FREE_CNT 2
static u32 counts[4];static int magic_bad,magic_handle;
static int8_t topaz_hbm_payload_get_pool_bus(void*p){(void)p;return 1;}
static void*bus_to_virt(uintptr_t p){return(void*)p;}
static u32*topaz_hbm_buf_get_meta(void*p){(void)p;return counts+3;}
static u32 arc_read_uncached_32(u32*p){return*p;}
static void arc_write_uncached_32(u32*p,u32 v){*p=v;}
static int hbm_buf_check_buf_magic(u32*p){(void)p;return magic_bad;}
static int topaz_hbm_handle_buf_err(u32*p,int pool){(void)p;(void)pool;return magic_handle;}
static void*topaz_hbm_payload_store_align_bus(void*p,int pool,int aligned){(void)pool;(void)aligned;return p;}
#define topaz_hbm_local_irq_save local_irq_save
#define topaz_hbm_local_irq_restore local_irq_restore
static void qtn_pipeline_drain(void){}
static void qtn_mproc_sync_log(const char*p){(void)p;}
#define unlikely(v) (v)
'''

TEST=r'''
static void clear(void){omhbm_generation=0;omhbm_reserved=omhbm_quarantined=omhbm_pending_release=false;omhbm_pending_buffer=NULL;omhbm_pending_pool=0;irq=phase=pre_reads=post_reads=writes=requests=releases=data_reads=relaxes=0;pre_done_on=post_done_on=1;data_value=0x1234;magic_bad=magic_handle=0;}
int main(void){unsigned cases=0;void*buf=(void*)0x4444;
for(unsigned ec=1;ec<=135;ec++)for(unsigned fc=0;fc<ec;fc++){
 clear();counts[2]=ec;counts[1]=fc;pre_done_on=0;
 enum omhbm_result r=omhbm_final_ref_preserve_abi(buf);
 if(fc+1<ec)assert(r==OMHBM_OK&&counts[1]==fc+1&&!pre_reads&&!writes);
 else assert(r==OMHBM_REFUSED&&counts[1]==fc&&counts[2]==ec&&pre_reads==1024&&!writes);
 assert(!irq);cases++;
}
for(unsigned ec=1;ec<=135;ec++)for(unsigned done=0;done<=1025;done++){
 clear();counts[2]=ec;counts[1]=ec-1;post_done_on=done;
 enum omhbm_result r=omhbm_final_ref_preserve_abi(buf);
 assert(pre_reads==1&&counts[2]==1&&counts[1]==0&&releases==1&&writes==2&&!data_reads&&!irq);
 if(done&&done<=1024)assert(r==OMHBM_OK&&post_reads==done&&!omhbm_quarantined&&!omhbm_pending_buffer);
 else {assert(r==OMHBM_PUBLISHED_UNKNOWN&&post_reads==1024&&omhbm_quarantined&&omhbm_pending_buffer==buf&&omhbm_pending_pool==1);unsigned n=writes;assert(omhbm_final_ref_preserve_abi(buf)==OMHBM_REFUSED&&writes==n);}
 cases++;
}
clear();counts[2]=7;counts[1]=6;magic_bad=1;assert(omhbm_final_ref_preserve_abi(buf)==OMHBM_REFUSED&&!writes&&!omhbm_reserved&&counts[2]==7&&counts[1]==6&&!irq);cases++;
/* Actual original weak body bypasses the typed latch. Readiness may arrive
 * later; waiting never authorizes republishing the retained unknownrelease. */
clear();counts[2]=3;counts[1]=2;post_done_on=0;assert(omhbm_final_ref_preserve_abi(buf)==OMHBM_PUBLISHED_UNKNOWN);assert(writes==2&&releases==1&&omhbm_quarantined);
post_done_on=post_reads+1;topaz_hbm_put_buf(buf,1);assert(writes==4&&releases==2&&omhbm_quarantined&&omhbm_pending_buffer==buf&&!irq);cases++;
printf("{\"cases\":%u,\"original_void_bypass_reproduced\":true}\n",cases);return 0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1]
    header=root/'work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h';text=header.read_text()
    primitives='\n'.join(typ+' '+function(text,s)for typ,s in [('static int','__topaz_hbm_is_done('),('static void','__topaz_hbm_release_buf('),('static void','__topaz_hbm_request_start('),('static void *','__topaz_hbm_rd_buf(')])
    # Search exact signature to avoid substring collisions with nowait helpers.
    voidbodies='\n'.join(typ+' '+function(text,s)for typ,s in [('static void','__topaz_hbm_wait(void)'),('static void','__topaz_hbm_put_buf(void *buf')])
    wrapper=function(text,'RUBY_WEAK(topaz_hbm_put_buf) void topaz_hbm_put_buf(void *buf')
    assert wrapper.count('#endif')==1
    voidbodies+='\n'+wrapper.replace('RUBY_WEAK(topaz_hbm_put_buf) void','static void',1).replace('#endif','',1)
    core=root/'outputs/rea/driver5g-ops-20261022-hbm-bounded-core-source-r1/bounded-hbm-transaction-core.h';final=root/'outputs/rea/driver5g-ops-20261022-hbm-final-ref-abi-source-r1/typed-final-ref-preserve-abi.h'
    pins={str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),header,core,final)}
    a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-combined-finalref-void-bypass.c';f.write_text(PRE+EXTRA+primitives+core.read_text()+final.read_text()+voidbodies+TEST)
    b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode()
    r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();observed=json.loads(r.stdout)
    result=dict(schema='openmitrastar.hbm-combined-finalref-void-bypass/v1',status='PASS_COMBINED_TYPED_PATH_AND_REPRODUCED_ORIGINAL_VOID_BYPASS_BLOCKER',hardware_accessed=False,firmware_eligible=False,cases=observed['cases'],original_void_bypass_reproduced=True,actual_oem_bodies=7,original_recycle_ec1_fc0_kept=True,typed_unknown_retained_no_retry=True,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),input_pins=pins,limits='Source-only fake MMIO. Original void APIs demonstrably bypass typed quarantine; all header consumers and ownership admission/provider pinning must change together before integration. Not a global fence or module change.')
    for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
