"""Execute actual recovered public-coexistence parser and policy consumer.

Fixture validates payload lengths before node mutation, channel-report bounds,
independent AP downgrade decisions, STA info/exemption handling and disabled
policy. Fake callbacks do not prove RX interrupt, RF or bandwidth completion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_input.c';text=source.read_text();start=text.index('static void\nieee80211_recv_action_public_coex(');end=text.index('/*\n * Process a public action frame',start);helper=text[start:end]
 c=r'''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint8_t u_int8_t;typedef uint8_t uint8_t;
#define READ_ONCE(x) (x)
#define IEEE80211_M_STA 1
#define IEEE80211_ELEMID_20_40_BSS_COEX 72
#define IEEE80211_ELEMID_20_40_IT_CH_REP 73
#define WLAN_20_40_BSS_COEX_INFO_REQ 1
#define WLAN_20_40_BSS_COEX_40MHZ_INTOL 2
#define WLAN_20_40_BSS_COEX_20MHZ_WIDTH_REQ 4
#define WLAN_20_40_BSS_COEX_OBSS_EXEMPT_REQ 8
#define WLAN_20_40_BSS_COEX_OBSS_EXEMPT_GRNT 16
#define IEEE80211_ACTION_CAT_PUBLIC 4
#define IEEE80211_ACTION_PUB_20_40_COEX 0
#define IEEE80211_FC0_SUBTYPE_ACTION 0xd0
#define WLAN_COEX_STATS_BW_ACTION 0
#define BW_HT20 20
#define IEEE80211_MSG_INPUT 0
#define IEEE80211_DISCARD(...) do{}while(0)
struct ieee80211com {int ic_opmode,ic_phymode;uint8_t om_20_40_bss_coex;int ic_obss_timer;void(*ic_coex_stats_update)(struct ieee80211com*,uint32_t);};
struct ieee80211vap {struct ieee80211com*iv_ic;uint8_t iv_coex;struct {unsigned is_rx_elem_toosmall,is_rx_elem_unknown;}iv_stats;};
struct ieee80211_node {struct ieee80211vap*ni_vap;uint8_t ni_coex;};
struct sk_buff {uint8_t*data;unsigned len;};
struct ieee80211_frame {int unused;};
struct ieee80211_action {uint8_t ia_category,ia_action;};
struct ieee80211_20_40_coex_param {uint8_t param_id,param_len,coex_param;};
struct ieee80211_20_40_in_ch_rep {uint8_t param_id,param_len,reg;uint8_t chan[0];};
struct ieee80211_action_data {int cat,action;void*params;};
#define IEEE80211_IS_11NG_40(ic) ((ic)->ic_phymode==9)
static unsigned sends,cancels,bw,stats,report_calls,grant_calls;static int report_bad;
#define IEEE80211_SEND_MGMT(ni,type,arg) do{assert((type)==0xd0);sends++;}while(0)
static int del_timer_sync(int*p){cancels++;return 0;}
static int ieee80211_is_40_allowed(struct ieee80211vap*v,int channel){report_calls++;return channel!=report_bad;}
static void om_ieee80211_change_bw(struct ieee80211vap*v,int value,int delay){assert(value==20&&delay==0&&stats==0);bw++;}
static void stats_cb(struct ieee80211com*ic,uint32_t reason){assert(bw==1&&reason==0);stats++;}
static int is_ieee80211_obss_grant(struct ieee80211com*ic,struct ieee80211_node*ni){grant_calls++;return 16;}
'''+helper+r'''
int main(void){struct ieee80211com ic;struct ieee80211vap v;struct ieee80211_node ni;struct ieee80211_frame wh;uint8_t bytes[300];unsigned len,declared,flags,role,policy,mode,reportkind;unsigned long cases=0;
for(len=0;len<18;len++)for(declared=0;declared<256;declared++)for(flags=0;flags<32;flags++)for(role=0;role<2;role++)for(policy=0;policy<2;policy++)for(mode=0;mode<2;mode++)for(reportkind=0;reportkind<3;reportkind++){
memset(&ic,0,sizeof(ic));memset(&v,0,sizeof(v));memset(bytes,0,sizeof(bytes));ic.ic_opmode=role?1:6;ic.ic_phymode=mode?9:8;ic.om_20_40_bss_coex=policy;ic.ic_coex_stats_update=stats_cb;v.iv_ic=&ic;v.iv_coex=7;ni.ni_vap=&v;ni.ni_coex=0xa5;struct ieee80211_action*ia=(void*)bytes;uint8_t*p=bytes+2;p[0]=72;p[1]=1;p[2]=flags;p[3]=reportkind?73:99;p[4]=declared;p[5]=81;for(unsigned i=6;i<sizeof(bytes)-2;i++)p[i]=(uint8_t)i;report_bad=reportkind==2?6:-1;struct sk_buff skb={bytes,len+2};sends=cancels=bw=stats=report_calls=grant_calls=0;
bool_valid:;
int valid=len>=3;
if(valid&&len>=5&&reportkind){if(declared<1||declared>(len-5))valid=0;}
unsigned expected_reports=0;int report_change=0;if(valid&&!role&&len>=6&&reportkind){unsigned limit=declared-1;for(unsigned i=0;i<limit;i++){expected_reports++;if((uint8_t)(6+i)==report_bad){report_change=1;break;}}}
ieee80211_recv_action_public_coex(&ni,&skb,&wh,ia,0);
if(!valid){assert(ni.ni_coex==0xa5&&v.iv_stats.is_rx_elem_toosmall==1&&!bw&&!stats&&!sends&&!cancels&&!report_calls&&!grant_calls);}
else{assert(ni.ni_coex==flags&&!v.iv_stats.is_rx_elem_toosmall&&!v.iv_stats.is_rx_elem_unknown);if(role){assert(sends==!!(flags&1)&&cancels==!!(flags&16)&&!bw&&!stats&&!report_calls&&!grant_calls);}else{unsigned change=(report_change||!!(flags&6))&&policy&&mode;assert(report_calls==expected_reports&&bw==change&&stats==change&&sends==!!(flags&8)&&grant_calls==!!(flags&8)&&!cancels);}}
cases++;}
assert(cases==3538944UL);
for(unsigned n=0;n<256;n++){memset(&ic,0,sizeof(ic));memset(&v,0,sizeof(v));v.iv_ic=&ic;ni.ni_vap=&v;ni.ni_coex=123;memset(bytes,0,sizeof(bytes));bytes[2]=72;bytes[3]=n;bytes[4]=6;struct sk_buff skb={bytes,5};sends=cancels=bw=stats=0;ieee80211_recv_action_public_coex(&ni,&skb,&wh,(void*)bytes,0);if(n!=1)assert(ni.ni_coex==123&&v.iv_stats.is_rx_elem_unknown==1&&!bw&&!sends);}
return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);pins={str(source):sha(source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(proc.stderr);assert proc.returncode==0,(proc.returncode,proc.stderr)
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_COEX449_PUBLIC_ACTION_LENGTH_POLICY_CONSUMER',hardware_accessed=False,firmware_eligible=False,cases=3538944,coex_length_cases=256,source_sha256=sha(source),function_sha256=hashlib.sha256(helper.encode()).hexdigest(),limits='Actualparserbody/fakeBW+stats/send/cancelcallbacks; validcallbackobjectrange only; noPHY/RX/RF/trafficacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
