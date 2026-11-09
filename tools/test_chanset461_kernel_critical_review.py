"""Read-only actual kernel adapter fixture and lifecycle counterexamples.

Compile the entire candidate include and pure helpers with fake kernel channels,
stats and start callbacks. No candidate mutation or hardware/ARC compilation.
"""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "openmitrastar_chanset_recovered.h"
typedef uint8_t u8;typedef uint32_t u32;
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_MODE_11B 2
#define IEEE80211_MODE_11G 3
#define IEEE80211_MODE_11NG 8
#define IEEE80211_MODE_11NG_HT40PM 9
#define IEEE80211_F_SCAN 0x80
#define IEEE80211_SCAN_USECACHE 0x40000
#define IEEE80211_CHAN_MAX 255
#define CTRY_DEFAULT 0
#define IEEE80211_CHAN_2GHZ 0x80
#define IEEE80211_CHAN_RADAR 0x1000
#define IEEE80211_CHAN_DFS 0x100000
#define IEEE80211_CHAN_HT40U 0x20000
#define IEEE80211_CHAN_HT40D 0x40000
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)1)
#define PWR_IDX_BF_OFF 0
#define PWR_IDX_1SS 0
#define PWR_IDX_40M 1
#define PWR_IDX_20M 0
#define READ_ONCE(v) (v)
#define EXPORT_SYMBOL(v)
typedef unsigned spinlock_t;
static unsigned locks;
#define spin_lock_irqsave(l,f) do{(f)=0;(*(l))++;locks++;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);assert(*(l));(*(l))--;locks--;}while(0)
#define spin_lock(l) do{(*(l))++;locks++;}while(0)
#define spin_unlock(l) do{assert(*(l));(*(l))--;locks--;}while(0)
#define isset(a,n) (((a)[(n)/8]>>((n)%8))&1U)
static void bitset(uint8_t*a,unsigned n){a[n/8]|=1U<<(n%8);}
struct ieee80211vap;struct ieee80211com;
struct ieee80211_channel{unsigned ic_ieee,ic_freq,ic_flags;u8 ic_center_f_40MHz;int ic_maxregpower;int ic_maxpower_table[1][1][2];};
struct ieee80211_scan_ssid{unsigned len;};
struct ieee80211_scan_entry{struct ieee80211_channel*se_chan;int se_rssi;unsigned bw,primary,secondary;};
struct ap_scan_entry{struct ieee80211_scan_entry base;struct ap_scan_entry*next;};
struct ap_scan_list{struct ap_scan_entry*asl_head;};
struct ap_state{spinlock_t asl_lock;struct ap_scan_list as_scan_list[255];};
#define TAILQ_FOREACH(v,h,f) for((v)=*(h);(v);(v)=(v)->next)
struct ieee80211_scan_state{struct ieee80211vap*ss_vap;void*ss_priv;};
struct scan_state{struct ieee80211_scan_state base;spinlock_t om_chanset_lock;bool om_chanset_stopping;u8 om_chanset_policy;struct ieee80211vap*om_chanset_owner;struct om_chanset_transaction om_chanset;struct om_chanset_observation om_observations[255];struct om_chanset_channel_state om_channels[98];u8 om_scan_detaching;int om_chanset_last_error;};
#define SCAN_PRIVATE(ss) ((struct scan_state*)(ss))
struct ieee80211com{spinlock_t ic_comlock;int ic_chan_is_set;unsigned ic_phymode,ic_flags,ic_country_code,ic_max_system_bw,bw;struct ieee80211_scan_state*ic_scan;struct ieee80211_channel*ic_bsschan;uint8_t ic_chan_disabled[32],ic_chan_pri_inactive[32],ic_chan_active_20[32],ic_chan_active_40[32];struct ieee80211_channel channels[255];int(*ic_check_channel)(struct ieee80211com*,struct ieee80211_channel*,int,int);};
struct ieee80211vap{unsigned iv_opmode;struct ieee80211com*iv_ic;};
struct qtn_scs_scan_info{u32 bw_sel,cca_try,cca_idle,cca_busy,cca_tx,cca_intf,cca_pri,cca_sec,cca_sec40,bcn_rcvd,crc_err,lpre_err,spre_err;};
struct qtn_scs_info_set{struct qtn_scs_scan_info scan_info[255];};
struct shared_params{struct qtn_scs_info_set*scs_info_lhost;};
static struct shared_params shares;static struct qtn_scs_info_set stats;static unsigned shared_calls,lookup_calls,check_calls,changes,start_calls,nested_result,start_behavior,check_result=1,neighbor_visits;static struct ieee80211vap*other;
static unsigned ieee80211_get_bw(struct ieee80211com*ic){return ic->bw;}
static struct shared_params*qtn_mproc_sync_shared_params_get(void){shared_calls++;return &shares;}
static struct ieee80211_channel*ieee80211_find_channel_by_ieee(struct ieee80211com*ic,unsigned c){lookup_calls++;return c<255&&ic->channels[c].ic_ieee?&ic->channels[c]:NULL;}
static unsigned ieee80211_find_sec_chan(struct ieee80211_channel*c){return(c->ic_flags&IEEE80211_CHAN_HT40U)?c->ic_ieee+4:(c->ic_flags&IEEE80211_CHAN_HT40D)?c->ic_ieee-4:0;}
static int ieee80211_ieee2mhz(unsigned c,int flags){(void)flags;return 2407+5*c;}
static unsigned ieee80211_get_max_ap_bw(struct ieee80211_scan_entry*e){neighbor_visits++;return e->bw;}
static void ieee80211_find_ht_pri_sec_chan(struct ieee80211vap*v,struct ieee80211_scan_entry*e,uint8_t*p,uint8_t*s){(void)v;*p=e->primary;*s=e->secondary;}
static int ieee80211_get_type_of_neighborhood(struct ieee80211com*ic){(void)ic;return 0;}
static int ieee80211_dual_sec_chan_supported(struct ieee80211vap*v,unsigned c){(void)v;(void)c;return 1;}
static void ieee80211_update_sec_chan_offset(struct ieee80211_channel*c,unsigned o){c->ic_flags&=~(IEEE80211_CHAN_HT40U|IEEE80211_CHAN_HT40D);c->ic_flags|=o==1?IEEE80211_CHAN_HT40U:o==3?IEEE80211_CHAN_HT40D:0;}
static void om_ieee80211_change_bw(struct ieee80211vap*v,unsigned w,int reason){(void)reason;v->iv_ic->bw=w;changes++;}
static int check(struct ieee80211com*ic,struct ieee80211_channel*c,int x,int y){(void)ic;(void)c;(void)x;(void)y;check_calls++;return check_result;}
int om_chanset_kernel_start(struct ieee80211vap*,int,unsigned,unsigned,const struct ieee80211_scan_ssid*);
void om_chanset_kernel_cancel(struct ieee80211com*);
static int ieee80211_start_scan(struct ieee80211vap*v,int f,unsigned d,unsigned n,const struct ieee80211_scan_ssid*s){(void)f;(void)d;(void)n;(void)s;start_calls++;struct scan_state*scan=SCAN_PRIVATE(v->iv_ic->ic_scan);if(start_behavior==1){start_behavior=0;nested_result=om_chanset_kernel_start(other,0,10,0,NULL);return 1;}if(start_behavior==2){scan->om_chanset_stopping=true;return 0;}return 1;}
'''

TEST=r'''
static struct ieee80211com ic;static struct scan_state scan;static struct ap_state ap;static struct ieee80211vap vap,vap2;
static void clear(void){memset(&ic,0,sizeof(ic));memset(&scan,0,sizeof(scan));memset(&ap,0,sizeof(ap));memset(&stats,0,sizeof(stats));ic.ic_scan=&scan.base;ic.ic_phymode=8;ic.bw=40;ic.ic_max_system_bw=40;ic.ic_bsschan=IEEE80211_CHAN_ANYC;ic.ic_check_channel=check;vap.iv_ic=vap2.iv_ic=&ic;vap.iv_opmode=vap2.iv_opmode=6;other=&vap2;scan.base.ss_vap=&vap;scan.base.ss_priv=&ap;shares.scs_info_lhost=&stats;shared_calls=lookup_calls=check_calls=changes=start_calls=start_behavior=nested_result=locks=neighbor_visits=0;check_result=1;for(unsigned c=1;c<=13;c++){ic.channels[c].ic_ieee=c;ic.channels[c].ic_freq=2407+5*c;ic.channels[c].ic_flags=IEEE80211_CHAN_2GHZ;bitset(ic.ic_chan_active_20,c);bitset(ic.ic_chan_active_40,c);}}
int main(void){unsigned cases=0;const u32 vals[]={0,1,2,3,255,256,0x7fffffff,0x80000000,0xffffffff};
for(unsigned mode=0;mode<32;mode++)for(unsigned op=0;op<16;op++){clear();ic.ic_phymode=mode;vap.iv_opmode=op;assert(om_chanset_kernel_allowed(&vap)==(op==6&&(mode==2||mode==3||mode==8||mode==9)));cases++;}
for(unsigned i=0;i<sizeof(vals)/sizeof(*vals);i++){clear();int v=(int)vals[i];assert(!om_chanset_kernel_policy(&ic,&v,1));v=0;assert(!om_chanset_kernel_policy(&ic,&v,0)&&v==(vals[i]&255));cases++;}
clear();start_behavior=1;assert(om_chanset_kernel_start(&vap,0,10,0,NULL)==1&&nested_result==-EBUSY&&scan.om_chanset_owner==&vap&&scan.om_chanset.generation==1);cases++;
clear();start_behavior=2;assert(om_chanset_kernel_start(&vap,0,10,0,NULL)==0&&!scan.om_chanset_owner&&!scan.om_chanset.busy&&scan.om_chanset_stopping);cases++;
clear();assert(om_chanset_kernel_start(&vap,0,10,0,NULL)==1);om_chanset_kernel_cancel(&ic);assert(!scan.om_chanset.busy&&!scan.om_chanset.active&&!scan.om_chanset_owner);assert(om_chanset_kernel_start(&vap2,0,10,0,NULL)==1&&scan.om_chanset.generation==2&&scan.om_chanset_owner==&vap2);cases++;
clear();assert(!om_chanset_prepare(&scan.om_chanset,OM_CHANSET_BAND24,40,0,0));scan.om_chanset_owner=&vap;shares.scs_info_lhost=NULL;assert(!om_chanset_kernel_pick(&ic));assert(scan.om_chanset.queue.cells[0]&&!om_chanset_kernel_finished(&ic));int apreturn=review_ap_null_result(&vap,&ic);assert(apreturn==1&&!review_scan_restarts(apreturn)&&scan.om_chanset.busy);cases++;
/* Exhausted queue + no legalchannel requests restart, forever, with typed busy. */
clear();assert(!om_chanset_prepare(&scan.om_chanset,OM_CHANSET_BAND24,20,0,0));scan.om_chanset_owner=&vap;memset(ic.ic_chan_active_20,0,32);assert(!om_chanset_kernel_pick(&ic));assert(om_chanset_kernel_finished(&ic)&&scan.om_chanset.busy);apreturn=review_ap_null_result(&vap,&ic);assert(apreturn==0&&review_scan_restarts(apreturn));cases++;
/* Missing sharedSCS intentionally refuses; queue is still pending. */
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,40,0,0));scan.om_chanset_owner=&vap;shares.scs_info_lhost=NULL;assert(!om_chanset_kernel_pick(&ic)&&!om_chanset_kernel_finished(&ic)&&scan.om_chanset.busy);cases++;
/* Whole picker width20 regulatory candidates and read bound. */
for(unsigned disabled=0;disabled<14;disabled++){clear();ic.bw=20;assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;if(disabled)bitset(ic.ic_chan_disabled,disabled);struct ieee80211_channel*c=om_chanset_kernel_pick(&ic);assert(c&&c->ic_ieee!=disabled&&!scan.om_chanset.active&&check_calls==1&&shared_calls==1&&lookup_calls<500&&!locks);cases++;}
printf("{\"cases\":%u,\"pending_queue_callback_inverted\":true,\"empty_queue_restarts\":true}\n",cases);return 0;}
'''

R10_TEST=r'''
static struct ieee80211com ic;static struct scan_state scan;static struct ap_state ap;static struct ieee80211vap vap,vap2;
static void clear(void){memset(&ic,0,sizeof(ic));memset(&scan,0,sizeof(scan));memset(&ap,0,sizeof(ap));memset(&stats,0,sizeof(stats));ic.ic_scan=&scan.base;ic.ic_phymode=8;ic.bw=40;ic.ic_max_system_bw=40;ic.ic_bsschan=IEEE80211_CHAN_ANYC;ic.ic_check_channel=check;vap.iv_ic=vap2.iv_ic=&ic;vap.iv_opmode=vap2.iv_opmode=6;other=&vap2;scan.base.ss_vap=&vap;scan.base.ss_priv=&ap;shares.scs_info_lhost=&stats;shared_calls=lookup_calls=check_calls=changes=start_calls=start_behavior=nested_result=locks=neighbor_visits=0;check_result=1;for(unsigned c=1;c<=13;c++){ic.channels[c].ic_ieee=c;ic.channels[c].ic_freq=2407+5*c;ic.channels[c].ic_flags=IEEE80211_CHAN_2GHZ;bitset(ic.ic_chan_active_20,c);bitset(ic.ic_chan_active_40,c);}}
int main(void){unsigned cases=0;struct ap_scan_entry bad={0};
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;shares.scs_info_lhost=NULL;assert(!om_chanset_kernel_pick(&ic)&&!scan.om_chanset.busy&&!scan.om_chanset_owner&&scan.om_chanset_last_error==-EAGAIN&&review_ap_null_result(&vap,&ic)==1);cases++;
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;memset(ic.ic_chan_active_20,0,32);assert(!om_chanset_kernel_pick(&ic)&&!scan.om_chanset.busy&&!scan.om_chanset_owner&&scan.om_chanset_last_error==-ENOENT&&review_ap_null_result(&vap,&ic)==1);cases++;
/* Adapter accepts unsupported40geometry then whole pure rank refuses. */
clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;bad.base.se_chan=&ic.channels[1];bad.base.bw=40;bad.base.primary=1;bad.base.secondary=2;bad.base.se_rssi=200;ap.as_scan_list[1].asl_head=&bad;assert(!om_chanset_kernel_pick(&ic)&&scan.om_chanset.busy&&scan.om_chanset_owner==&vap&&scan.om_chanset_last_error==0&&om_chanset_kernel_finished(&ic));cases++;
/* A 20MHz selected candidate changes channelflags before finalreject. */
clear();ic.bw=20;assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;ic.channels[1].ic_flags|=IEEE80211_CHAN_HT40U;check_result=0;assert(!om_chanset_kernel_pick(&ic)&&check_calls==1&&!scan.om_chanset.busy&&!(ic.channels[1].ic_flags&IEEE80211_CHAN_HT40U)&&scan.om_chanset_last_error==0);cases++;
/* Traversal bound uses accepted n only: rejected80MHznodes all visited. */
static struct ap_scan_entry rejected[2048];clear();assert(!om_chanset_prepare(&scan.om_chanset,0,20,0,0));scan.om_chanset_owner=&vap;for(unsigned i=0;i<2048;i++){rejected[i].base.se_chan=&ic.channels[1];rejected[i].base.bw=80;rejected[i].next=i+1<2048?&rejected[i+1]:NULL;}ap.as_scan_list[1].asl_head=rejected;assert(om_chanset_kernel_pick(&ic)&&neighbor_visits==2048&&!locks);cases++;
printf("{\"cases\":%u,\"missing_shared_fixed\":true,\"empty_legal_set_fixed\":true,\"rank_failure_leaves_busy\":true,\"rejected_choice_changes_flags\":true,\"rejected_list_visits\":%u}\n",cases,neighbor_visits);return 0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--new-failure-checks',action='store_true');p.add_argument('--fixed-failure-checks',action='store_true');a=p.parse_args();base=a.candidate/'source/wlan';inc=base/'openmitrastar_chanset_kernel.inc';ap=base/'ieee80211_scan_ap.c';scan=base/'ieee80211_scan.c'
    branch=re.search(r'return om_chanset_kernel_allowed\(vap\)\?[^;]+;',ap.read_text()).group()
    assert '!ss->ss_ops->scan_end(ss, vap, NULL, 0)'in scan.read_text()
    wrapper='static int review_ap_null_result(struct ieee80211vap*vap,struct ieee80211com*ic){'+branch+'}\nstatic int review_scan_restarts(int apreturn){return !apreturn;}\n'
    pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),inc,ap,scan,base/'openmitrastar_chanset_recovered.c',base/'openmitrastar_chanset_recovered.h',base/'openmitrastar_chanset_tables.h')}
    test=R10_TEST if a.new_failure_checks else TEST
    if a.fixed_failure_checks:
        test=test.replace('scan.om_chanset.busy&&scan.om_chanset_owner==&vap&&scan.om_chanset_last_error==0&&om_chanset_kernel_finished(&ic)','!scan.om_chanset.busy&&!scan.om_chanset_owner&&scan.om_chanset_last_error==-EINVAL&&om_chanset_kernel_finished(&ic)').replace('!(ic.channels[1].ic_flags&IEEE80211_CHAN_HT40U)&&scan.om_chanset_last_error==0','(ic.channels[1].ic_flags&IEEE80211_CHAN_HT40U)&&scan.om_chanset_last_error==-EINVAL').replace('neighbor_visits==2048','neighbor_visits==255').replace('\\\"rank_failure_leaves_busy\\\":true','\\\"rank_failure_leaves_busy\\\":false').replace('\\\"rejected_choice_changes_flags\\\":true','\\\"rejected_choice_changes_flags\\\":false')
    a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-kernel-review.c';f.write_text(PRE+inc.read_text()+wrapper+test);cmd=[str(a.compiler),'-O1','-std=c11','-I'+str(base),str(f),str(base/'openmitrastar_chanset_recovered.c'),'-o',str(a.output/'fixture.exe')];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
    result=dict(status='PASS_ACTUAL_ADAPTER_REVIEW_FIXTURE_WITH_CALLBACK_COUNTEREXAMPLES',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Whole adapter include/pure helpers actual; kernel primitives/channels/start are fake. AP null-return exact extracted branch + scan callback boolean witness, not full ap_end/scan_next. VAP teardown/real callback scheduling not completely exercised.')
    for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
