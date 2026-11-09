"""Exercise real F344 admission functions with explicit fake VAP objects."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
def main():
 out=ROOT/'outputs/preflight'/('f344-mode-gate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 source=(SOURCE/'qdrv_control.c').read_text()
 for name in ('f344_mode_gate.c','f344_mode_gate.h','f344_csa_state.h'):(out/name).write_bytes((SOURCE/name).read_bytes())
 (out/'test_mode_gate.c').write_bytes((ROOT/'work/kernel-port/f344/test_mode_gate.c').read_bytes())
 pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include "f344_mode_gate.h"
#include "f344_csa_state.h"
typedef uint8_t u8;
#define IEEE80211_ADDR_LEN 6
#define QDRV_MAX_VAPS 4
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_M_STA 1
#define IEEE80211_M_WDS 2
#define IFF_UP 1
#define IEEE80211_T_OFDM 2
#define IEEE80211_T_DS 1
#define QDRV_FLAG_3ADDR_BRIDGE_ENABLED() (!(qw->flags_ext&1))
#define pr_info(...) do{}while(0)
#define pr_err(...) do{}while(0)
struct ieee80211vap{int iv_opmode;bool extender;unsigned iv_flags_ext;};
struct qdrv_vap{struct ieee80211vap iv;};
struct net_device{char name[16];unsigned flags;struct qdrv_vap private;};
struct ieee80211com{bool repeater;unsigned ic_phytype,ic_csa_count,ic_flags,ic_f344_hardware_generation;int ic_timer_csa;};
#define IEEE80211_FEXT_WDS 1
#define IEEE80211_F_CHANSWITCH 2
#define QTN_CSA_STATUS_LHOST_ACTIVE 32
#define QTN_CSA_STATUS_MUC_COMPLETE 64
#define BW_HT20 20
#define BW_HT40 40
#define BW_HT80 80
#define READ_ONCE(x) (x)
#define spin_lock_irqsave(lock,flags) do{(void)(lock);(flags)=0;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);}while(0)
static unsigned f344_policy_lock;
static struct f344_csa_state f344_policy={.generation=1,.hold=true,.drained=true};
struct csa{unsigned lhost_status,muc_status;};struct shared_params{struct csa*csa_lhost;};
static struct csa csa;static struct shared_params shared={&csa};
static struct shared_params*qtn_mproc_sync_shared_params_get(void){return &shared;}
static bool timer_pending(int*t){return !!*t;}
static unsigned ieee80211_f344_policy_abi_v1(void){return sizeof(struct ieee80211com);}
static unsigned ieee80211_get_bw(struct ieee80211com*ic){(void)ic;return 80;}

struct qdrv_wlan{struct ieee80211com ic;unsigned flags_ext,csa_lock;};
struct qdrv_mac{struct qdrv_wlan*data;struct net_device*vnet[QDRV_MAX_VAPS];};
struct device{struct qdrv_mac*mac;};
static int locked,rf,openmitrastar_single_vap_create=1,openmitrastar_sequential_started=1,openmitrastar_sequential_mac0_valid=1;
static u8 openmitrastar_sequential_mac0[6]={2,0,0,0,0,1};
static struct qdrv_mac*qdrv_control_mac_get(struct device*d,const char*s){assert(!strcmp(s,"0"));return d->mac;}
static struct qdrv_wlan*qdrv_mac_get_wlan(struct qdrv_mac*m){return m->data;}
static struct qdrv_vap*netdev_priv(struct net_device*n){assert(locked);return &n->private;}
static int qdrv_parse_mac(const char*s,u8*out){if(strcmp(s,"factory"))return -1;memcpy(out,openmitrastar_sequential_mac0,6);return 0;}
static int qdrv_openmitrastar_rf_gate_enabled(void){return rf;}
static void rtnl_lock(void){assert(!locked);locked=1;}
static void rtnl_unlock(void){assert(locked);locked=0;}
static bool ieee80211_is_repeater(struct ieee80211com*ic){return ic->repeater;}
#define IEEE80211_VAP_WDS_IS_MBS(v) ((v)->extender)
#define IEEE80211_VAP_WDS_IS_RBS(v) ((v)->extender)
'''
 test=r'''
int main(void){
 struct qdrv_wlan wlan={0};struct qdrv_mac mac={.data=&wlan};struct device dev={.mac=&mac};
 struct net_device primary={.name="wifi0",.private={.iv={.iv_opmode=IEEE80211_M_STA}}},secondary={.name="wifi1",.private={.iv={.iv_opmode=IEEE80211_M_HOSTAP}}};
 char*sta[]={"start","0","sta","wifi0","factory"};char*ap[]={"start","0","ap","wifi0","factory"};char*ap1[]={"start","0","ap","wifi1"};char*stop[]={"stop","0","all"};
 assert(!f344_control_vap_admit(&dev,5,sta));assert(!f344_control_vap_admit(&dev,5,ap));
 rf=1;assert(f344_control_vap_admit(&dev,5,sta)==-EPERM);rf=0;
 mac.vnet[0]=&primary;assert(f344_control_vap_admit(&dev,5,sta)==-EPERM);assert(f344_control_vap_admit(&dev,4,ap1)==-EPERM);
 wlan.ic.repeater=true;assert(!f344_control_vap_admit(&dev,4,ap1));
 primary.flags=IFF_UP;assert(f344_control_vap_admit(&dev,4,ap1)==-EPERM);primary.flags=0;
 mac.vnet[1]=&secondary;assert(!f344_control_vap_admit(&dev,3,stop));
 secondary.private.iv.extender=true;assert(f344_control_vap_admit(&dev,3,stop)==-EPERM);secondary.private.iv.extender=false;
 strcpy(secondary.name,"wds0");assert(f344_control_vap_admit(&dev,3,stop)==-EPERM);strcpy(secondary.name,"wifi1");
 mac.data=0;assert(f344_control_vap_admit(&dev,3,stop)==-ENODEV);assert(!locked);
 puts("F344_ACTUAL_TOPOLOGY_GATE_PASS cases=11 hardware=0");return 0;
}
'''
 (out/'actual_gate.c').write_bytes((pre+function(source,'f344_copy_topology')+function(source,'f344_control_vap_admit')+test).encode())
 (out/'run.sh').write_bytes((f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror '{linux(out/'f344_mode_gate.c')}' '{linux(out/'test_mode_gate.c')}' -o '{linux(out/'policy')}'\n'{linux(out/'policy')}'\ncc -std=c11 -O2 -Wall -Wextra -Werror '{linux(out/'f344_mode_gate.c')}' '{linux(out/'actual_gate.c')}' -o '{linux(out/'actual')}'\n'{linux(out/'actual')}'\n").encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=40)
 result={'status':'PASS_MODE_GATE_AND_ACTUAL_TOPOLOGY' if not p.returncode else 'FAIL','control_sha256':hashlib.sha256((SOURCE/'qdrv_control.c').read_bytes()).hexdigest(),'evidence':p.stdout.strip(),'errors':p.stderr[-2500:],'hardware':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
