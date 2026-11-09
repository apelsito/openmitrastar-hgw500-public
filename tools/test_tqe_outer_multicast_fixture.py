"""Actual tqe_rx_multicast IP/FWT/decoder entry fixture, source-only host.

Uses the already-extracted actual provider/typed caller and inserts the exact
outer function, VLAN EtherType parser, IP MAC classifiers and packet structs.
No real MMIO/FWT/HBM is performed; lookup hooks return deterministic outcomes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

NET=r'''
#define likely(x) (x)
#define KERN_WARNING ""
#define ETH_P_IP 0x0800
#define ETH_P_IPV6 0x86dd
#define VLAN_HLEN 4
#define __constant_htons(x) ((uint16_t)(((x)>>8)|((x)<<8)))
static int qtn_ether_type_is_vlan(uint16_t type){return type==__constant_htons(0x8100)||type==__constant_htons(0x88a8);}
typedef int(*fwt_false_miss_cb)(unsigned,uint8_t);
static unsigned lookup_calls,hook_calls,miss_calls,lookup_timeout,lookup_valid,lookup_falsemiss,hook_present,hook_null,node_result;
static const void *hook_ip;
static uint16_t hook_type;
union topaz_fwt_lookup{struct{unsigned trig:1,unused:7,hash_addr:10,unused2:2,entry_addr:11,valid:1;}data;};
static union topaz_fwt_lookup topaz_fwt_hw_lookup_wait_be(const uint8_t*mac,int*timeout,uint8_t*miss){(void)mac;lookup_calls++;*timeout=lookup_timeout;*miss=lookup_falsemiss;union topaz_fwt_lookup r={0};r.data.valid=lookup_valid;r.data.entry_addr=3;return r;}
static int false_miss(unsigned entry,uint8_t value){assert(entry==3&&value==lookup_falsemiss);miss_calls++;return 0;}
static const struct topaz_fwt_sw_mcast_entry *lookup_hook(unsigned entry,const void*ip,uint16_t type);
static const struct topaz_fwt_sw_mcast_entry *(*g_tqe_fwt_get_mcast_hook)(unsigned,const void*,uint16_t);
static fwt_false_miss_cb g_tqe_fwt_false_miss_hook;
static int tqe_rx_get_node_id(const struct ether_header*eh){(void)eh;return node_result;}
'''

TEST=r'''
static struct topaz_fwt_sw_mcast_entry group;
static const struct topaz_fwt_sw_mcast_entry *lookup_hook(unsigned entry,const void*ip,uint16_t type){assert(entry==3);hook_calls++;hook_ip=ip;hook_type=type;return hook_null?NULL:&group;}
static unsigned char packet[160];
static union topaz_tqe_cpuif_descr make_packet(int ipv6,int vlan,unsigned length){
 memset(packet,0,sizeof(packet));struct ether_header*eh=(void*)packet;eh->ether_dhost[0]=ipv6?0x33:1;eh->ether_dhost[1]=ipv6?0x33:0;eh->ether_dhost[2]=ipv6?0:0x5e;
 eh->ether_type=__constant_htons(vlan?0x8100:(ipv6?ETH_P_IPV6:ETH_P_IP));unsigned offset=14;if(vlan){*(uint16_t*)(packet+16)=__constant_htons(ipv6?ETH_P_IPV6:ETH_P_IP);offset=18;}
 if(ipv6){struct qtn_ipv6*ip=(void*)(packet+offset);ip->next_hdr=17;}else{struct qtn_ipv4*ip=(void*)(packet+offset);ip->proto=17;}
 union topaz_tqe_cpuif_descr d={.data={.pkt=packet,.length=length,.in_port=0}};return d;
}
static void clear_outer(void){clear();lookup_calls=hook_calls=miss_calls=lookup_timeout=lookup_falsemiss=hook_null=0;lookup_valid=1;node_result=1;g_tqe_fwt_get_mcast_hook=lookup_hook;g_tqe_fwt_false_miss_hook=false_miss;memset(&group,0,sizeof(group));group.port_bitmap=2;}
int main(void){unsigned cases=0;union topaz_tqe_cpuif_descr d;
for(unsigned len=0;len<14;len++){clear_outer();d=make_packet(0,0,len);assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls&&!ec_writes&&!publications);cases++;}
for(unsigned len=14;len<34;len++){clear_outer();d=make_packet(0,0,len);assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls&&!ec_writes);cases++;}
for(unsigned len=14;len<54;len++){clear_outer();d=make_packet(1,0,len);assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls&&!ec_writes);cases++;}
for(unsigned type=0;type<2;type++)for(unsigned vlan=0;vlan<2;vlan++){
 clear_outer();d=make_packet(type,vlan,type?(vlan?58:54):(vlan?38:34));assert(tqe_rx_multicast(NULL,&d)==1&&lookup_calls==1&&hook_calls==1&&ec_value==1&&publications==1&&omcgq_held_count==0);cases++;
 clear_outer();d=make_packet(type,vlan,64);lookup_timeout=1;assert(tqe_rx_multicast(NULL,&d)==0&&lookup_calls==1&&!hook_calls&&!ec_writes);cases++;
 clear_outer();d=make_packet(type,vlan,64);lookup_valid=0;assert(tqe_rx_multicast(NULL,&d)==0&&lookup_calls==1&&!hook_calls&&!ec_writes);cases++;
 clear_outer();d=make_packet(type,vlan,64);hook_null=1;assert(tqe_rx_multicast(NULL,&d)==0&&hook_calls==1&&!ec_writes);cases++;
 clear_outer();d=make_packet(type,vlan,64);g_tqe_fwt_get_mcast_hook=NULL;assert(tqe_rx_multicast(NULL,&d)==0&&!hook_calls&&!ec_writes);cases++;
 clear_outer();d=make_packet(type,vlan,64);lookup_falsemiss=2;assert(tqe_rx_multicast(NULL,&d)==1&&miss_calls==1&&publications==1);cases++;
}
clear_outer();d=make_packet(0,0,34);((struct qtn_ipv4*)(packet+14))->proto=2;assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls&&!ec_writes);cases++;
clear_outer();d=make_packet(0,0,34);packet[0]=2;assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls);cases++;
clear_outer();d=make_packet(0,1,17);assert(tqe_rx_multicast(NULL,&d)==0&&!lookup_calls);cases++;
clear_outer();d=make_packet(0,0,34);omcgq_held_count=256;assert(tqe_rx_multicast(NULL,&d)==0&&lookup_calls==1&&!ec_writes&&!publications);cases++;
clear_outer();d=make_packet(0,0,34);complete_on=0;assert(tqe_rx_multicast(NULL,&d)==1&&publications==1&&ec_value==1&&omcgq_held_count==1&&omcgq_quarantined);cases++;
clear_outer();d=make_packet(0,0,34);d.data.in_port=5;group.flood_forward=1;node_result=0;assert(tqe_rx_multicast(NULL,&d)==0&&!ec_writes);cases++;
clear_outer();d=make_packet(0,0,34);d.data.in_port=5;group.flood_forward=1;node_result=3;assert(tqe_rx_multicast(NULL,&d)==0&&!ec_writes);cases++;
printf("{\"cases\":%u}\n",cases);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--fullcaller-fixture',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];source=(a.candidate/'switch_tqe.c').read_text();base=a.fullcaller_fixture.read_text().split('int main(void)',1)[0];base=base.replace('uint8_t dest[6],src[6]','uint8_t ether_dhost[6],ether_shost[6]').replace('uint8_t port_bitmap;','uint8_t port_bitmap;unsigned flood_forward;');packet=(root/'work/sources/Quantenna-GPL/include/qtn/qtn_net_packet.h').read_text();packet=packet[packet.index('union qtn_ipv4_addr {'):packet.index('RUBY_INLINE uint8_t qtn_ipv6_tclass')];ip=(root/'work/sources/Quantenna-GPL/include/qtn/iputil.h').read_text();classifiers=function(ip,'static inline int iputil_mac_is_v6_multicast(')+function(ip,'static inline int iputil_mac_is_v4_multicast(');parser='const uint16_t *'+function(source,'tqe_rx_ether_type_skip_vlan(');outer=function(source,'int __sram_text tqe_rx_multicast(');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-outer-ip-fwt-multicast.c';f.write_text(base+NET+packet+'\n#define QTN_IP_PROTO_IGMP 2\n'+classifiers+parser+outer+TEST);b=subprocess.run([str(a.compiler),'-std=c11','-O1',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_OUTER_IP_FWT_MULTICAST_ENTRY_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'actual_outer_entry_and_VLANparser':True,'actual_IPMAC_classifiers_packet_structs':True,'FWT_lookup_valid_invalid_timeout_hooks':True,'refcount_mutation_guard_and_partial_retention':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'FWT/MMIO/cache/refcount writes fake; malformedbounds andselectedhookstates tested, notallIP/FWT/foreignhardwarecases orphysicalacceptance.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
