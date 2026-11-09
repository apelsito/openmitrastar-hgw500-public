"""Actual CGQ provider and TQE four-writer bounded protocol fixture, host only.

Combines actual owner/ledger/pin functions with extracted CPUIF writes and all
four source writer paths. IRQ/MMIO/HBM/module references are deterministic fakes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_bounded_local_ownership import BOUNDED, TESTS
from test_tqe_lhost_writer_serialization import PRELUDE

MODULES = r'''
typedef uint32_t u32;
struct module {unsigned refs;bool deny;};
static struct module om_provider,om_consumer;
#define THIS_MODULE (&om_consumer)
static bool try_module_get(struct module*m){if(m->deny)return false;m->refs++;return true;}
static void module_put(struct module*m){assert(m->refs);m->refs--;}
struct omcgq_bank_token{uint32_t generation;struct module *owner;};
struct omcgq_batch_token{uint32_t generation;struct module *owner;};
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=(a.candidate/'switch_tqe.c').read_text();queue=(a.candidate/'topaz_congest_queue.c').read_text()
    h=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h').read_text()
    pub='\n'.join(function(h,s)for s in('topaz_tqe_cpuif_port_to_num(','__topaz_tqe_cpuif_ppctl_write(','__topaz_tqe_cpuif_tx_start(','\ntopaz_tqe_cpuif_tx_start('))
    pub='static int '+pub
    for name,typ in(('__topaz_tqe_cpuif_ppctl_write','int'),('__topaz_tqe_cpuif_tx_start','void'),('topaz_tqe_cpuif_tx_start','void')):pub=pub.replace('\n'+name+'(','\nstatic '+typ+' '+name+'(',1)
    begin=queue.index('#define OMCGQ_HELD_MAX');end=queue.index('struct topaz_congest_queue *g_congest_queue_ptr',begin)
    provider=queue[begin:end].replace('try_module_get(THIS_MODULE)','try_module_get(&om_provider)')
    funcs='\n'.join(function(source,s)for s in('static int omtqe_lhost_quarantined(','static int omtqe_lhost_reserve(','static void omtqe_lhost_cancel_reservation(','static int omtqe_lhost_submit_reserved(','static int omtqe_lhost_submit(','int topaz_tqe_xmit(','static void __sram_text tqe_push_mcast(','static int topaz_swfwd_tqe_xmit(','static int tqe_tx_buf(','int tqe_tx('))
    pre=PRELUDE.replace('static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}','static int ready_state(void);\nstatic int topaz_tqe_cpuif_tx_nready(void){return ready_state();}')
    pre=pre.replace('static int vlan_enabled,g_dscp_flag,g_dscp_value[2];','static int vlan_enabled,g_dscp_flag,g_dscp_value[2],vlan_denied;static unsigned egress_calls;')
    pre=pre.replace('static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;return 1;}','static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;egress_calls++;return !vlan_denied;}')
    pre=pre.replace('static uint32_t qtn_mproc_sync_mem_read(uint32_t address){assert(address==0xe1034038U);phase(10);return last_status;}','static int status_state(uint32_t address);\nstatic uint32_t qtn_mproc_sync_mem_read(uint32_t address){return status_state(address);}')
    pre=pre.replace('static void run_kind(unsigned kind);','static void run_kind(unsigned kind);\nstatic void reset(void);\nstatic unsigned postsubmit;')
    pre=pre.replace('publications++;bank_writes[0]++;last_status=0;phase(9);','publications++;bank_writes[0]++;last_status=0;postsubmit=1;phase(9);')
    bounded=BOUNDED.replace('static bool omtqe_bank_reserved,omtqe_bank_quarantined,omtqe_held_published;','')
    bounded=bounded.replace('static union topaz_tqe_cpuif_ppctl omtqe_held_descriptor;','')
    test=TESTS.replace('omtqe_bank_reserved','omcgq_reserved').replace('omtqe_bank_quarantined','omcgq_quarantined').replace('omtqe_held_published','omcgq_held[0].published')
    test=test.replace('reset();omcgq_reserved=omcgq_quarantined=omcgq_held[0].published=false;','reset();omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_generation=omcgq_held_count=omcgq_unrecorded=0;omcgq_owner=NULL;om_provider.refs=om_consumer.refs=0;')
    test=test.replace('memset(&omtqe_held_descriptor,0,sizeof(omtqe_held_descriptor));','memset(omcgq_held,0,sizeof(omcgq_held));')
    marker=' printf("{\\"executed_cases\\":%u}\\n",cases);return 0;'
    # Actual multicast callback must retain before VLAN can reach HBM drop.
    additions='''
 clear_all();complete_on=0;assert(topaz_tqe_xmit(&p)==OMTQE_OWNERSHIP_UNCERTAIN);union topaz_tqe_cpuif_ppctl held_first=omcgq_held[0].descriptor;unsigned held_before=omcgq_held_count;vlan_enabled=1;vlan_denied=1;egress_calls=0;drops=0;
 tqe_push_mcast(&incoming,NULL,1,3,0);assert(egress_calls==0&&drops==0&&publications==1&&omcgq_held_count==held_before+1&&!memcmp(&held_first,&omcgq_held[0].descriptor,sizeof(held_first)));cases++;
 tqe_push_mcast(&incoming,(void*)1,1,4,0);assert(egress_calls==0&&drops==0&&publications==1&&!memcmp(&held_first,&omcgq_held[0].descriptor,sizeof(held_first)));cases++;
 vlan_enabled=0;vlan_denied=0;
'''
    assert marker in test
    test=test.replace(marker,additions+marker,1)
    a.output.mkdir(parents=True,exist_ok=False);fixture=a.output/'actual-provider-and-four-writers.c';fixture.write_text(pre+bounded+MODULES+provider+pub+funcs+test)
    compiled=subprocess.run([str(a.compiler),'-std=c11','-O1',str(fixture),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(compiled.stderr);assert not compiled.returncode,compiled.stderr.decode()
    tested=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(tested.stderr);assert not tested.returncode,tested.stderr.decode()
    result={'status':'PASS_ACTUAL_PROVIDER_AND_FOUR_WRITER_BOUNDED_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(tested.stdout)['executed_cases'],'module_tokens_and_pins_actual_functions':True,'irq_read_budgets_1024':True,'postsubmit_unknown_retained_never_CN':True,'foreign_bank_writer_counterexample_reproduced':True,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'limits':'Actual source with fake module/MMIO/HBM callbacks; no physical/foreign firmware/retention recovery acceptance.'}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
