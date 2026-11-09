"""Actual typed batch callback plus provider catalog/publication functions.

Host fake IRQ/MMIO and VLAN verdicts. This proves finite catalog owner count and
no policy-denied forwarding/late cleanup; congestion retry behavior is an explicit
candidate change and physical firmware/recovery remains outside the fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_lhost_writer_serialization import PRELUDE

EXTRA=r'''
#define READ_ONCE(x) (x)
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
#define OMTQE_READY_READ_MAX 1024U
#define OMTQE_COMPLETE_READ_MAX 1024U
typedef uint32_t u32;
struct module{unsigned refs;bool deny;};
static struct module provider,consumer,foreign;
#define THIS_MODULE (&consumer)
static bool try_module_get(struct module*m){if(m->deny)return false;m->refs++;return true;}
static void module_put(struct module*m){assert(m->refs);m->refs--;}
struct omcgq_bank_token{u32 generation;struct module*owner;};
struct omcgq_batch_token{u32 generation;struct module*owner;};
static unsigned ready_reads,complete_reads,ready_on,complete_on,postsubmit,vlan_denied,egress_calls;
static int ready_state(void){if(postsubmit){complete_reads++;return!complete_on||complete_reads<complete_on;}ready_reads++;return!ready_on||ready_reads<ready_on;}
static void cpu_relax(void){}
'''
TEST=r'''
static void run_kind(unsigned k){(void)k;}
static void clear(void){memset(omcgq_held,0,sizeof(omcgq_held));omcgq_held_count=omcgq_unrecorded=omcgq_generation=omcgq_batch_generation=0;omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_owner=NULL;memset(&omcgq_batch,0,sizeof(omcgq_batch));provider.refs=consumer.refs=0;provider.deny=consumer.deny=false;irq_disabled=publications=collisions=queue_calls=drops=waits=pending_kind=scheduled_kind=inject_phase=injected=foreign_kind=foreign_inflight=0;ready_reads=complete_reads=postsubmit=vlan_denied=egress_calls=0;ready_on=complete_on=1;vlan_enabled=0;}
int main(void){unsigned cases=0;union topaz_tqe_cpuif_ppctl payload={0};struct omtqe_mcast_context ctx;struct omcgq_bank_token normal;payload.data.pkt=(void*)64;payload.data.length=64;
for(unsigned expected=1;expected<=135;expected++){
 clear();assert(omcgq_batch_admit(&consumer,&payload,expected,&ctx.batch));ctx.queue=NULL;
 for(unsigned n=0;n<expected;n++){postsubmit=0;ready_reads=complete_reads=0;omtqe_push_mcast_batch(&incoming,&ctx,1,n,0);assert(omcgq_held_count==1&&!omcgq_bank_acquire(&consumer,&normal));}
 assert(publications==expected&&omcgq_batch_finish(&ctx.batch)&&omcgq_held_count==0&&!omcgq_quarantined);cases++;
}
clear();omcgq_held_count=256;assert(!omcgq_batch_admit(&consumer,&payload,135,&ctx.batch)&&!publications);cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,135,&ctx.batch));ctx.queue=NULL;complete_on=0;
for(unsigned n=0;n<135;n++)omtqe_push_mcast_batch(&incoming,&ctx,1,n,0);
assert(publications==1&&complete_reads==1024&&omcgq_held_count==1&&omcgq_held[0].references==135&&omcgq_held[0].published&&!drops&&!irq_disabled);assert(omcgq_batch_finish(&ctx.batch)&&omcgq_held_count==1);cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,2,&ctx.batch));ctx.queue=(void*)1;vlan_enabled=1;vlan_denied=1;omtqe_push_mcast_batch(&incoming,&ctx,1,1,0);assert(!publications&&egress_calls==1&&!drops&&omcgq_quarantined&&omcgq_held_count==1);omtqe_push_mcast_batch(&incoming,&ctx,1,2,0);assert(egress_calls==1&&!drops&&omcgq_held_count==1);assert(omcgq_batch_finish(&ctx.batch));cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,2,&ctx.batch));ctx.queue=NULL;ready_on=0;omtqe_push_mcast_batch(&incoming,&ctx,1,1,0);assert(ready_reads==1024&&!publications&&omcgq_quarantined&&omcgq_held_count==1);cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,1,&ctx.batch));ctx.queue=NULL;omcgq_generation=~0U;omtqe_push_mcast_batch(&incoming,&ctx,1,1,0);assert(!publications&&omcgq_quarantined&&omcgq_held_count==1);assert(omcgq_batch_finish(&ctx.batch)&&omcgq_held_count==1);cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,1,&ctx.batch));ctx.queue=NULL;omtqe_push_mcast_batch(&incoming,&ctx,1,1,0);assert(publications==1);omtqe_push_mcast_batch(&incoming,&ctx,1,2,0);assert(publications==1&&omcgq_held_count==1);assert(omcgq_batch_finish(&ctx.batch)&&omcgq_held_count==0);cases++;
clear();assert(omcgq_batch_admit(&consumer,&payload,2,&ctx.batch));ctx.queue=NULL;omtqe_push_mcast_batch(&incoming,&ctx,1,1,0);assert(publications==1&&omcgq_batch_finish(&ctx.batch)&&omcgq_quarantined&&omcgq_held_count==1);assert(!omcgq_bank_acquire(&consumer,&normal));cases++;
printf("{\"cases\":%u}\n",cases);return0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];tqe=(a.candidate/'switch_tqe.c').read_text();cgq=(a.candidate/'topaz_congest_queue.c').read_text();start=cgq.index('#define OMCGQ_HELD_MAX');end=cgq.index('struct topaz_congest_queue *g_congest_queue_ptr',start);providerbody=cgq[start:end].replace('try_module_get(THIS_MODULE)','try_module_get(&provider)');h=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h').read_text();pub='\n'.join(function(h,s)for s in('topaz_tqe_cpuif_port_to_num(','__topaz_tqe_cpuif_ppctl_write(','__topaz_tqe_cpuif_tx_start(','\ntopaz_tqe_cpuif_tx_start('));pub='static int '+pub
 for name,typ in(('__topaz_tqe_cpuif_ppctl_write','int'),('__topaz_tqe_cpuif_tx_start','void'),('topaz_tqe_cpuif_tx_start','void')):pub=pub.replace('\n'+name+'(','\nstatic '+typ+' '+name+'(',1)
 funcs='\n'.join(function(tqe,s)for s in('static int omtqe_lhost_quarantined(','static int omtqe_lhost_submit_reserved(','static void omtqe_push_mcast_batch('));structbody='struct omtqe_mcast_context {\n void*queue;struct omcgq_batch_token batch;\n};\n';pre=PRELUDE.replace('static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}','static int ready_state(void);static int topaz_tqe_cpuif_tx_nready(void){return ready_state();}').replace('static void run_kind(unsigned kind);','static void run_kind(unsigned kind);static unsigned postsubmit;').replace('publications++;bank_writes[0]++;last_status=0;phase(9);','publications++;bank_writes[0]++;last_status=0;postsubmit=1;phase(9);').replace('static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;return 1;}','static unsigned vlan_denied,egress_calls;static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;egress_calls++;return!vlan_denied;}');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-typed-batch-publication.c';f.write_text(pre+EXTRA+providerbody+pub+structbody+funcs+TEST.replace('return0','return 0'));c=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(c.stderr);assert not c.returncode,c.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_TYPED_BATCH_BOUNDED_PUBLICATION_AND_OWNER_CATALOG','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'fanout_all1to135':True,'full_catalog_refusal_preownership':True,'partial135refs_onecatalog_owner':True,'VLANdenied_no_forward_no_HBM_drop':True,'no_catalog_growth_after_quarantine':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'FakeIRQ/MMIO/VLAN; congestionretry policychanged to quarantine; no foreignfirmware/recovery/physicalacceptance.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
