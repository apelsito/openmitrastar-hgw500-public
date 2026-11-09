"""Actual CGQ provider token/ledger/lifetime API fixture, no MMIO or hardware.

Fake module-reference callbacks prove before-ownership pin sequencing, wrong
owner/stale token rejection, bounded append/coalescing ledger and retained exit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

PRE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define EXPORT_SYMBOL(x)
#define READ_ONCE(x) (x)
typedef uint32_t u32;
struct module {unsigned refs;bool deny;};
static struct module provider,consumer,foreign;
#define THIS_MODULE (&provider)
static bool try_module_get(struct module*m){if(m->deny)return false;m->refs++;return true;}
static void module_put(struct module*m){assert(m->refs);m->refs--;}
static unsigned irqstate;
static void irqsave(unsigned long*f){*f=irqstate;irqstate=1;}
static void irqrestore(unsigned long f){irqstate=f;}
#define local_irq_save(f) irqsave(&(f))
#define local_irq_restore(f) irqrestore(f)
union topaz_tqe_cpuif_ppctl{u32 raw[6];};
struct omcgq_bank_token {u32 generation;struct module*owner;};
struct topaz_congest_queue{int congest_tx;};
static struct topaz_congest_queue*g_congest_queue_ptr;
static unsigned tasklet_kills,queue_frees;
static void tasklet_kill(int*p){(void)p;tasklet_kills++;}
static void kfree(void*p){(void)p;queue_frees++;}
'''

TEST = r'''
static unsigned cases;
static void clear(void){memset(omcgq_held,0,sizeof(omcgq_held));omcgq_held_count=omcgq_unrecorded=omcgq_generation=0;omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_owner=NULL;provider.refs=consumer.refs=foreign.refs=0;provider.deny=consumer.deny=foreign.deny=false;irqstate=tasklet_kills=queue_frees=0;}
int main(void){struct omcgq_bank_token t,wrong,next;union topaz_tqe_cpuif_ppctl p={{1,2,3,4,5,6}},first;struct topaz_congest_queue queue;
clear();consumer.deny=true;assert(!omcgq_bank_acquire(&consumer,&t)&&!omcgq_retained&&!consumer.refs&&!provider.refs);cases++;
clear();provider.deny=true;assert(!omcgq_bank_acquire(&consumer,&t)&&!omcgq_retained&&!consumer.refs&&!provider.refs);cases++;
clear();assert(omcgq_bank_acquire(&consumer,&t)&&omcgq_bank_token_valid(&t)&&consumer.refs==1&&provider.refs==1);cases++;
wrong=t;wrong.owner=&foreign;assert(!omcgq_bank_cancel(&wrong)&&omcgq_bank_token_valid(&t));cases++;
wrong=t;wrong.generation++;assert(!omcgq_bank_cancel(&wrong)&&omcgq_bank_token_valid(&t));cases++;
assert(!omcgq_bank_acquire(&foreign,&next)&&omcgq_bank_token_valid(&t));cases++;
assert(omcgq_bank_cancel(&t)&&!omcgq_bank_token_valid(&t));assert(omcgq_bank_acquire(&consumer,&next)&&next.generation!=t.generation&&provider.refs==1&&consumer.refs==1);assert(!omcgq_bank_cancel(&t)&&omcgq_bank_token_valid(&next));cases++;
assert(omcgq_bank_quarantine(&next,&p,true)&&omcgq_bank_quarantined()&&!omcgq_reserved&&omcgq_held_count==1);first=omcgq_held[0].descriptor;cases++;
for(unsigned i=0;i<100;i++)assert(omcgq_bank_retain(&p,true));assert(omcgq_held_count==1&&omcgq_held[0].references==101&&!memcmp(&first,&omcgq_held[0].descriptor,sizeof(first)));cases++;
for(unsigned i=1;i<256;i++){p.raw[0]=1000+i;assert(omcgq_bank_retain(&p,false));}assert(omcgq_held_count==256&&!memcmp(&first,&omcgq_held[0].descriptor,sizeof(first)));cases++;
p.raw[0]=9999;assert(!omcgq_bank_retain(&p,false)&&omcgq_unrecorded==1&&omcgq_held_count==256&&!memcmp(&first,&omcgq_held[0].descriptor,sizeof(first)));cases++;
assert(!omcgq_bank_acquire(&consumer,&t)&&!omcgq_bank_acquire(&foreign,&t)&&provider.refs==1&&consumer.refs==1);cases++;
topaz_congest_queue_exit(&queue);assert(!tasklet_kills&&!queue_frees);cases++;
clear();topaz_congest_queue_exit(&queue);assert(tasklet_kills==1&&queue_frees==1);cases++;
clear();omcgq_generation=~0U;assert(!omcgq_bank_acquire(&consumer,&t)&&!provider.refs&&!consumer.refs);cases++;
clear();irqstate=1;assert(omcgq_bank_acquire(&consumer,&t)&&irqstate==1&&omcgq_bank_cancel(&t)&&irqstate==1);cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=(a.candidate/'topaz_congest_queue.c').read_text()
    begin=source.index('#define OMCGQ_HELD_MAX');end=source.index('struct topaz_congest_queue *g_congest_queue_ptr',begin)
    provider=source[begin:end]
    exitbody=function(source,'void topaz_congest_queue_exit(')
    a.output.mkdir(parents=True,exist_ok=False);fixture=a.output/'actual-provider-lifecycle.c';fixture.write_text(PRE+provider+exitbody+TEST)
    proc=subprocess.run([str(a.compiler),'-std=c11','-O1',str(fixture),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert not proc.returncode,proc.stderr.decode()
    tested=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(tested.stderr);assert not tested.returncode,tested.stderr.decode()
    result={'status':'PASS_ACTUAL_PROVIDER_TOKEN_LEDGER_LIFETIME_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(tested.stdout)['cases'],'module_get_before_ownership':True,'failed_partial_get_rolled_back':True,'wrong_owner_and_stale_token_rejected':True,'ledger_bounded_no_overwrite':True,'ledger_saturation_unrecorded_explicit':True,'retained_queue_exit_no_free':True,'prior_irq_state_preserved':True,'source_sha256':hashlib.sha256((a.candidate/'topaz_congest_queue.c').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'limits':'Host fake module callbacks; no module load, real lifecycle/recovery/foreign writer/physical acceptance.'}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
