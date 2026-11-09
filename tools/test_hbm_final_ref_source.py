"""Typed final-reference source fixture; real cache/pool/hardware remain fakes.

Checks nonfinal increments, prebank no-mutation refusal, postrelease retention
and duplicate final completion rejection. Terminal metadata change is SOURCE_ONLY.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;typedef uint8_t u8;
#define TOPAZ_HBM_BUF_WMAC_RX_POOL 1
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_BUF_MAGIC_CHK_ALLPOOL 0
#define HBM_HR_OFFSET_ENQ_CNT 1
#define HBM_HR_OFFSET_FREE_CNT 2
enum omhbm_result{OMHBM_REFUSED,OMHBM_OK,OMHBM_PUBLISHED_UNKNOWN};
struct omhbm_token{u32 generation;};
static uint32_t counters[4];static unsigned irq,admit_ok,release_result,admits,releases,cancels;
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
static int8_t topaz_hbm_payload_get_pool_bus(void*p){(void)p;return 0;}
static void*bus_to_virt(uintptr_t p){return(void*)p;}
static void*topaz_hbm_buf_get_meta(void*p){(void)p;return counters+3;}
static uint32_t arc_read_uncached_32(uint32_t*p){return*p;}
static void arc_write_uncached_32(uint32_t*p,uint32_t v){*p=v;}
static int omhbm_admit(struct omhbm_token*t){admits++;t->generation=1;return admit_ok;}
static int omhbm_cancel(const struct omhbm_token*t){(void)t;cancels++;return 1;}
static int hbm_buf_check_buf_magic(void*p){(void)p;return0;}
static int topaz_hbm_handle_buf_err(void*p,int pool){(void)p;(void)pool;return1;}
static void*topaz_hbm_payload_store_align_bus(void*p,int pool,int aligned){(void)pool;(void)aligned;return p;}
static enum omhbm_result omhbm_release(const struct omhbm_token*t,u8 pool,void*p){(void)t;(void)pool;(void)p;releases++;return release_result;}
'''
TEST=r'''
int main(void){unsigned cases=0;for(unsigned ec=1;ec<=135;ec++)for(unsigned fc=0;fc<ec;fc++){
 counters[2]=ec;counters[1]=fc;admits=releases=0;admit_ok=0;release_result=OMHBM_OK;enum omhbm_result r=omhbm_final_ref_try(counters);
 if(fc+1<ec)assert(r==OMHBM_OK&&counters[1]==fc+1&&!admits&&!releases);else assert(r==OMHBM_REFUSED&&counters[1]==fc&&admits==1&&!releases);assert(!irq);cases++;}
for(unsigned result=1;result<=2;result++){counters[2]=3;counters[1]=2;admits=releases=0;admit_ok=1;release_result=result;assert(omhbm_final_ref_try(counters)==result&&counters[1]==3&&releases==1);assert(omhbm_final_ref_try(counters)==OMHBM_REFUSED&&releases==1);cases++;}
printf("{\"cases\":%u}\n",cases);return0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=(a.candidate/'typed-final-reference.h').read_text();a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-final-ref.c';f.write_text((PRE+text+TEST).replace('return0','return 0').replace('return1','return 1'));b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();result={'status':'PASS_SOURCE_ONLY_TYPED_FINAL_REF_ORDER_COUNTEREXAMPLES','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'nonfinal_no_MMIO_admission':True,'prebank_refusal_no_counterchange':True,'postrelease_terminal_ref_not_rolledback':True,'duplicate_release_refused':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'Typedhelperwholefunction actualsource; admission/release/magic/hardwarefake. Terminalcounter ABI differsoriginal; poolreusegenerationproof/moduleintegration pending.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
