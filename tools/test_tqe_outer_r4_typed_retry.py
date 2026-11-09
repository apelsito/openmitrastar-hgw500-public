"""Actual R4 outerIP/FWT->typedinitial->CGQretry chain fixture, host only.

Boundaries/hooks are deterministic fakes, while selected outer/parser/IP structs,
OEM enumerators, provider credits/markers, TQE writer and queueconsumer are real.
No hardware/refcount release/reset acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_outer_multicast_fixture import NET,TEST as OUTER_TEST

COUNT=r'''
#define TOPAZ_TQE_FIRST_PORT 0
#define TOPAZ_TQE_MUC_PORT 5
#define TOPAZ_FWT_SW_NODE_BITMAP_SIZE 4
#define TOPAZ_BITS_PER_WD 32
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define unlikely(x) (x)
#define printk_ratelimit() 0
#define printk(...) ((void)0)
#define KERN_CRIT ""
struct ether_header{uint8_t ether_dhost[6],ether_shost[6];uint16_t ether_type;};
struct topaz_fwt_sw_mcast_entry{uint32_t node_bitmap[4];uint8_t port_bitmap;unsigned flood_forward;};
static unsigned ec_writes,ec_value,fc_value,cache_ops;
static void tqe_buf_set_refcounts(void*p,int enq,int free_){(void)p;ec_writes++;ec_value=enq;fc_value=free_;assert(omcgq_batch.active&&omcgq_retained&&omcgq_held_count==1);}
static void flush_and_inv_dcache_range(uintptr_t a,uintptr_t b){assert(b>=a);cache_ops++;}
static int topaz_fwt_sw_mcast_port_has_nodes(uint8_t port){return port==2;}
'''
RETRY=r'''
clear_outer();memset(&cgq,0,sizeof(cgq));cgq.xmit_func=ordinary;d=make_packet(0,0,34);last_status=0x40000000U;
assert(tqe_rx_multicast(&cgq,&d)==1&&ec_value==1&&publications==1&&queue.qlen==1&&omcgq_queue_pending==1&&omcgq_batch.active&&!omcgq_quarantined);cases++;
last_status=0;postsubmit=0;ready_reads=complete_reads=0;queue.last_retry_success=1;assert(topaz_congest_queue_xmit(&queue,1)==1&&publications==2&&queue.qlen==0&&omcgq_queue_pending==0&&omcgq_held_count==0&&dequeues==1);cases++;
clear_outer();memset(&cgq,0,sizeof(cgq));cgq.xmit_func=ordinary;cgq.total_qlen=2048;d=make_packet(0,0,34);assert(tqe_rx_multicast(&cgq,&d)==0&&lookup_calls==1&&!ec_writes&&!publications&&!omcgq_batch.active);cases++;
clear_outer();memset(&cgq,0,sizeof(cgq));cgq.xmit_func=ordinary;d=make_packet(0,0,34);last_status=0x40000000U;assert(tqe_rx_multicast(&cgq,&d)==1&&queue.qlen==1);postsubmit=0;complete_on=0;queue.last_retry_success=1;assert(topaz_congest_queue_xmit(&queue,1)==0&&publications==2&&omcgq_quarantined&&queue.qlen==1&&omcgq_held_count==1&&!dequeues);cases++;
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--initial-retry-fixture',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];t=(a.candidate/'switch_tqe.c').read_text();base=a.initial_retry_fixture.read_text().split('int main(void)',1)[0];packet=(root/'work/sources/Quantenna-GPL/include/qtn/qtn_net_packet.h').read_text();packet=packet[packet.index('union qtn_ipv4_addr {'):packet.index('RUBY_INLINE uint8_t qtn_ipv6_tclass')];ip=(root/'work/sources/Quantenna-GPL/include/qtn/iputil.h').read_text();classifier=function(ip,'static inline int iputil_mac_is_v6_multicast(')+function(ip,'static inline int iputil_mac_is_v4_multicast(');fwt=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_fwt_cpuif.h').read_text();enum='\n'.join(typ+' '+function(fwt,s)for typ,s in [('static uint8_t','topaz_fwt_sw_count_bits('),('static int','topaz_fwt_sw_mcast_node_is_set('),('static uint32_t','topaz_fwt_sw_mcast_enqueues('),('static uint32_t','topaz_fwt_sw_mcast_do_per_node(')]);caller=function(t,'static uint32_t __sram_text tqe_push_mc_ports(');parser='const uint16_t *'+function(t,'tqe_rx_ether_type_skip_vlan(');outer=function(t,'int __sram_text tqe_rx_multicast(');test=OUTER_TEST.replace('int main(void){unsigned cases=0;union topaz_tqe_cpuif_descr d;','int main(void){unsigned cases=0;union topaz_tqe_cpuif_descr d;struct topaz_congest_queue cgq;').replace('clear();lookup_calls','clear();ec_writes=ec_value=fc_value=cache_ops=0;lookup_calls');marker='printf("{\\"cases\\":%u}\\n",cases);return 0;}';assert marker in test;test=test.replace(marker,RETRY+marker,1);a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-R4-outer-typed-retry.c';f.write_text(base+COUNT+NET+packet+'\n#define QTN_IP_PROTO_IGMP 2\n'+classifier+enum+caller+parser+outer+test);c=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(c.stderr);assert not c.returncode,c.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_R4_OUTER_IP_FWT_TYPED_INITIAL_QUEUE_RETRY_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'selected_source_sha256':hashlib.sha256((a.candidate/'switch_tqe.c').read_bytes()).hexdigest(),'actual_IPFWT_outer_and_decoder':True,'actual_credit_preEC_and_typedcaller':True,'confirmed_CN_to_sameownedqueue_then_success':True,'fullqueue_refusal_before_EC':True,'retry_unknown_payload_retained':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'FakeFWT/MMIO/cache/HBM/VLAN/queueallocator; selectedmalformed/hook/credit states only, no allpacket/allnodes/foreignhardware/recoveryacceptance.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
