"""Actual R3 preownership batch-capacity functions; no MMIO or driver build.

Tests the finite reservation surface only. Credits are not yet integrated into
all callback publishers and pins, so success remains SOURCE_ONLY/NO_GO_MODULE.
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
typedef uint32_t u32;
struct module{int unused;};
static struct module owner,other;
#define EXPORT_SYMBOL(x)
#define OMCGQ_HELD_MAX 256U
#define OMCGQ_MULTICAST_FANOUT_MAX 135U
static bool omcgq_batch_active,omcgq_reserved,omcgq_quarantined;
static u32 omcgq_batch_credits,omcgq_batch_generation,omcgq_held_count;
static struct module*omcgq_batch_owner;
static unsigned irq;
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
'''
TEST=r'''
int main(void){u32 token,other_token;unsigned cases=0;
for(unsigned held=0;held<=256;held++)for(unsigned refs=0;refs<=136;refs++){
 omcgq_held_count=held;omcgq_batch_active=omcgq_reserved=omcgq_quarantined=false;omcgq_batch_owner=0;omcgq_batch_generation=0;
 int expected=(refs>0&&refs<=135&&refs<=256-held);assert(omcgq_batch_begin(&owner,refs,&token)==expected);
 if(expected){assert(omcgq_batch_active&&omcgq_batch_credits==refs&&token==1);assert(!omcgq_batch_begin(&other,1,&other_token));assert(!omcgq_batch_end(&other,token)&&omcgq_batch_active);assert(!omcgq_batch_end(&owner,token+1)&&omcgq_batch_active);assert(omcgq_batch_end(&owner,token)&&!omcgq_batch_active);}
 assert(!irq);cases++;
}
omcgq_batch_generation=~0U;omcgq_held_count=0;assert(!omcgq_batch_begin(&owner,1,&token));cases++;
omcgq_batch_generation=0;omcgq_quarantined=true;assert(!omcgq_batch_begin(&owner,1,&token));cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 text=(a.candidate/'topaz_congest_queue.c').read_text();body=function(text,'int omcgq_batch_begin(')+function(text,'int omcgq_batch_end(')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-batch-admission.c';f.write_text(PRE+body+TEST);proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert not proc.returncode,proc.stderr.decode();run=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not run.returncode,run.stderr.decode()
 result={'status':'PASS_SOURCE_ONLY_FINITE_BATCH_CAPACITY_FUNCTION_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(run.stdout)['cases'],'capacity_unchanged':256,'fanout_limit':135,'refusal_before_hbm_reference_mutation':True,'wrong_owner_stale_end_rejected':True,'candidate_source_sha256':hashlib.sha256((a.candidate/'topaz_congest_queue.c').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'Onlyfiniteadmissionfunctionsmodeled; allwriterbatchtokenflow, credits/pins integration andHMB/foreign/recovery remainNO_GO.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
