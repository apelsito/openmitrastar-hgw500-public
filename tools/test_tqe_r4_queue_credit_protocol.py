"""Host fixture for exact finite queue-credit protocol source functions.

No driver/MMIO execution; tests admitted capacity, CN reservation conversion,
successful retry credit accounting and postpublication uncertainty refusal.
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
#include <string.h>
typedef uint32_t u32;
struct module{int unused;};static struct module owner,other;
static unsigned irq;
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
'''
TEST=r'''
int main(void){unsigned cases=0;struct omq_credit_token token,wrong;
for(unsigned used=0;used<=2048;used++)for(unsigned expected=1;expected<=135;expected++){
 memset(&omq_state,0,sizeof(omq_state));int accepted=expected<=2048-used;assert(omq_reserve(&owner,expected,used,&token)==accepted);
 if(accepted){assert(!omq_reserve(&other,1,used,&wrong));wrong=token;wrong.owner=&other;assert(!omq_enqueue_credit(&wrong,false));assert(omq_enqueue_credit(&token,false));assert(omq_state.queued==1&&omq_state.reserved==expected-1&&omq_state.outstanding==expected);assert(omq_accept(&token,true));for(unsigned i=1;i<expected;i++)assert(omq_accept(&token,false));assert(!omq_state.active&&!omq_state.outstanding&&!omq_state.reserved&&!omq_state.queued);}
 assert(!irq);cases++;
}
memset(&omq_state,0,sizeof(omq_state));assert(omq_reserve(&owner,2,0,&token));assert(!omq_enqueue_credit(&token,true)&&omq_state.quarantined&&omq_state.outstanding==2&&omq_state.reserved==2&&!omq_state.queued);assert(!omq_accept(&token,false));cases++;
memset(&omq_state,0,sizeof(omq_state));assert(omq_reserve(&owner,2,0,&token));assert(omq_enqueue_credit(&token,false));assert(omq_retain_unknown(&token)&&omq_state.quarantined&&omq_state.queued==1&&omq_state.outstanding==2);assert(!omq_accept(&token,true));cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=(a.candidate/'typed-queue-credit-core.h').read_text();a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-queue-credit.c';f.write_text(PRE+text+TEST);b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();result={'status':'PASS_SOURCE_ONLY_TYPED_QUEUE_CREDIT_PROTOCOL','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'existing_total_queue_capacity':2048,'preownership_refusal_before_ec':True,'confirmed_CN_queue_credit_retries_preserved':True,'published_unknown_no_enqueue_or_retry':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'Protocolscalarfunctions only; originalCGQring/callback/typedbatch token integration notbuilt orvalidated.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
