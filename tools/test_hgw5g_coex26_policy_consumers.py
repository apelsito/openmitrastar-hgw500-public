"""Execute actual Coex26 timer, scan consumer and recv-mgmt gate fragments.

Independent expected decisions cover disabled/enabled policy, phymode, opmode,
scan inventory, HT intolerance, BSS identity and neighboring legacy beacons.
Only exact recovered decision fragments are extracted from the candidate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def balanced(text,start):
 brace=text.index('{',start);depth=1;i=brace+1
 while depth:depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[start:i]

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);wp=a.candidate/'source/wlan/ieee80211_wireless.c';ip=a.candidate/'source/wlan/ieee80211_input.c';w=wp.read_text();t=ip.read_text();timer=balanced(w,w.index('void ieee80211_start_obss_scan_timer('));scan=balanced(t,t.index('int\nieee80211_check_mode('));assoc=balanced(t,t.index('if (READ_ONCE(ic->om_20_40_bss_coex) &&'));sta=balanced(t,t.index('if ((ic->ic_opmode == IEEE80211_M_STA) &&\n\t\t\t\t\tREAD_ONCE(ic->om_20_40_bss_coex)'));nonht=balanced(t,t.index('if (ic->ic_curmode == IEEE80211_MODE_11NG_HT40PM &&\n\t\t\t\t    READ_ONCE(ic->om_20_40_bss_coex)'))
 c=r'''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdbool.h>
typedef uint8_t uint8_t;
#define READ_ONCE(x) (x)
#define IEEE80211_M_STA 1
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_MODE_11NG_HT40PM 9
#define IEEE80211_IS_11NG_40(ic) ((ic)->ic_phymode==9)
#define IEEE80211_OBSS_AP_SCAN_INT 25
#define IEEE80211_CHAN_MAX 255
#define HZ 200
#define EINVAL 22
#define BW_HT20 20
#define WLAN_COEX_STATS_BW_SCAN 2
#define WLAN_COEX_STATS_BW_ASSOC 1
#define WLAN_20_40_BSS_COEX_40MHZ_INTOL 2
#define WLAN_20_40_BSS_COEX_20MHZ_WIDTH_REQ 4
#define IEEE80211_HTCAP_C_40_INTOLERANT 0x4000
#define IEEE80211_ADDR_EQ(a,b) (!memcmp((a),(b),6))
struct scanbase {unsigned id;uint8_t pri,sec;bool permitted;};
struct ap_scan_entry {struct scanbase base;struct ap_scan_entry*ase_list;};
struct head {struct ap_scan_entry*first;};
struct ap_state {struct {struct head asl_head;}as_scan_list[255];};
struct ieee80211_scan_state {void*ss_priv;};
struct ieee80211vap;
struct ieee80211_node {uint8_t ni_macaddr[6],ni_coex;struct {uint16_t cap;}ni_htcap;struct {uint8_t choffset;}ni_htinfo;};
struct ieee80211com {int ic_opmode,ic_phymode,ic_curmode,ic_obss_timer;uint8_t om_20_40_bss_coex,ic_obss_scan_enable,ic_obss_scan_count;struct ieee80211vap*ic_obss_vap;struct ieee80211_scan_state*ic_scan;void(*ic_coex_stats_update)(struct ieee80211com*,uint32_t);};
struct ieee80211vap {struct ieee80211com*iv_ic;struct ieee80211_node*iv_bss;};
#define TAILQ_FOREACH(x,h,n) for((x)=(h)->first;(x);(x)=(x)->n)
static unsigned timers,bw,stats,visited;static unsigned long expiry,jiffies=123;static unsigned lastid;static bool selected;
static void mod_timer(int*p,unsigned long v){timers++;expiry=v;}
static void ieee80211_find_ht_pri_sec_chan(struct ieee80211vap*v,struct scanbase*b,uint8_t*p,uint8_t*s){*p=b->pri;*s=b->sec;selected=b->permitted;lastid=b->id;visited++;}
static int ieee80211_20_40_operation_permitted(struct ieee80211vap*v,uint8_t p,uint8_t s){return selected;}
static void om_ieee80211_change_bw(struct ieee80211vap*v,int value,int delay){assert(value==20&&delay==0&&stats==0);bw++;}
static void stats_cb(struct ieee80211com*ic,uint32_t reason){assert(bw==1);stats++;}
'''+timer+'\n'+scan+r'''
static void assoc_gate(struct ieee80211vap*vap,struct ieee80211_node*ni){struct ieee80211com*ic=vap->iv_ic;
'''+assoc+r'''
}
static void sta_gate(struct ieee80211vap*vap,struct ieee80211_node*ni){struct ieee80211com*ic=vap->iv_ic;
'''+sta+r'''
}
static void nonht_gate(struct ieee80211vap*vap){struct ieee80211com*ic=vap->iv_ic;
'''+nonht+r'''
}
int main(void){struct ieee80211com ic;struct ieee80211vap v;struct ieee80211_node ni,bss;struct ap_state as;struct ieee80211_scan_state ss={&as};struct ap_scan_entry e[3];unsigned policy,mode,enable,op,bucket,bad;unsigned long cases=0;
for(policy=0;policy<2;policy++)for(mode=0;mode<15;mode++)for(enable=0;enable<2;enable++)for(op=0;op<8;op++){memset(&ic,0,sizeof(ic));v.iv_ic=&ic;ic.om_20_40_bss_coex=policy;ic.ic_phymode=mode;ic.ic_opmode=op;ic.ic_obss_scan_enable=enable;ic.ic_obss_scan_count=99;timers=0;ieee80211_start_obss_scan_timer(&v);bool want=policy&&mode==9&&enable;assert(timers==want&&(!want||(expiry==jiffies+5000&&ic.ic_obss_scan_count==0&&ic.ic_obss_vap==&v)));cases++;}
for(policy=0;policy<2;policy++)for(mode=0;mode<15;mode++)for(op=0;op<8;op++)for(bucket=0;bucket<255;bucket++)for(bad=0;bad<4;bad++){
memset(&ic,0,sizeof(ic));memset(&as,0,sizeof(as));memset(e,0,sizeof(e));ic.om_20_40_bss_coex=policy;ic.ic_phymode=mode;ic.ic_opmode=op;ic.ic_scan=&ss;ic.ic_coex_stats_update=stats_cb;v.iv_ic=&ic;for(unsigned i=0;i<3;i++){e[i].base.id=i;e[i].base.permitted=(i!=bad);e[i].base.pri=i+1;e[i].base.sec=i+5;e[i].ase_list=i<2?&e[i+1]:NULL;}as.as_scan_list[bucket].asl_head.first=e;bw=stats=visited=0;int rc=ieee80211_check_mode(&v);if(op!=6)assert(rc==-22&&!bw&&!stats&&!visited);else{assert(rc==0&&visited==(bad<3?bad+1:3)&&ic.ic_obss_scan_count==1);bool want=policy&&mode==9&&bad<3;assert(bw==want&&stats==want);}cases++;}
for(policy=0;policy<2;policy++)for(unsigned coex=0;coex<256;coex++)for(unsigned ht=0;ht<2;ht++){memset(&ic,0,sizeof(ic));memset(&ni,0,sizeof(ni));v.iv_ic=&ic;ic.om_20_40_bss_coex=policy;ic.ic_coex_stats_update=stats_cb;ni.ni_coex=coex;ni.ni_htcap.cap=ht?0x4000:0;bw=stats=0;assoc_gate(&v,&ni);bool want=policy&&((coex&6)||ht);assert(bw==want&&stats==want);cases++;}
for(policy=0;policy<2;policy++)for(mode=0;mode<15;mode++)for(op=0;op<8;op++)for(unsigned same=0;same<2;same++)for(unsigned present=0;present<2;present++)for(unsigned offset=0;offset<2;offset++){memset(&ic,0,sizeof(ic));memset(&ni,0,sizeof(ni));memset(&bss,0,sizeof(bss));v.iv_ic=&ic;v.iv_bss=present?&bss:NULL;ic.om_20_40_bss_coex=policy;ic.ic_phymode=mode;ic.ic_opmode=op;ic.ic_coex_stats_update=stats_cb;ni.ni_macaddr[0]=same?0:1;ni.ni_htinfo.choffset=offset;bw=stats=0;sta_gate(&v,&ni);bool want=policy&&mode==9&&op==1&&same&&present&&!offset;assert(bw==want&&stats==want);cases++;}
for(policy=0;policy<2;policy++)for(mode=0;mode<15;mode++){memset(&ic,0,sizeof(ic));v.iv_ic=&ic;ic.ic_curmode=mode;ic.om_20_40_bss_coex=policy;ic.ic_coex_stats_update=stats_cb;bw=stats=0;nonht_gate(&v);assert(bw==(policy&&mode==9)&&stats==bw);cases++;}
assert(cases==248254UL);return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);pins={str(wp):sha(wp),str(ip):sha(ip),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(proc.stderr);assert proc.returncode==0,(proc.returncode,proc.stderr)
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_COEX26_TIMER_SCAN_ASSOC_STA_OBSS_CONSUMER_FIXTURE',hardware_accessed=False,firmware_eligible=False,cases=248254,timer_cases=480,scan_cases=244800,assoc_cases=1024,sta_cases=1920,nonht_cases=30,fragment_hashes={k:hashlib.sha256(v.encode()).hexdigest()for k,v in [('timer',timer),('scan',scan),('assoc',assoc),('sta',sta),('nonht',nonht)]},limits='Actualfunctions/conditions withfakecallbacks; incomingmanagementparsersotherthanpubliccoex notfullreplayed; noRX/RF/PHY/trafficacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
