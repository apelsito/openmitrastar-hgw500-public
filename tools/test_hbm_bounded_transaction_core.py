"""Actual OEM HBM primitives plus bounded core pre/post ownership fixture.

MMIO DONE/request/release data are deterministic fakes. No driver or hardware.
Postpublication timeout is retained/quarantined and never retried/freed/reset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
typedef uint32_t u32;typedef uint8_t u8;
#define TOPAZ_HBM_LOCAL_CPU 0
#define TOPAZ_HBM_POOL_REQ(cpu) (0x110U+4U*(cpu))
#define TOPAZ_HBM_POOL_DATA(cpu) (0x140U+4U*(cpu))
#define TOPAZ_HBM_POOL_NUM(pool) ((pool)<<2)
#define TOPAZ_HBM_DONE (1U<<31)
#define TOPAZ_HBM_RELEASE_BUF 1U
#define TOPAZ_HBM_REQUEST_BUF 2U
static unsigned irq,phase,pre_reads,post_reads,pre_done_on,post_done_on,writes,requests,releases,data_reads,relaxes;
static uint32_t data_value;
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
static void cpu_relax(void){relaxes++;}
static uint32_t qtn_mproc_sync_mem_read(uint32_t address){
 if(address==0x140U){data_reads++;return data_value;}
 assert(address==0x110U);unsigned n;if(!phase){n=++pre_reads;return pre_done_on&&n>=pre_done_on?TOPAZ_HBM_DONE:0;}n=++post_reads;return post_done_on&&n>=post_done_on?TOPAZ_HBM_DONE:0;
}
static void qtn_mproc_sync_mem_write_wmb(uint32_t address,uint32_t value){assert(irq);writes++;if(address==0x140U){data_value=value;return;}assert(address==0x110U);if(value&1)releases++;if(value&2)requests++;phase=1;}
'''
TEST=r'''
static void clear(void){omhbm_generation=0;omhbm_reserved=omhbm_quarantined=omhbm_pending_release=false;omhbm_pending_buffer=NULL;omhbm_pending_pool=0;irq=phase=pre_reads=post_reads=writes=requests=releases=data_reads=relaxes=0;pre_done_on=post_done_on=1;data_value=0x1234;}
int main(void){unsigned cases=0;struct omhbm_token token,wrong;void*buf=(void*)99;
for(unsigned done=0;done<=1025;done++){
 clear();pre_done_on=done;int admitted=omhbm_admit(&token);assert(admitted==(done>0&&done<=1024));assert(pre_reads==(admitted?done:1024)&&!writes&&!requests&&!releases&&!data_reads&&!irq);if(admitted)assert(omhbm_cancel(&token));cases++;
}
for(unsigned done=0;done<=1025;done++){
 clear();assert(omhbm_admit(&token));post_done_on=done;enum omhbm_result r=omhbm_request(&token,0,&buf);
 if(done>0&&done<=1024)assert(r==OMHBM_OK&&buf==(void*)0x1234&&data_reads==1&&!omhbm_quarantined);else assert(r==OMHBM_PUBLISHED_UNKNOWN&&buf==NULL&&!data_reads&&omhbm_quarantined&&!omhbm_admit(&wrong));assert(requests==1&&writes==1&&!irq);cases++;
}
for(unsigned done=0;done<=1025;done++){
 clear();assert(omhbm_admit(&token));post_done_on=done;enum omhbm_result r=omhbm_release(&token,0,(void*)0x4444);
 if(done>0&&done<=1024)assert(r==OMHBM_OK&&!omhbm_pending_buffer&&!omhbm_quarantined);else assert(r==OMHBM_PUBLISHED_UNKNOWN&&omhbm_pending_buffer==(void*)0x4444&&omhbm_pending_release&&omhbm_quarantined&&!omhbm_admit(&wrong));assert(releases==1&&writes==2&&!irq);cases++;
}
clear();assert(omhbm_admit(&token));wrong=token;wrong.generation++;assert(!omhbm_cancel(&wrong)&&omhbm_token_valid(&token));assert(omhbm_cancel(&token));cases++;
clear();irq=1;assert(omhbm_admit(&token)&&irq==1);assert(omhbm_cancel(&token)&&irq==1);cases++;
printf("{\"cases\":%u}\n",cases);return0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];header=root/'work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h';text=header.read_text();primitives='\n'.join(typ+' '+function(text,s)for typ,s in [('static int','__topaz_hbm_is_done('),('static void','__topaz_hbm_release_buf('),('static void','__topaz_hbm_request_start('),('static void *','__topaz_hbm_rd_buf(')]);core=(a.candidate/'bounded-hbm-transaction-core.h').read_text();a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-hbm-primitives-core.c';f.write_text(PRE+primitives+core+TEST.replace('return0','return 0'));b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_HBM_PRIMITIVES_BOUNDED_PRE_POST_OWNER_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'OEM_primitive_functions_actual':4,'pretimeout_zero_writes_owner_unchanged':True,'postrequest_timeout_no_dataread_no_retry':True,'postrelease_timeout_bufferretained_no_retry':True,'generation_cancel_guard':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'original_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),'limits':'Source-only fakeMMIO progress; originalHBMvoidcaller andfinalrefcount_reset integration notaccepted/hardware/moduleproof.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
