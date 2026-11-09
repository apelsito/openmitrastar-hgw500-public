"""Extract actual R3 multicast caller + OEM enumeration + typed callback fixture.

No hardware. Tests refcount mutation ordering, actual output enumeration, finite
catalog admission and retained owner count. Encoders/MMIO/HBM cache are fakes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_r3_actual_typed_publication import EXTRA
from test_tqe_lhost_writer_serialization import PRELUDE

CALLER_PRE=r'''
#define TOPAZ_TQE_FIRST_PORT 0
#define TOPAZ_TQE_MUC_PORT 5
#define TOPAZ_FWT_SW_NODE_BITMAP_SIZE 4
#define TOPAZ_BITS_PER_WD 32
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define unlikely(x) (x)
#define printk_ratelimit() 0
#define printk(...) ((void)0)
#define KERN_CRIT ""
struct ether_header{uint8_t dest[6],src[6];uint16_t ether_type;};
struct topaz_fwt_sw_mcast_entry{uint32_t node_bitmap[4];uint8_t port_bitmap;};
static unsigned ec_writes,ec_value,fc_value,cache_ops;
static void tqe_buf_set_refcounts(void*p,int enq,int free_){(void)p;ec_writes++;ec_value=enq;fc_value=free_;assert(omcgq_batch.active&&omcgq_retained&&omcgq_held_count==1);}
static void flush_and_inv_dcache_range(uintptr_t a,uintptr_t b){assert(b>=a);cache_ops++;}
static int topaz_fwt_sw_mcast_port_has_nodes(uint8_t port){return port==2;}
'''
TEST=r'''
static void run_kind(unsigned k){(void)k;}
static void clear(void){memset(omcgq_held,0,sizeof(omcgq_held));omcgq_held_count=omcgq_unrecorded=omcgq_generation=omcgq_batch_generation=0;omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_owner=NULL;memset(&omcgq_batch,0,sizeof(omcgq_batch));provider.refs=consumer.refs=0;provider.deny=consumer.deny=false;irq_disabled=publications=collisions=queue_calls=drops=waits=pending_kind=scheduled_kind=inject_phase=injected=foreign_kind=foreign_inflight=0;ready_reads=complete_reads=postsubmit=vlan_denied=egress_calls=ec_writes=ec_value=fc_value=cache_ops=0;ready_on=complete_on=1;vlan_enabled=0;}
int main(void){unsigned cases=0;struct topaz_fwt_sw_mcast_entry e;union topaz_tqe_cpuif_descr d={.data={.pkt=(void*)64,.length=64,.in_port=0,.buff_ptr_offset=0}};
for(unsigned ports=1;ports<256;ports++){
 clear();memset(&e,0,sizeof(e));e.port_bitmap=ports;
 unsigned expected=topaz_fwt_sw_mcast_enqueues(&e,(uint8_t)ports,0,0);unsigned actual=tqe_push_mc_ports(NULL,&e,&d,0,0,0);
 assert(actual==expected);if(expected)assert(ec_writes==1&&ec_value==expected&&publications==expected&&omcgq_held_count==0);else assert(!ec_writes&&!publications);cases++;
}
clear();memset(&e,0,sizeof(e));e.port_bitmap=0xff;for(unsigned i=0;i<4;i++)e.node_bitmap[i]=~0U;
assert(tqe_push_mc_ports(NULL,&e,&d,0,0,0)==134&&ec_value==134&&publications==134&&!omcgq_held_count);cases++;
clear();omcgq_held_count=256;memset(&e,0,sizeof(e));e.port_bitmap=2;assert(tqe_push_mc_ports(NULL,&e,&d,0,0,0)==0&&!ec_writes&&!publications);cases++;
clear();complete_on=0;memset(&e,0,sizeof(e));e.port_bitmap=0xff;for(unsigned i=0;i<4;i++)e.node_bitmap[i]=~0U;
assert(tqe_push_mc_ports(NULL,&e,&d,0,0,0)==134&&ec_value==134&&publications==1&&omcgq_held_count==1&&omcgq_held[0].references==134&&omcgq_quarantined&&!drops&&!irq_disabled);cases++;
clear();provider.deny=true;memset(&e,0,sizeof(e));e.port_bitmap=2;assert(tqe_push_mc_ports(NULL,&e,&d,0,0,0)==0&&!ec_writes&&!publications&&!consumer.refs);cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];t=(a.candidate/'switch_tqe.c').read_text();q=(a.candidate/'topaz_congest_queue.c').read_text();h=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h').read_text();fw=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_fwt_cpuif.h').read_text();start=q.index('#define OMCGQ_HELD_MAX');end=q.index('struct topaz_congest_queue *g_congest_queue_ptr',start);providerbody=q[start:end].replace('try_module_get(THIS_MODULE)','try_module_get(&provider)');pub='\n'.join(function(h,s)for s in('topaz_tqe_cpuif_port_to_num(','__topaz_tqe_cpuif_ppctl_write(','__topaz_tqe_cpuif_tx_start(','\ntopaz_tqe_cpuif_tx_start('));pub='static int '+pub
 for name,typ in(('__topaz_tqe_cpuif_ppctl_write','int'),('__topaz_tqe_cpuif_tx_start','void'),('topaz_tqe_cpuif_tx_start','void')):pub=pub.replace('\n'+name+'(','\nstatic '+typ+' '+name+'(',1)
 enum='\n'.join(typ+' '+function(fw,name)for typ,name in [('static uint8_t','topaz_fwt_sw_count_bits('),('static int','topaz_fwt_sw_mcast_node_is_set('),('static uint32_t','topaz_fwt_sw_mcast_enqueues('),('static uint32_t','topaz_fwt_sw_mcast_do_per_node(')])
 funcs='\n'.join(function(t,s)for s in('static int omtqe_lhost_quarantined(','static int omtqe_lhost_submit_reserved(','static void omtqe_push_mcast_batch(','static uint32_t __sram_text tqe_push_mc_ports('));structs='struct omtqe_mcast_context{void*queue;struct omcgq_batch_token batch;};\n';pre=PRELUDE.replace('static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}','static int ready_state(void);static int topaz_tqe_cpuif_tx_nready(void){return ready_state();}').replace('static void run_kind(unsigned kind);','static void run_kind(unsigned kind);static unsigned postsubmit;').replace('publications++;bank_writes[0]++;last_status=0;phase(9);','publications++;bank_writes[0]++;last_status=0;postsubmit=1;phase(9);').replace('static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;return 1;}','static unsigned vlan_denied,egress_calls;static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;egress_calls++;return!vlan_denied;}');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-full-multicast-caller.c';f.write_text(pre+EXTRA+providerbody+pub+CALLER_PRE+enum+structs+funcs+TEST);c=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(c.stderr);assert not c.returncode,c.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_FULL_MULTICAST_CALLER_AND_ENUMERATION_TYPED_OWNERSHIP','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'caller_function_actual':True,'OEM_enumerators_actual':4,'pre_ec_catalog_and_module_pin_order_asserted':True,'max_fanout134_actual_inputEMAC0':True,'timeoutallrefs_single_owner':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'FakeMMIO/HBMcache/IEmetadata only; no firmwarebus/recovery/physicalacceptance.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
