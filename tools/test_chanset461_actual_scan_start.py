"""Extract the actual complete kernel start function; source-only race witness.

Fake scanner hooks and UP IRQ locks. Reproduce an intervening original/WEXT start
after typed reservation; do not replace the candidate or access hardware.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from test_chanset461_kernel_critical_review import PRE

MORE=r'''
typedef unsigned u_int;
#define IEEE80211_QTN_MONITOR 1
#define IEEE80211_SCAN_NOSSID 1
#define IEEE80211_SCAN_ACTIVE 2
#define IEEE80211_SCAN_FLUSH 4
#define IEEE80211_IS_CHAN_CAC_IN_PROGRESS(c) (0)
#define IEEE80211_DPRINTF(...)
#define IEEE80211_LOCK_IRQ(ic) do{locks++;}while(0)
#define IEEE80211_UNLOCK_IRQ(ic) do{assert(locks);locks--;}while(0)
#define ISCAN_DISCARD 2
struct ieee80211_scanner{void(*scan_detach)(struct ieee80211_scan_state*);int(*scan_attach)(struct ieee80211_scan_state*);void(*scan_flush)(struct ieee80211_scan_state*);void(*scan_start)(struct ieee80211_scan_state*,struct ieee80211vap*);};
static void detach(struct ieee80211_scan_state*s){(void)s;}
static int attach(struct ieee80211_scan_state*s){(void)s;return 1;}
static void flush(struct ieee80211_scan_state*s){(void)s;}
static void start(struct ieee80211_scan_state*s,struct ieee80211vap*v){(void)s;(void)v;}
static const struct ieee80211_scanner scanner={detach,attach,flush,start};
static const struct ieee80211_scanner*ieee80211_scanner_get(unsigned m,int n){(void)m;(void)n;return &scanner;}
static void copy_ssid(struct ieee80211vap*v,struct ieee80211_scan_state*s,unsigned n,const struct ieee80211_scan_ssid*p){(void)v;(void)s;(void)n;(void)p;}
static int scan_restart(struct scan_state*s,unsigned d){(void)s;(void)d;return 1;}
static unsigned beacons;
static void beacon_stop(struct ieee80211vap*v){(void)v;beacons++;}
static unsigned legacy_steal,legacy_expected=128;
int ieee80211_start_scan(struct ieee80211vap*,int,unsigned,unsigned,const struct ieee80211_scan_ssid*);
static int invoke_actual(struct ieee80211vap*v,int flags,unsigned duration,unsigned nssid,const struct ieee80211_scan_ssid*ssids){if(legacy_steal){legacy_steal=0;assert(ieee80211_start_scan(other,flags,duration,nssid,ssids)==legacy_expected);}return ieee80211_start_scan(v,flags,duration,nssid,ssids);}
'''

TEST=r'''
int main(void){struct ieee80211com ic={0};struct scan_state scan={0};struct ieee80211vap one={0},two={0};struct ap_state ap={0};
ic.ic_phymode=8;ic.bw=20;ic.ic_scan=&scan.base;ic.ic_bsschan=IEEE80211_CHAN_ANYC;ic.ic_beacon_stop=beacon_stop;one.iv_ic=two.iv_ic=&ic;one.iv_opmode=two.iv_opmode=6;other=&two;scan.base.ss_vap=&one;scan.base.ss_priv=&ap;legacy_steal=1;
int r=om_chanset_kernel_start(&one,0,10,0,NULL);assert(r==IEEE80211_F_SCAN&&scan.base.ss_vap==&two&&scan.om_chanset_owner==&one&&scan.om_chanset.busy&&beacons==2&&!locks);assert(!om_chanset_kernel_pick(&ic)&&scan.om_chanset.busy&&scan.om_chanset_owner==&one);
printf("{\"cases\":1,\"legacy_start_steals_reservation\":true,\"false_success\":%d,\"requested_owner_matches_scanner\":false}\n",r);return 0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixed',action='store_true');p.add_argument('--beacon-fixed',action='store_true');a=p.parse_args();base=a.candidate/'source/wlan';scan=base/'ieee80211_scan.c';inc=base/'openmitrastar_chanset_kernel.inc';actual='int '+function(scan.read_text(),'ieee80211_start_scan(struct ieee80211vap *vap')
    pre=PRE.replace('struct ieee80211_scan_state{struct ieee80211vap*ss_vap;void*ss_priv;};','struct ieee80211_scanner;struct ieee80211_scan_state{struct ieee80211vap*ss_vap;void*ss_priv;const struct ieee80211_scanner*ss_ops;unsigned ss_flags;};').replace('u8 om_scan_detaching;int om_chanset_last_error;','u8 om_scan_detaching;unsigned ss_iflags;int om_chanset_last_error;').replace('struct ieee80211com{','struct ieee80211com{struct {unsigned sta_dfs_strict_mode;}sta_dfs_info;void(*ic_beacon_stop)(struct ieee80211vap*);unsigned ic_flags_qtn;',1).replace('struct ieee80211vap{unsigned iv_opmode;','struct ieee80211vap{struct{unsigned is_scan_active,is_scan_passive;}iv_stats;unsigned iv_opmode;')
    # Omit only the fake actual-start replacement from the shared fixture preamble.
    pre=pre[:pre.index('static int ieee80211_start_scan(')]
    adaptedinc=inc.read_text().replace('result=ieee80211_start_scan(vap,','result=invoke_actual(vap,',1)
    pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),Path(__file__).with_name('test_chanset461_kernel_critical_review.py'),Path(__file__).with_name('prepare_tqe_bounded_admission_prototype.py'),a.compiler,scan,inc,base/'openmitrastar_chanset_recovered.c',base/'openmitrastar_chanset_recovered.h',base/'openmitrastar_chanset_tables.h')}
    test=TEST
    if a.fixed:
        test=test.replace('legacy_steal=1;','legacy_steal=1;legacy_expected=0;').replace('r==IEEE80211_F_SCAN&&scan.base.ss_vap==&two','r==1&&scan.base.ss_vap==&one').replace('assert(!om_chanset_kernel_pick(&ic)&&scan.om_chanset.busy&&scan.om_chanset_owner==&one);','assert(scan.om_chanset_owner==scan.base.ss_vap);').replace('\\\"legacy_start_steals_reservation\\\":true','\\\"legacy_start_steals_reservation\\\":false').replace('\\\"requested_owner_matches_scanner\\\":false','\\\"requested_owner_matches_scanner\\\":true')
    if a.beacon_fixed:
        test=test.replace('beacons==2','beacons==1').replace('printf("{','assert(ieee80211_start_scan(&two,0,10,0,NULL)==0&&beacons==1);assert(ieee80211_start_scan(&one,0,10,0,NULL)==0&&beacons==1);om_chanset_kernel_cancel(&ic);ic.ic_flags=0;assert(ieee80211_start_scan(&two,0,10,0,NULL)==IEEE80211_F_SCAN&&beacons==2);assert(ieee80211_start_scan(&two,0,10,0,NULL)==IEEE80211_F_SCAN&&beacons==2);printf("{').replace('\\\"cases\\\":1','\\\"cases\\\":5').replace('\\\"false_success\\\":%d','\\\"typed_start_return\\\":%d')
    a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-start-reservation.c';f.write_text(pre+MORE+actual+adaptedinc+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11','-I'+str(base),str(f),str(base/'openmitrastar_chanset_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
    result=dict(status='PASS_ACTUAL_KERNEL_START_LEGACY_RESERVATION_GUARD'if a.fixed else'PASS_ACTUAL_KERNEL_START_REPRODUCED_LEGACY_RESERVATION_STEAL',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actual complete start function/adapter; one wrapper inserts legacy start between reservation and actual requestedstart. Scanner hooks/IRQ locks fake; source counterexample, no kernel runtime acceptance.')
    for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
