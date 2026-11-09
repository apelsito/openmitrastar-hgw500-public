"""Execute actual bounded467 query with real AP list refresh and whole pick body.

Fake channel-check/radio helpers are explicit; AP start and AP pick C bodies,
metric/list/flags/alternate bookkeeping and query body come from candidate.
Independent expectedDFS existence is checked at20MHz understable APscanner.
No24GHzchanset or fullOEMmetric/alternateequivalence is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def extract(text,start):
 brace=text.index('{',start);depth=1;i=brace+1
 while depth:depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[start:i]

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);sp=a.candidate/'source/wlan/ieee80211_scan.c';ap=a.candidate/'source/wlan/ieee80211_scan_ap.c';s=sp.read_text();t=ap.read_text();startfn=extract(t,t.index('static int\nap_start('));pickfn=extract(t,t.index('static struct ieee80211_channel *\nap_pick_channel('));wrapper=extract(s,s.index('struct ieee80211_channel *\nieee80211_scan_pickchannel('));query=extract(s,s.index('int om_ieee80211_dfs_channel_available('));metric=t[t.index('enum chan_sel_algorithm {'):t.index('/*\n * Pick a channel',t.index('enum chan_sel_algorithm {'))]if '/*\n * Pick a channel' in t[t.index('enum chan_sel_algorithm {'):]else''
 # Only the exact factor definitions/limits preceding actual APpick.
 metric=t[t.index('enum chan_sel_algorithm {'):t.index('/*\n * Pick a quiet channel',t.index('enum chan_sel_algorithm {'))]
 c=r'''#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include <stdbool.h>
#include <stdarg.h>
typedef unsigned u_int;
#define READ_ONCE(x) (x)
#define EOPNOTSUPP 95
#define MIN(a,b) ((a)<(b)?(a):(b))
#define IEEE80211_MODE_AUTO 0
#define IEEE80211_MODE_11G 3
#define IEEE80211_MODE_MAX 15
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_CHAN_DFS 0x100000U
#define IEEE80211_CHAN_RADAR 0x1000U
#define IEEE80211_CHAN_HT40 0x80000U
#define IEEE80211_CHAN_VHT80 0x400000U
#define IEEE80211_CHAN_ST 0x2000U
#define IEEE80211_CHAN_108G 0x8000U
#define IEEE80211_CHAN_108A 0x4000U
#define IEEE80211_CHAN_ALLTURBO 0x3ffU
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)(uintptr_t)0xffff)
#define IEEE80211_IS_CHAN_TURBO(c) ((c)->ic_flags&0x10)
#define IEEE80211_IS_CHAN_ST(c) ((c)->ic_flags&0x2000)
#define IEEE80211_IS_CHAN_B(c) ((c)->ic_flags&0x20)
#define IEEE80211_IS_CHAN_STURBO(c) ((c)->ic_flags&0x2000)
#define IEEE80211_ATHC_XR 1
#define IEEE80211_ATHC_TURBOP 2
#define IEEE80211_SCAN_MAX 32
#define IEEE80211_SCAN_NO_DFS 0x20
#define IEEE80211_SCAN_NOPICK 1
#define IEEE80211_SCAN_KEEPMODE 0x80000
#define IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY 17
#define IEEE80211_SCAN_PICK_AVAILABLE_ANY_CHANNEL 18
#define IEEE80211_PICK_DOMIAN_MASK 7
#define IEEE80211_PICK_DFS 2
#define IEEE80211_PICK_NONDFS 4
#define IEEE80211_PICK_DEFAULT 0x101
#define IEEE80211_PICK_ALGORITHM_MASK 0xff00
#define IEEE80211_PICK_REENTRY 0x200
#define IEEE80211_PICK_CLEAREST 0x100
#define QTN_APSCAN_TXPOWER_RANDOM_LIMIT 4
#define QTN_APSCAN_METSHIFT 16
#define CHIPID_DUAL 2
#define BW_HT20 20
#define BW_HT40 40
#define BW_HT80 80
#define IEEE80211_SCS_CCA_INTF_SCALE 1000
#define DM_FLAG_TXPOWER_FACTOR_PRESENT 1
#define DM_FLAG_ACI_FACTOR_PRESENT 2
#define DM_FLAG_CCI_FACTOR_PRESENT 4
#define DM_FLAG_DFS_FACTOR_PRESENT 8
#define DM_FLAG_BEACON_FACTOR_PRESENT 16
#define IEEE80211_MSG_SCAN 0
#define KERN_WARNING ""
#define IEEE80211_DPRINTF(...) do{}while(0)
#define IEEE80211_LOCK_ASSERT(ic) do{}while(0)
#define isset(p,n) (((p)[(n)>>3]>>((n)&7))&1)
#define isclr(p,n) (!isset((p),(n)))
struct ieee80211com;struct ieee80211vap;struct ieee80211_scan_state;
struct ieee80211_channel {uint32_t ic_flags;uint8_t ic_ieee;int8_t ic_maxpower;uint16_t ic_freq;bool accepted,weather,available;};
struct ap_state {uint8_t as_obss_chanlayout[255];uint16_t as_cca_intf[255];int as_cci[255],as_aci[255],as_chanmetric[255],as_maxrssi[255],as_numpkts[255];unsigned as_numbeacons[255];};
struct ieee80211_scanner {int(*scan_start)(struct ieee80211_scan_state*,struct ieee80211vap*);struct ieee80211_channel*(*scan_pickchan)(struct ieee80211com*,struct ieee80211_scan_state*,int);};
struct ieee80211_scan_state {struct ieee80211vap*ss_vap;const struct ieee80211_scanner*ss_ops;void*ss_priv;struct ieee80211_channel*ss_chans[32];unsigned ss_last,ss_next,ss_flags,ss_pick_flags;unsigned long ss_mindwell,ss_maxdwell,ss_maxdwell_passive,ss_mindwell_passive;};
struct ieee80211com {int ic_phymode,ic_des_mode,ic_nchans,ic_rf_chipid,ic_chan_is_set,ic_des_chan_after_init_cac;struct ieee80211_channel ic_channels[8],*ic_curchan,*ic_bsschan;uint8_t ic_chan_active[32],ic_chan_pri_inactive[32],ic_ieee_best_alt_chan;unsigned ic_mindwell_active,ic_maxdwell_active,ic_maxdwell_passive,ic_mindwell_passive;struct ieee80211_scan_state*ic_scan;struct {unsigned flags;int txpower_factor,aci_factor,cci_factor,dfs_factor,beacon_factor;}ic_dm_factor;int(*ic_check_channel)(struct ieee80211com*,struct ieee80211_channel*,int,int);bool(*ic_chan_compare_equality)(struct ieee80211com*,struct ieee80211_channel*,struct ieee80211_channel*);bool(*ic_dfs_chans_available_for_cac)(struct ieee80211com*,struct ieee80211_channel*);};
struct ieee80211vap {struct ieee80211com*iv_ic;int iv_opmode;unsigned iv_ath_cap;};
static unsigned starts,picks,checks,random_calls;static unsigned sequence;
static int printk(const char*fmt,...){return 0;}
static int find11gchannel(struct ieee80211com*ic,int i,int f){return 0;}
static unsigned ieee80211_get_chanflags(int m){return 0x100U;}
static unsigned long msecs_to_jiffies(unsigned x){return x;}
static int ieee80211_chan2ieee(struct ieee80211com*ic,struct ieee80211_channel*c){return c?c->ic_ieee:0;}
static bool is_channel_valid(int n){return n>0&&n<255;}
static void get_random_bytes(void*p,unsigned n){memset(p,0,n);random_calls++;}
static int ieee80211_get_bw(struct ieee80211com*ic){return 20;}
static int check(struct ieee80211com*ic,struct ieee80211_channel*c,int x,int y){assert(!x&&!y);checks++;return c->accepted;}
static bool equal(struct ieee80211com*ic,struct ieee80211_channel*a,struct ieee80211_channel*b){return a&&b&&a->ic_ieee==b->ic_ieee;}
static bool available(struct ieee80211_channel*c){return c->available;}
#define ieee80211_is_chan_available(c) available(c)
static bool cac(struct ieee80211com*ic,struct ieee80211_channel*c){return true;}
static int ieee80211_find_sec_chan(struct ieee80211_channel*c){return 0;}
static int ieee80211_find_sec40u_chan(struct ieee80211_channel*c){return 0;}
static int ieee80211_find_sec40l_chan(struct ieee80211_channel*c){return 0;}
static bool ieee80211_is_on_weather_channel(struct ieee80211com*ic,struct ieee80211_channel*c){return c->weather;}
static struct ieee80211_channel*ieee80211_scan_switch_pri_chan(struct ieee80211_scan_state*ss,struct ieee80211_channel*c){return c;}
static struct ieee80211_channel*ieee80211_find_channel_by_ieee(struct ieee80211com*ic,int n){for(int i=0;i<ic->ic_nchans;i++)if(ic->ic_channels[i].ic_ieee==n)return&ic->ic_channels[i];return NULL;}
'''+metric+'\n'+startfn+'\n'+pickfn+'\n'+wrapper+'\n'+query+r'''
static int start_adapter(struct ieee80211_scan_state*ss,struct ieee80211vap*v){assert(sequence==0);sequence=1;starts++;return ap_start(ss,v);}
static struct ieee80211_channel*pick_adapter(struct ieee80211com*ic,struct ieee80211_scan_state*ss,int f){assert(sequence==1&&f==0x130000);sequence=2;picks++;return ap_pick_channel(ic,ss,f);}
int main(void){struct ieee80211com ic;struct ieee80211vap vap;struct ieee80211_scan_state ss;struct ap_state as;struct ieee80211_scanner ops={start_adapter,pick_adapter};unsigned long cases=0;int modes[]={1,7,10,11,12,13,14};
for(unsigned mode=0;mode<7;mode++)for(unsigned states=0;states<4096;states++){
memset(&ic,0,sizeof(ic));memset(&vap,0,sizeof(vap));memset(&ss,0,sizeof(ss));memset(&as,0,sizeof(as));ic.ic_phymode=modes[mode];ic.ic_des_mode=1;ic.ic_nchans=3;ic.ic_rf_chipid=2;ic.ic_check_channel=check;ic.ic_chan_compare_equality=equal;ic.ic_dfs_chans_available_for_cac=cac;ic.ic_scan=&ss;ic.ic_chan_is_set=99;ic.ic_bsschan=&ic.ic_channels[0];ic.ic_curchan=&ic.ic_channels[0];vap.iv_ic=&ic;vap.iv_opmode=6;ss.ss_vap=&vap;ss.ss_ops=&ops;ss.ss_priv=&as;ss.ss_pick_flags=0x102;ss.ss_last=1;ss.ss_chans[0]=&ic.ic_channels[0];bool expect=false;unsigned expected_last=0;
for(unsigned i=0;i<3;i++){unsigned bits=(states>>(i*4))&15;struct ieee80211_channel*c=&ic.ic_channels[i];c->ic_ieee=36+i*8;c->ic_freq=5180+i*40;c->ic_flags=0x100|(bits&1?0x100000:0)|(bits&2?0x1000:0);c->accepted=!(bits&4);c->weather=!!(bits&8);c->available=true;c->ic_maxpower=10+i;if(!(bits&2)){ic.ic_chan_active[c->ic_ieee>>3]|=(1U<<(c->ic_ieee&7));expected_last++;if((bits&1)&&!(bits&4)&&!(bits&8))expect=true;}}
starts=picks=checks=random_calls=sequence=0;int rc=om_ieee80211_dfs_channel_available(&ic);assert(rc==(expect?1:-95)&&starts==1&&picks==(expected_last!=0)&&sequence==(expected_last?2U:1U)&&ss.ss_last==expected_last&&ss.ss_next==0&&ss.ss_pick_flags==(expected_last?0x101U:0x102U)&&ic.ic_chan_is_set==99);cases++;}
for(unsigned mode=0;mode<16;mode++)for(unsigned missing=0;missing<6;missing++){memset(&ic,0,sizeof(ic));memset(&vap,0,sizeof(vap));memset(&ss,0,sizeof(ss));ic.ic_phymode=mode;ic.ic_scan=missing==0?NULL:&ss;vap.iv_ic=&ic;vap.iv_opmode=missing==5?1:6;ss.ss_vap=missing==1?NULL:&vap;ss.ss_ops=missing==2?NULL:&ops;ss.ss_priv=missing==3?NULL:&as;struct ieee80211_scanner partial=ops;if(missing==4){partial.scan_start=NULL;ss.ss_ops=&partial;}starts=picks=sequence=0;assert(om_ieee80211_dfs_channel_available(&ic)==-95&&!starts&&!picks);}
assert(cases==28672UL);return 0;}
''';f=a.output/'fixture.c';f.write_text(c);pins={str(sp):sha(sp),str(ap):sha(ap),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert r.returncode==0,(r.returncode,r.stderr);assert all(sha(p)==h for p,h in pins.items());result=dict(status='PASS_ACTUAL_DFS467_QUERY_REFRESH_WHOLE_APSTART_AP_PICK_5GHZ_FIXTURE',hardware_accessed=False,firmware_eligible=False,cases=28672,missing_mode_cases=96,functions={'query':hashlib.sha256(query.encode()).hexdigest(),'ap_start':hashlib.sha256(startfn.encode()).hexdigest(),'ap_pick':hashlib.sha256(pickfn.encode()).hexdigest()},limits='WholeactualAPstart/pick/query at20MHzdeterministicrandom withfakechannelcheck/alternateavailability; notallOEMmetric/rank/fallbackequivalence, not24GHz461/RF/lifetimeacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
