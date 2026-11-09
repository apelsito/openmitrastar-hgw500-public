"""Actual OEM multicast enumeration and HBM refcount completion fixture, host only.

The final pool put is fake: its real path waits unbounded, so this fixture only
proves when cleanup would reach that blocker. No MMIO, firmware or device action.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

PRELUDE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define RUBY_INLINE static
#define EXPORT_SYMBOL(x)
#define TOPAZ_TQE_WMAC_PORT 2
#define TOPAZ_BITS_PER_WD 32
#define TOPAZ_FWT_SW_NODE_BITMAP_SIZE 4
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define TOPAZ_HBM_BUF_WMAC_RX_POOL 1
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_BUF_MAGIC_CHK_ALLPOOL 0
#define TOPAZ_HBM_DEBUG_STAMPS 0
#define HBM_HR_OFFSET_ENQ_CNT 1
#define HBM_HR_OFFSET_FREE_CNT 2
#define unlikely(x) (x)
#define HBM_STATS(a,b) ((void)0)
#define printk(...) ((void)0)
#define KERN_CRIT ""
struct topaz_fwt_sw_mcast_entry {uint32_t node_bitmap[4];uint8_t port_bitmap;};
static uint32_t meta[4];static unsigned pool_puts,callbacks;
static void *bus_to_virt(uintptr_t p){return(void*)p;}
static int topaz_hbm_payload_get_pool_bus(void*p){(void)p;return 0;}
static void *topaz_hbm_buf_get_meta(void*p){(void)p;return meta+3;}
static uint32_t arc_read_uncached_32(const uint32_t*p){return*p;}
static void arc_write_uncached_32(uint32_t*p,uint32_t v){*p=v;}
static int hbm_buf_check_buf_magic(void*p){(void)p;return 0;}
static int topaz_hbm_handle_buf_err(void*p,int pool){(void)p;(void)pool;return 1;}
static void topaz_hbm_put_payload_aligned_bus(void*p,int pool){(void)p;(void)pool;pool_puts++;}
static void callback(const void*t1,void*t2,uint8_t port,uint8_t node,uint8_t tid){(void)t1;(void)t2;(void)port;(void)node;(void)tid;callbacks++;}
'''

TESTS = r'''
int main(void){unsigned cases=0;struct topaz_fwt_sw_mcast_entry e;
for(unsigned bitmap=0;bitmap<256;bitmap++)for(unsigned input=0;input<8;input++){
 memset(&e,0,sizeof(e));e.port_bitmap=bitmap;e.node_bitmap[0]=0x17;
 unsigned expected=topaz_fwt_sw_mcast_enqueues(&e,(uint8_t)bitmap,(uint8_t)input,0);
 unsigned count=0;for(unsigned p=0;p<8;p++)if((bitmap&(1U<<p))&&p!=2&&p!=input)count++;
 count+=4;if(input==2)count--;assert(expected==count);cases++;
}
memset(&e,0,sizeof(e));e.node_bitmap[0]=0x17;callbacks=0;
assert(topaz_fwt_sw_mcast_do_per_node(callback,&e,NULL,NULL,0,2,0)==4&&callbacks==4);cases++;
callbacks=0;assert(topaz_fwt_sw_mcast_do_per_node(callback,&e,NULL,NULL,1,2,0)==3&&callbacks==3);cases++;
/* Five expected outputs, only two published completions: payload stays owned.
 * Lowering ec to two would permit an unsafe early free while other callbacks
 * and queue records still reference the payload; do not do it in a timeout. */
meta[2]=5;meta[1]=0;pool_puts=0;
topaz_hbm_filter_txdone_buf(meta);topaz_hbm_filter_txdone_buf(meta);
assert(meta[2]==5&&meta[1]==2&&pool_puts==0);cases++;
/* Three known unsubmitted refs must be accounted before release. The last
 * call invokes real final-put boundary (mocked here), whose OEM wait is unbounded. */
topaz_hbm_filter_txdone_buf(meta);topaz_hbm_filter_txdone_buf(meta);
assert(pool_puts==0&&meta[1]==4);topaz_hbm_filter_txdone_buf(meta);
assert(pool_puts==1&&meta[2]==1&&meta[1]==0);cases++;
/* An extra completion after reset immediately puts the same payload again:
 * duplicate retry/completion is not a benign counter increment. */
topaz_hbm_filter_txdone_buf(meta);assert(pool_puts==2);cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    fwt=root/'work/sources/Quantenna-GPL/include/qtn/topaz_fwt_cpuif.h'
    hbm=root/'work/linux510-radio-port/quantenna-f344-peers/platform/topaz/hbm.c'
    text=fwt.read_text()
    parts=[function(text,'topaz_fwt_sw_count_bits('),function(text,'topaz_fwt_sw_mcast_node_is_set('),function(text,'topaz_fwt_sw_mcast_enqueues('),function(text,'topaz_fwt_sw_mcast_do_per_node('),function(hbm.read_text(),'void  __attribute__((section(".sram.text"))) topaz_hbm_filter_txdone_buf(')]
    parts[0]='static uint8_t '+parts[0];parts[1]='static int '+parts[1];parts[2]='static uint32_t '+parts[2];parts[3]='static uint32_t '+parts[3]
    a.output.mkdir(parents=True,exist_ok=False);fixture=a.output/'actual-multicast-refcounts.c';fixture.write_text(PRELUDE+'\n'.join(parts)+TESTS)
    built=subprocess.run([str(a.compiler),'-O1','-std=c11',str(fixture),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(built.stderr);assert not built.returncode,built.stderr.decode()
    tested=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(tested.stderr);assert not tested.returncode,tested.stderr.decode()
    result={'status':'PASS_ACTUAL_MULTICAST_ENUMERATION_AND_HBM_REFERENCE_COUNTEREXAMPLES','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(tested.stdout)['cases'],'expected_refcount_before_callbacks':True,'midbatch_missing_refs_retain_payload':True,'final_release_boundary_reached_only_after_all_refs':True,'duplicate_completion_after_reset_double_release_reproduced':True,'real_final_put_unbounded':'topaz_hbm_put_payload_aligned_bus -> topaz_hbm_put_buf -> __topaz_hbm_wait','pins':{str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in(fwt,hbm,fixture)},'limits':'Final pool put mocked; source-only contract fixture. No safe bounded cleanup/recovery or driver/module/physical acceptance.'}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
