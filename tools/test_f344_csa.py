"""Host execution of real F344 drain/timer code with fake firmware state."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'work/kernel-port/f344';Q=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv';W=ROOT/'work/linux510-radio-port/quantenna-f344-peers/wlan'
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "f344_csa_state.h"
#define QTN_CSA_STATUS_LHOST_ACTIVE 1U
#define QTN_CSA_STATUS_MUC_COMPLETE 64U
#define IEEE80211_F_CHANSWITCH 2U
#define READ_ONCE(x) (x)
#define from_timer(var,p,field) ((struct ieee80211com*)((char*)(p)-offsetof(struct ieee80211com,field)))
struct timer_list {bool pending;};
struct work_struct {int kind;};
struct ieee80211_channel {unsigned number;};
struct ieee80211com {
 struct timer_list ic_timer_csa;unsigned ic_csa_count,ic_flags,ic_f344_timer_generation,ic_f344_hardware_generation;
 void (*ic_finish_csa)(unsigned long);
 struct ieee80211_channel *ic_csa_chan;
 unsigned (*ic_f344_csa_enter)(struct ieee80211com*,struct ieee80211_channel*,unsigned);
 void (*ic_f344_csa_leave)(struct ieee80211com*);
};
struct qdrv_wlan {struct ieee80211com ic;unsigned csa_lock;struct work_struct csa_wq,channel_work_wq;};
struct qdrv_mac {struct qdrv_wlan *data;};struct device {struct qdrv_mac *mac;};
struct csa {unsigned lhost_status,muc_status;};struct shared_params {struct csa *csa_lhost;};
static bool openmitrastar_mode_workflow=true;
static unsigned f344_policy_lock,locks,joins,callbacks,checks,flush_action;
static struct f344_csa_state f344_policy={.generation=1};
static struct csa firmware;static struct shared_params shared={&firmware};
static struct qdrv_wlan wlan;static struct qdrv_mac mac={&wlan};static struct device dev={&mac};
#define spin_lock_irqsave(lock,flags) do{(void)(lock);(flags)=0;assert(!locks);locks++;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);assert(locks==1);locks--;}while(0)
#define C(x) do{checks++;assert(x);}while(0)
static struct qdrv_mac*qdrv_control_mac_get(struct device*d,const char*s){assert(!strcmp(s,"0"));return d->mac;}
static struct qdrv_wlan*qdrv_mac_get_wlan(struct qdrv_mac*m){return m->data;}
static struct shared_params*qtn_mproc_sync_shared_params_get(void){return &shared;}
static int f344_control_vap_admit(struct device*d,int argc,char**argv){(void)d;(void)argv;return argc!=3||!f344_policy.hold;}
static void del_timer_sync(struct timer_list*t){assert(!locks);joins++;t->pending=false;}
static void flush_work(struct work_struct*w){(void)w;assert(!locks);joins++;if(flush_action){flush_action=0;assert(!f344_csa_hold(&f344_policy,true));}}
static unsigned enter(struct ieee80211com*ic,struct ieee80211_channel*c,unsigned g){(void)ic;(void)c;return f344_csa_enter(&f344_policy,g);}
static void leave(struct ieee80211com*ic){(void)ic;f344_csa_leave(&f344_policy);}
static void ieee80211_finish_csa(unsigned long arg){(void)arg;callbacks++;}
static void custom_finish(unsigned long arg){(void)arg;callbacks+=10;}
'''
TEST=r'''
int main(void){
 char*a[]={"mode","0","drain-csa"};unsigned old,g;struct ieee80211_channel ch={36};
 wlan.ic.ic_f344_csa_enter=enter;wlan.ic.ic_f344_csa_leave=leave;wlan.ic.ic_csa_chan=&ch;
 old=f344_csa_enter(&f344_policy,0);C(old==1&&f344_policy.readers==1);
 C(!f344_csa_hold(&f344_policy,true));C(f344_policy.generation==2);
 C(qdrv_command_mode(&dev,3,a)==-EAGAIN&&joins==0);
 C(!f344_csa_enter(&f344_policy,0));f344_csa_leave(&f344_policy);
 firmware.lhost_status=QTN_CSA_STATUS_LHOST_ACTIVE;wlan.ic.ic_csa_count=3;
 wlan.ic.ic_flags=IEEE80211_F_CHANSWITCH;wlan.ic.ic_timer_csa.pending=true;
 C(qdrv_command_mode(&dev,3,a)==-EAGAIN&&joins==1);
 C(firmware.lhost_status==QTN_CSA_STATUS_LHOST_ACTIVE&&wlan.ic.ic_csa_count==3);
 C(f344_csa_hold(&f344_policy,false)!=0); /* not a fake cancellation */
 firmware.lhost_status=0; wlan.ic.ic_f344_hardware_generation=1;
 C(qdrv_command_mode(&dev,3,a)==-EOPNOTSUPP); /* final scope forbids reuse */
 firmware.muc_status=QTN_CSA_STATUS_MUC_COMPLETE;
 C(qdrv_command_mode(&dev,3,a)==-EOPNOTSUPP); /* COMPLETE is not a new epoch token */
 wlan.ic.ic_f344_hardware_generation=0; /* separate fresh-boot fixture */
 C(!qdrv_command_mode(&dev,3,a));C(joins==4&&f344_policy.drained);
 C(!wlan.ic.ic_csa_count&&!(wlan.ic.ic_flags&IEEE80211_F_CHANSWITCH));
 C(!f344_csa_hold(&f344_policy,false));C(!f344_csa_enter(&f344_policy,old));
 wlan.ic.ic_f344_timer_generation=old;wlan.ic.ic_finish_csa=custom_finish;
 ieee80211_finish_csa_timer(&wlan.ic.ic_timer_csa);C(!callbacks&&!f344_policy.readers);
 wlan.ic.ic_f344_timer_generation=f344_policy.generation;
 ieee80211_finish_csa_timer(&wlan.ic.ic_timer_csa);C(callbacks==10&&!f344_policy.readers);
 wlan.ic.ic_finish_csa=NULL;ieee80211_finish_csa_timer(&wlan.ic.ic_timer_csa);C(callbacks==11);
 /* A rollback starts another generation. Its old timer stays fenced even
  * after the new transition releases HOLD. */
 g=f344_policy.generation;C(!f344_csa_hold(&f344_policy,true));
 flush_action=1;C(qdrv_command_mode(&dev,3,a)==-EAGAIN&&!f344_policy.drained);
 C(!qdrv_command_mode(&dev,3,a));C(!f344_csa_hold(&f344_policy,false));
 wlan.ic.ic_f344_timer_generation=g;ieee80211_finish_csa_timer(&wlan.ic.ic_timer_csa);C(callbacks==11);
 f344_policy.generation=UINT32_MAX;C(f344_csa_hold(&f344_policy,true)!=0&&f344_policy.generation==UINT32_MAX);
 C(!locks&&!f344_policy.readers);
 printf("F344_CSA_REAL_DRAIN_TIMER_PASS checks=%u fake_firmware=1 hardware=0\n",checks);
 return 0;
}
'''
def main():
 out=ROOT/'outputs/preflight'/('f344-csa-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 (out/'f344_csa_state.h').write_bytes((SRC/'f344_csa_state.h').read_bytes())
 code=PRE+function((Q/'qdrv_control.c').read_text(),'qdrv_command_mode')+function((W/'ieee80211_wireless.c').read_text(),'ieee80211_finish_csa_timer')+TEST
 (out/'test.c').write_bytes(code.encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\ncc -std=c11 -O2 -Wall -Wextra -Werror '{linux(SRC/'f344_transaction.c')}' '{linux(SRC/'test_transaction.c')}' -o '{linux(out/'transaction')}'\n'{linux(out/'transaction')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=45)
 result={'status':'PASS_REAL_CSA_DRAIN_TIMER_AND_TRANSACTIONS' if not p.returncode else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'sources':{str(v.relative_to(ROOT)):hashlib.sha256(v.read_bytes()).hexdigest() for v in (Q/'qdrv_control.c',W/'ieee80211_wireless.c',SRC/'f344_csa_state.h',SRC/'f344_transaction.c')},'hardware':False,'wifi':'USER_DEFERRED'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
