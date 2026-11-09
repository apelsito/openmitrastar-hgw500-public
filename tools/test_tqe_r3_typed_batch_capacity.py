"""Actual provider R3 batch/catalog/token/pin fixture, host-only.

No firmware/MMIO. This tests catalog capacity and owner admission, not VLAN,
congestion retry policy or complete multicast publication until integrated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from test_tqe_provider_lifecycle import PRE as MODULE_PRE

TEST=r'''
static void reset_state(void){memset(omcgq_held,0,sizeof(omcgq_held));omcgq_held_count=omcgq_unrecorded=omcgq_generation=0;omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_owner=NULL;memset(&omcgq_batch,0,sizeof(omcgq_batch));omcgq_batch_generation=0;consumer.refs=provider.refs=foreign.refs=0;consumer.deny=provider.deny=false;irqstate=0;}
int main(void){unsigned cases=0;struct omcgq_batch_token b,bad;struct omcgq_bank_token bank,normal;union topaz_tqe_cpuif_ppctl payload={{1,2,3,4,5,6}};
for(unsigned held=0;held<=256;held++)for(unsigned refs=0;refs<=136;refs++){
 reset_state();omcgq_held_count=held;int expected=held<256&&refs>0&&refs<=135;assert(omcgq_batch_admit(&consumer,&payload,refs,&b)==expected);
 if(expected){assert(consumer.refs==1&&provider.refs==1&&omcgq_held_count==held+1&&omcgq_held[held].references==refs);assert(!omcgq_bank_acquire(&consumer,&normal));assert(!omcgq_batch_admit(&consumer,&payload,1,&bad));assert(omcgq_batch_valid(&b));bad=b;bad.owner=&foreign;assert(!omcgq_batch_acquire(&bad,&bank));assert(omcgq_batch_acquire(&b,&bank));assert(omcgq_bank_cancel(&bank));for(unsigned n=0;n<refs;n++)assert(omcgq_batch_complete(&b,true));assert(!omcgq_batch_complete(&b,true));assert(omcgq_batch_finish(&b)&&omcgq_held_count==held&&!omcgq_batch.active);}
 assert(!irqstate);cases++;
}
reset_state();assert(omcgq_batch_admit(&consumer,&payload,135,&b));assert(omcgq_batch_acquire(&b,&bank));assert(omcgq_bank_quarantine(&bank,&payload,true));assert(omcgq_held_count==1);for(unsigned n=0;n<135;n++)assert(omcgq_batch_complete(&b,n==0));assert(omcgq_batch_finish(&b)&&omcgq_held_count==1&&omcgq_held[0].references==135&&omcgq_held[0].published);cases++;
assert(!omcgq_batch_admit(&consumer,&payload,1,&bad)&&!omcgq_bank_acquire(&consumer,&normal));cases++;
reset_state();provider.deny=true;assert(!omcgq_batch_admit(&consumer,&payload,1,&b)&&!consumer.refs&&!provider.refs&&!omcgq_held_count);cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();src=(a.candidate/'topaz_congest_queue.c').read_text();start=src.index('#define OMCGQ_HELD_MAX');end=src.index('struct topaz_congest_queue *g_congest_queue_ptr',start);provider=src[start:end];pre=MODULE_PRE.replace('struct omcgq_bank_token {u32 generation;struct module*owner;};','struct omcgq_bank_token {u32 generation;struct module*owner;};\nstruct omcgq_batch_token {u32 generation;struct module*owner;};');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-provider-batch.c';f.write_text(pre+provider+TEST);b=subprocess.run([str(a.compiler),'-std=c11','-O1',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_TYPED_BATCH_CATALOG_CAPACITY_SOURCE_ONLY','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'ledger_not_enlarged':256,'max_outputs_per_payload':135,'pins_before_batch_ownership':True,'normal_nestedbankwriters_refused':True,'slot_reserved_before_ec_mutation':True,'partial_batch_quarantine_single_owner_all_refs':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'ProvidercapacityAPIonly; multicastVLANpolicy/congestion/4writer/MMIOfixture+complete modulebuild pending.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
