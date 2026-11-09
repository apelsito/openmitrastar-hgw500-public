"""Actual VOPT34 Linux worker/queue/policy/quiesce with fake callback contexts."""
import argparse,hashlib,json,subprocess
from pathlib import Path
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#undef EINPROGRESS
#define EINPROGRESS 115 /* Linux ARC errno; hostMinGW value differs. */
#include "openmitrastar_vopt481_recovered.h"
#include "openmitrastar_vopt482_state.h"
typedef uint32_t u32;typedef uint8_t u8;
typedef unsigned spinlock_t;
struct work_struct{void(*fn)(struct work_struct*);unsigned queued;};
struct timer_list{unsigned pending;};
struct ieee80211com;struct ieee80211vap;struct ieee80211_node;
struct node_table{struct ieee80211_node*nodes[8];unsigned count;};
struct ieee80211_channel{int8_t ic_maxpower_normal;};
struct net_device{unsigned unused;};
struct ieee80211vap{struct ieee80211com*iv_ic;struct ieee80211_node*iv_bss;unsigned iv_opmode;unsigned char iv_myaddr[6];struct net_device*iv_dev;};
struct ieee80211_node{struct ieee80211vap*ni_vap;unsigned char ni_macaddr[6];u32 ni_qtn_flags;};
struct ieee80211com{unsigned ic_opmode;struct om_vopt_state om_vopt;struct om_vopt482_state om_vopt482;struct work_struct om_vopt_work;spinlock_t om_vopt_lock;bool om_vopt_stopping,om_vopt_pending,om_vopt_running,om_vopt_destroying;int om_vopt_last_error;int(*om_vopt_vsp_get)(struct ieee80211com*,unsigned,u32*);int(*om_vopt_vsp_set)(struct ieee80211com*,unsigned,unsigned);unsigned ic_flags,ic_flags_ext;struct{struct{unsigned ocac_chan_ieee,ocac_enable;}ocac_cfg;}ic_ocac;struct ieee80211_channel*ic_curchan;struct node_table ic_sta;void*ic_setparam;void(*ic_iterate_nodes)(struct node_table*,void(*)(void*,struct ieee80211_node*),void*,int);struct ieee80211vap*ic_vaps;u8 ic_pppc_select_enable,ic_airfair;struct timer_list ic_inact;};
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_ADDR_LEN 6
#define IEEE80211_CHAN_ANYC ((void*)0xffff)
#define IEEE80211_INACT_WAIT 5
#define HZ 200
#define READ_ONCE(v) (v)
#define EXPORT_SYMBOL(v)
#define TAILQ_FIRST(h) (*(h))
#define TAILQ_EMPTY(h) (!*(h))
static unsigned locks,rtlock,try_success=1,scheduled,canceled,timerjoins,params[500],reassocs,iterations;static int param_values[500],rc482,scs_rc,ocac_rc,irq_flag,interrupt_flag;static const struct work_struct*current;
static unsigned long jiffies;
#define spin_lock_irqsave(l,f) do{(f)=0;(*(l))++;locks++;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);assert(*(l));(*(l))--;locks--;}while(0)
#define spin_lock_init(l) (*(l)=0)
#define INIT_WORK(w,f) do{(w)->fn=(f);(w)->queued=0;}while(0)
static int rtnl_trylock(void){assert(!locks);if(!try_success)return 0;rtlock++;return 1;}
static void rtnl_unlock(void){assert(rtlock);rtlock--;}
static unsigned rtnl_is_locked(void){return rtlock;}
static unsigned in_interrupt(void){return interrupt_flag;}
static unsigned irqs_disabled(void){return irq_flag;}
static int schedule_work(struct work_struct*w){scheduled++;if(w->queued)return 0;w->queued=1;return 1;}
static void cancel_work_sync(struct work_struct*w){assert(!locks);w->queued=0;canceled++;}
static void del_timer_sync(struct timer_list*t){assert(!locks);t->pending=0;timerjoins++;}
static void mod_timer(struct timer_list*t,unsigned long when){(void)when;t->pending=1;}
static const struct work_struct*current_work(void){return current;}
int om_qdrv_vopt482_pending(const struct om_vopt482_state*s){return s&&(s->processing||s->quarantined);}
int om_qdrv_vopt482(struct ieee80211vap*v,struct om_vopt482_state*s,int val){(void)v;params[482]++;param_values[482]=val;if(rc482==-EINPROGRESS){s->processing=s->quarantined=1;s->payload=(void*)1;}return rc482;}
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,unsigned command,int val,void*d,unsigned n){(void)v;(void)d;(void)n;assert(command<500);params[command]++;param_values[command]=val;}
static int ieee80211_param_scs_set(struct net_device*d,struct ieee80211vap*v,u32 value){(void)d;(void)v;param_values[147]=value;return scs_rc;}
static int ieee80211_param_ocac_set(struct net_device*d,struct ieee80211vap*v,u32 value){(void)d;v->iv_ic->ic_ocac.ocac_cfg.ocac_enable=(value>>16)==1;return ocac_rc;}
static void ieee80211_wireless_reassoc(struct ieee80211vap*v,unsigned a,unsigned b){(void)v;assert(!a&&!b);reassocs++;}
static void iterator(struct node_table*t,void(*fn)(void*,struct ieee80211_node*),void*a,int ignore){assert(ignore==0);iterations++;for(unsigned i=0;i<t->count;i++)fn(a,t->nodes[i]);}
'''
TEST=r'''
static struct ieee80211com ic;static struct ieee80211vap vap;static struct ieee80211_node self,peer;static struct ieee80211_channel chan;static struct net_device dev;
static void clear(void){memset(&ic,0,sizeof(ic));memset(&vap,0,sizeof(vap));memset(&self,0,sizeof(self));memset(&peer,0,sizeof(peer));memset(params,0,sizeof(params));memset(param_values,0,sizeof(param_values));locks=rtlock=scheduled=canceled=timerjoins=reassocs=iterations=irq_flag=interrupt_flag=0;try_success=1;rc482=scs_rc=ocac_rc=0;current=NULL;ic.ic_opmode=6;vap.iv_ic=&ic;vap.iv_opmode=6;vap.iv_bss=&self;vap.iv_dev=&dev;self.ni_vap=peer.ni_vap=&vap;peer.ni_macaddr[0]=1;peer.ni_qtn_flags=0x800;ic.ic_vaps=&vap;ic.ic_setparam=(void*)1;ic.ic_iterate_nodes=iterator;ic.ic_sta.nodes[0]=&self;ic.ic_sta.nodes[1]=&peer;ic.ic_sta.count=2;chan.ic_maxpower_normal=-127;ic.ic_curchan=&chan;ic.ic_pppc_select_enable=ic.ic_airfair=1;om_ieee80211_vopt_initialize(&ic);om_vopt_global_backoff=0;}
static void run(void){ic.om_vopt_work.queued=0;current=&ic.om_vopt_work;ic.om_vopt_work.fn(&ic.om_vopt_work);current=NULL;}
int main(void){unsigned cases=0;int value;
clear();assert(ic.om_vopt.saved_probe==1&&ic.om_vopt.saved_pppc==1&&ic.om_vopt.saved_airfair==1&&!ic.om_vopt_stopping&&!ic.om_vopt_pending);om_ieee80211_vopt_queue(&ic);om_ieee80211_vopt_queue(&ic);assert(scheduled==1&&ic.om_vopt_pending&&!params[482]);run();assert(!ic.om_vopt_pending&&!params[482]&&!reassocs&&!locks&&!rtlock);cases++;
clear();value=2;assert(!om_vopt_kernel_policy(&vap,&value,1));om_ieee80211_vopt_queue(&ic);run();assert(ic.om_vopt.effective==1&&params[482]==1&&params[414]==1&&reassocs==1&&iterations==1&&!ic.om_vopt_pending);cases++;
clear();value=1;assert(!om_vopt_kernel_policy(&vap,&value,1));rc482=-EINPROGRESS;om_ieee80211_vopt_queue(&ic);run();assert(ic.om_vopt.effective==1&&params[482]==1&&!params[414]&&!reassocs&&ic.om_vopt_stopping&&ic.om_vopt_last_error==-EINPROGRESS);assert(om_ieee80211_vopt_quiesce(&ic)==-EINPROGRESS);scheduled=0;om_ieee80211_vopt_queue(&ic);assert(!scheduled);cases++;
clear();value=1;assert(!om_vopt_kernel_policy(&vap,&value,1));try_success=0;om_ieee80211_vopt_queue(&ic);run();assert(!params[482]&&!ic.om_vopt_pending&&!ic.om_vopt_running);try_success=1;om_ieee80211_vopt_queue(&ic);run();assert(params[482]==1);cases++;
clear();om_ieee80211_vopt_queue(&ic);assert(!om_ieee80211_vopt_quiesce(&ic)&&ic.om_vopt_stopping&&!ic.om_vopt_work.queued&&timerjoins==1&&canceled==1);om_ieee80211_vopt_resume(&ic);assert(!ic.om_vopt_stopping&&ic.ic_inact.pending);cases++;
clear();om_ieee80211_vopt_queue(&ic);assert(!om_ieee80211_vopt_detach_begin(&ic)&&ic.om_vopt_destroying);om_ieee80211_vopt_resume(&ic);assert(ic.om_vopt_stopping&&!ic.ic_inact.pending);cases++;
clear();current=&ic.om_vopt_work;assert(om_ieee80211_vopt_quiesce(&ic)==-EBUSY&&!timerjoins&&!canceled);current=NULL;cases++;
clear();om_vopt_kernel_backup(&ic,78,255);om_vopt_kernel_backup(&ic,195,128);om_vopt_kernel_backup(&ic,147,0x12345678);om_vopt_kernel_backup(&ic,158,256);om_vopt_kernel_backup(&ic,288,255);ic.ic_ocac.ocac_cfg.ocac_enable=1;om_vopt_kernel_backup(&ic,232,0);assert(ic.om_vopt.saved_txbf==255&&ic.om_vopt.saved_probe==128&&ic.om_vopt.saved_scs==0x5678&&!ic.om_vopt.saved_pppc&&ic.om_vopt.saved_airfair==255&&ic.om_vopt.saved_ocac);cases++;
clear();ic.om_vopt_running=true;value=1;assert(om_vopt_kernel_policy(&vap,&value,1)==-EBUSY);cases++;
/* No survivingVAP leaves stop latched; a newconstructedVAP resumes timer. */
clear();assert(!om_ieee80211_vopt_quiesce(&ic));ic.ic_vaps=NULL;om_ieee80211_vopt_resume(&ic);assert(ic.om_vopt_stopping&&!ic.ic_inact.pending);ic.ic_vaps=&vap;om_ieee80211_vopt_resume(&ic);assert(!ic.om_vopt_stopping&&ic.ic_inact.pending);cases++;
/* Actualrestorecallback values are unsignedsaved bytes exceptchannel482. */
clear();ic.om_vopt.effective=1;ic.om_vopt.policy=0;ic.om_vopt.saved_txbf=255;ic.om_vopt.saved_probe=128;ic.om_vopt.saved_pppc=255;ic.om_vopt.saved_airfair=255;ic.om_vopt.saved_scs=3;om_ieee80211_vopt_queue(&ic);run();assert(param_values[78]==255&&param_values[195]==128&&param_values[158]==255&&param_values[288]==255&&param_values[482]==-127&&param_values[147]==0x10003&&reassocs==1);cases++;
/* Errorsotherthanunknown482 are faithfullyignored thenreassociation occurs. */
clear();ic.om_vopt.policy=1;rc482=-EIO;scs_rc=ocac_rc=-EIO;om_ieee80211_vopt_queue(&ic);run();assert(params[482]==1&&params[414]==1&&reassocs==1&&!ic.om_vopt_stopping&&!ic.om_vopt_last_error);cases++;
/* Global backoff is shared betweentwoICs, notreset bysecondICconstructor. */
clear();ic.om_vopt.policy=2;ic.om_vopt.effective=1;peer.ni_qtn_flags=0;om_ieee80211_vopt_queue(&ic);run();assert(om_vopt_global_backoff==10&&ic.om_vopt.effective==0);struct ieee80211com second=ic;struct ieee80211vap secondvap=vap;struct ieee80211_node secondpeer=peer,secondself=self;secondvap.iv_ic=&second;secondvap.iv_bss=&secondself;secondpeer.ni_vap=secondself.ni_vap=&secondvap;secondpeer.ni_qtn_flags=0x800;second.ic_vaps=&secondvap;second.ic_sta.nodes[0]=&secondself;second.ic_sta.nodes[1]=&secondpeer;om_ieee80211_vopt_initialize(&second);second.om_vopt.policy=2;assert(om_vopt_global_backoff==10);om_ieee80211_vopt_queue(&second);second.om_vopt_work.queued=0;second.om_vopt_work.fn(&second.om_vopt_work);assert(om_vopt_global_backoff==9&&second.om_vopt.effective==0);cases++;
clear();assert(om_vopt_kernel_write_ready(&ic,78)==-EBUSY);rtlock=1;assert(!om_vopt_kernel_write_ready(&ic,78));ic.om_vopt_running=true;assert(om_vopt_kernel_write_ready(&ic,78)==-EBUSY);assert(!om_vopt_kernel_write_ready(&ic,999));rtlock=0;cases++;
/* OEM481 admission/getter belongs to radioICmode, even mixedVAPmode. */
for(unsigned radio=0;radio<16;radio++)for(unsigned vmode=0;vmode<16;vmode++){clear();ic.ic_opmode=radio;vap.iv_opmode=vmode;value=1;int r=om_vopt_kernel_policy(&vap,&value,1);assert(r==(radio==6?0:-95));ic.om_vopt.policy=2;ic.om_vopt.effective=1;value=-1;assert(!om_vopt_kernel_policy(&vap,&value,0)&&value==(radio==6?33:0));cases++;}
printf("{\"cases\":%u,\"actualworker_queue_policy_quiesce_resume\":true,\"unknown482_stops414_reassoc\":true,\"allcount_includingnonblacklist\":true,\"RTNLtrylock_nojoin_deadlock\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.candidate/'source/wlan';core=w/'openmitrastar_vopt481_kernel_core.inc';adapter=w/'openmitrastar_vopt481_kernel.inc';header=a.candidate/'headers/net80211/openmitrastar_vopt482_state.h';pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),a.compiler,core,adapter,header,w/'openmitrastar_vopt481_recovered.h']};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-vopt34-worker.c';f.write_text(PRE+core.read_text()+adapter.read_text()+TEST);cmd=[str(a.compiler),'-std=c11','-O1','-I'+str(w),'-I'+str(header.parent),str(f),'-o',str(a.output/'fixture.exe')];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_ACTUAL_VOPT34_LINUX_WORKER_SOURCE_FAKE_CALLBACK_FIXTURE',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actualadapter/corevariant source; LinuxRTNL/spinlock/timers/scheduler/hostlinkcallbacks fake. Fullmodule/ABI/physicalgates remain.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
