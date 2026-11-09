"""Actual complete scan_next/AP end C bodies connected to whole typed picker.

Fake IRQ/timers/channels/shared stats, default AP foreground path. Compile-time
optional background/STA hooks are omitted, never claimed as coverage. Empty scan
list is run separately with SIGSEGV capture to preserve the source counterexample.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from test_chanset461_kernel_critical_review import PRE

MORE=r'''
#include <stddef.h>
#include <signal.h>
#include <stdlib.h>
typedef uint32_t u_int32_t;typedef uint8_t u_int8_t;
#define IEEE80211_M_STA 1
#define IEEE80211_S_RUN 4
#define IEEE80211_QTN_PRINT_CH_INUSE 1
#define IEEE80211_SCAN_OBSS 0x10000
#define IEEE80211_SCAN_QTN_SEARCH_MBS 0x200
#define IEEE80211_SCAN_DFS_ACTION 0x400
#define IEEE80211_SCAN_NOPICK 0x8
#define IEEE80211_SCAN_GOTPICK 0x10
#define IEEE80211_SCAN_ONCE 0x20
#define IEEE80211_SCAN_BGSCAN 0x40
#define IEEE80211_SCAN_PICK1ST 0x4
#define IEEE80211_SCAN_ACTIVE 0x1
#define IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY 0x80
#define IEEE80211_FEXT_SCAN_20 0x1
#define IEEE80211_FEXT_SCAN_40 0x2
#define IEEE80211_FEXT_BGSCAN 0x4
#define IEEE80211_CHAN_PASSIVE 0x200
#define IEEE80211_CHAN_TURBO 0x10
#define ISCAN_MINDWELL 1
#define ISCAN_DISCARD 2
#define ISCAN_CANCEL 4
#define ISCAN_START 8
#define IEEE80211_PARAM_BEACON_ALLOW 0
#define IEEE80211_IS_CHAN_TURBO(c) (0)
#define IEEE80211_IS_CHAN_STURBO(c) (0)
#define IEEE80211_IS_11NG_40(ic) (0)
#define IEEE80211_AID(v) ((v)&0x3fff)
#define IEEE80211_LOCK_IRQ(ic) do{locks++;}while(0)
#define IEEE80211_UNLOCK_IRQ(ic) do{assert(locks);locks--;}while(0)
#define IEEE80211_DPRINTF(...)
#define KASSERT(...)
#define KERN_ERR ""
#define KERN_DEBUG ""
#define printk(...) ((void)0)
#define from_timer(v,t,m) ((struct scan_state*)((char*)(t)-offsetof(struct scan_state,m)))
#define time_before(a,b) ((long)((a)-(b))<0)
#define time_after(a,b) time_before(b,a)
#define IEEE80211_SCHEDULE_TQUEUE(t) do{(t)->scheduled=1;}while(0)
struct ieee80211_node{unsigned ni_associd;};
struct ieee80211_scanner{int(*scan_end)(struct ieee80211_scan_state*,struct ieee80211vap*,int(*)(struct ieee80211vap*,const struct ieee80211_scan_entry*),u_int32_t);int(*scan_default)(struct ieee80211vap*,const struct ieee80211_scan_entry*);};
static unsigned long jiffies=100;static unsigned txpow_rxgain_state,txpow_rxgain_count,ends,sets,probes;
static void get_max_min_dwell(struct ieee80211_scan_state*s,struct ieee80211_node*n,int p,int o,int*a,int*b){(void)s;(void)n;(void)p;(void)o;*a=1;*b=2;}
static void ieee80211_pwr_adjust(struct ieee80211vap*v,unsigned x){(void)v;(void)x;}
static void change_channel(struct ieee80211com*ic,struct ieee80211_channel*c){ic->ic_curchan=c;sets++;}
static void mod_timer(struct timer_list*t,unsigned long when){t->pending=1;t->when=when;}
static void ieee80211_check_type_of_neighborhood(struct ieee80211com*ic){(void)ic;}
static void wake_up_interruptible_all(void*p){(void)p;}
static void ieee80211_sta_pwrsave(struct ieee80211vap*v,int x){(void)v;(void)x;}
static void ieee80211_notify_scan_done(struct ieee80211vap*v){(void)v;}
static void ieee80211_send_20_40_bss_coex(struct ieee80211vap*v){(void)v;}
static void ieee80211_check_mode(struct ieee80211vap*v){(void)v;}
static void ap_list_asl_table(struct ieee80211_scan_state*s){(void)s;}
static struct ieee80211_channel*ieee80211_find_channel(struct ieee80211com*ic,unsigned f,unsigned flags){(void)flags;for(unsigned i=0;i<255;i++)if(ic->channels[i].ic_freq==f)return&ic->channels[i];return NULL;}
struct ieee80211_channel*om_chanset_kernel_pick(struct ieee80211com*);
static struct ieee80211_channel*ap_pick_channel(struct ieee80211com*ic,struct ieee80211_scan_state*ss,unsigned flags){(void)ss;(void)flags;return om_chanset_kernel_pick(ic);}
static int cac(struct ieee80211com*ic){(void)ic;return 0;}
static void done(struct ieee80211com*ic){(void)ic;ends++;}
static void dfsdone(void){}
static int scan_default(struct ieee80211vap*v,const struct ieee80211_scan_entry*e){(void)v;(void)e;return 0;}
static int ieee80211_start_scan(struct ieee80211vap*v,int f,unsigned d,unsigned n,const struct ieee80211_scan_ssid*s){(void)v;(void)f;(void)d;(void)n;(void)s;return 0;}
static void crash(int s){(void)s;puts("{\"empty_scan_list_null_dereference\":true}");exit(0);}
'''

TEST=r'''
static struct ieee80211com ic;static struct scan_state scan;static struct ap_state ap;static struct ieee80211vap vap;static struct ieee80211_node node;static struct net_device dev;static const struct ieee80211_scanner scanner={ap_end,scan_default};
static void clear(void){memset(&ic,0,sizeof(ic));memset(&scan,0,sizeof(scan));memset(&ap,0,sizeof(ap));memset(&stats,0,sizeof(stats));ic.ic_scan=&scan.base;ic.ic_phymode=8;ic.bw=20;ic.ic_max_system_bw=20;ic.ic_bsschan=IEEE80211_CHAN_ANYC;ic.ic_check_channel=check;ic.ic_get_init_cac_duration=cac;ic.ic_scan_end=done;ic.ic_dfs_action_scan_done=dfsdone;vap.iv_ic=&ic;vap.iv_opmode=6;vap.iv_bss=&node;vap.iv_dev=&dev;scan.base.ss_vap=&vap;scan.base.ss_priv=&ap;scan.base.ss_ops=&scanner;shares.scs_info_lhost=&stats;shared_calls=lookup_calls=check_calls=changes=start_calls=start_behavior=nested_result=locks=neighbor_visits=ends=sets=0;check_result=1;for(unsigned c=1;c<=13;c++){ic.channels[c].ic_ieee=c;ic.channels[c].ic_freq=2407+5*c;ic.channels[c].ic_flags=IEEE80211_CHAN_2GHZ;bitset(ic.ic_chan_active_20,c);bitset(ic.ic_chan_active_40,c);}scan.base.ss_chans[0]=&ic.channels[1];scan.base.ss_last=1;scan.base.ss_next=1;scan.ss_scanend=jiffies+1000;ic.ic_flags=IEEE80211_F_SCAN;}
int main(int argc,char**argv){unsigned cases=0;clear();if(argc>1){signal(SIGSEGV,crash);scan.base.ss_next=scan.base.ss_last=0;scan.base.ss_chans[0]=NULL;scan_next(&scan.ss_scan_timer);puts("{\"empty_scan_list_null_dereference\":false}");return 0;}
assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;scan_next(&scan.ss_scan_timer);assert(!scan.om_chanset.busy&&!ic.ic_flags&&ap.as_actiontq.scheduled==1&&ends==1&&!locks);cases++;
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;shares.scs_info_lhost=NULL;scan_next(&scan.ss_scan_timer);assert(!scan.om_chanset.busy&&!ic.ic_flags&&scan.om_chanset_last_error==-EAGAIN&&ends==1&&!locks);cases++;
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;memset(ic.ic_chan_active_20,0,32);scan_next(&scan.ss_scan_timer);assert(!scan.om_chanset.busy&&!ic.ic_flags&&scan.om_chanset_last_error==-ENOENT&&ends==1&&!locks);cases++;
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;om_chanset_kernel_cancel(&ic);scan.ss_iflags|=ISCAN_CANCEL;scan_next(&scan.ss_scan_timer);assert(!scan.om_chanset.busy&&!ic.ic_flags&&ends==1&&!locks);cases++;
printf("{\"cases\":%u,\"full_scan_next_ap_end_selected_missing_empty_cancel\":true}\n",cases);return 0;}
'''

FORTY=r'''
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,40,0,0));scan.om_chanset_owner=&vap;scan.om_chanset.queue.cells[0]=3;scan.om_chanset.queue.cells[1]=1;scan.om_chanset.queue.current_bandwidth=40;scan.base.ss_next=0;scan.base.ss_last=2;scan.base.ss_chans[0]=&ic.channels[1];scan.base.ss_chans[1]=&ic.channels[6];scan.ss_iflags=ISCAN_START;ic.ic_chan_active_40[0]&=~(1U<<5);scan_next(&scan.ss_scan_timer);assert(sets==1&&ic.ic_curchan==&ic.channels[6]&&scan.base.ss_next==2&&scan.ss_scan_timer.pending&&!locks);cases++;
/* Rejected lastchannel must complete pass then restart queue20 atfirstchannel. */
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,40,0,0));scan.om_chanset_owner=&vap;scan.om_chanset.queue.cells[0]=3;scan.om_chanset.queue.cells[1]=1;scan.om_chanset.queue.current_bandwidth=40;scan.base.ss_next=1;scan.base.ss_last=2;scan.base.ss_chans[0]=&ic.channels[6];scan.base.ss_chans[1]=&ic.channels[1];scan.ss_iflags=ISCAN_START;ic.ic_chan_active_40[0]&=~(1U<<5);scan_next(&scan.ss_scan_timer);assert(sets==1&&ic.ic_curchan==&ic.channels[6]&&scan.base.ss_next==1&&ends==1&&scan.om_chanset.queue.cells[0]==1&&scan.om_chanset.busy&&scan.ss_scan_timer.pending&&!locks);cases++;
/* BELOW queue4: rejectprimary5 withsecondary1 then visitprimary10/secondary6. */
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,40,0,0));scan.om_chanset_owner=&vap;scan.om_chanset.queue.cells[0]=4;scan.om_chanset.queue.cells[1]=1;scan.om_chanset.queue.current_bandwidth=40;scan.base.ss_next=0;scan.base.ss_last=2;scan.base.ss_chans[0]=&ic.channels[5];scan.base.ss_chans[1]=&ic.channels[10];scan.ss_iflags=ISCAN_START;ic.ic_chan_active_40[0]&=~(1U<<1);scan_next(&scan.ss_scan_timer);assert(sets==1&&ic.ic_curchan==&ic.channels[10]&&scan.base.ss_next==2&&scan.ss_scan_timer.pending&&!locks);cases++;
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--forty-flow',action='store_true');a=p.parse_args();base=a.candidate/'source/wlan';scan=base/'ieee80211_scan.c';ap=base/'ieee80211_scan_ap.c';inc=base/'openmitrastar_chanset_kernel.inc'
    pre=PRE[:PRE.index('static int ieee80211_start_scan(')]
    pre=pre.replace('struct ieee80211_scan_state{','struct ieee80211_scanner;struct ieee80211_node;struct timer_list{unsigned pending;unsigned long when;};struct ieee80211_scan_state{').replace('void*ss_priv;};','void*ss_priv;const struct ieee80211_scanner*ss_ops;unsigned ss_flags,ss_pick_flags,ss_next,ss_last,is_scan_valid;struct ieee80211_channel*ss_chans[255];};').replace('int om_chanset_last_error;};','int om_chanset_last_error;unsigned long ss_scanend,ss_chanmindwell;unsigned ss_iflags;struct timer_list ss_scan_timer,ss_probe_timer;};').replace('struct ap_state{','struct tasklet_stub{unsigned scheduled;};struct ap_state{').replace('struct ap_scan_list as_scan_list[255];};','struct ap_scan_list as_scan_list[255];int(*as_action)(struct ieee80211vap*,const struct ieee80211_scan_entry*);struct ieee80211_scan_entry as_selbss;struct tasklet_stub as_actiontq;};').replace('struct ieee80211vap{unsigned iv_opmode;','struct net_device{char name[8];};struct ieee80211_node;struct ieee80211vap{struct net_device*iv_dev;struct ieee80211_node*iv_bss;struct{unsigned is_scan_active,is_scan_passive;}iv_stats;unsigned iv_state;unsigned iv_opmode;').replace('unsigned ic_phymode,ic_flags,','void(*ic_setparam)(struct ieee80211_node*,int,int,void*,int);int(*ic_get_init_cac_duration)(struct ieee80211com*);void(*ic_dfs_action_scan_done)(void);void(*ic_scan_end)(struct ieee80211com*);unsigned ic_des_chan_after_init_scan;struct ieee80211_channel*ic_des_chan,*ic_curchan,*ic_scanchan;unsigned ic_flags_qtn,ic_flags_ext,ic_lastscan,ic_scan_comp,ic_pwr_adjust_scancnt,ic_11n_40_only_mode,ic_opmode;unsigned ic_phymode,ic_flags,')
    end='static int '+function(ap.read_text(),'ap_end(struct ieee80211_scan_state *ss');nextbody='static void '+function(scan.read_text(),'scan_next(struct timer_list *timer)');pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),Path(__file__).with_name('test_chanset461_kernel_critical_review.py'),Path(__file__).with_name('prepare_tqe_bounded_admission_prototype.py'),a.compiler,scan,ap,inc,base/'openmitrastar_chanset_recovered.c',base/'openmitrastar_chanset_recovered.h',base/'openmitrastar_chanset_tables.h')}
    test=TEST
    if a.forty_flow:test=test.replace('printf("{\\\"cases',FORTY+'printf("{\\\"cases')
    a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-scan-next-ap-end.c';f.write_text(pre+MORE+inc.read_text()+end+nextbody+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11','-I'+str(base),str(f),str(base/'openmitrastar_chanset_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=[]
    for args in ([],['empty']):
        r=subprocess.run([str(a.output/'fixture.exe')]+args,capture_output=True,timeout=10);assert not r.returncode,r.stderr.decode();obs.append(json.loads(r.stdout))
    result=dict(status='PASS_ACTUAL_FULL_SCAN_NEXT_AP_END_FOREGROUND_SOURCE_FIXTURE',hardware_accessed=False,firmware_eligible=False,observations=obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Complete scan_next/ap_end actual sources with foreground AP relevant branches; optional QTN_BG_SCAN/QSCS/QBMPS compile hooks omitted. Hardware/timers/scannerlegacy hooks fake; no fullkernel runtime claim. Emptylist diagnostic isnot proof of reachability; actualscan_restart rejects emptylist beforetimerpublication.')
    for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
