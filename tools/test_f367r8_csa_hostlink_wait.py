"""Replay the missing CSA -> full channel callback -> hostlink wait path.

The mailbox, delivered ticks and radar/hardware hooks are explicit substitutes.
Virtual waits are not elapsed hardware time or evidence of the R8 reset cause.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from test_f355_lifetime import extract

ROOT=Path(__file__).resolve().parents[1]
Q=ROOT/'work/kernel-port/f367r7-clock-publication/qdrv/qdrv'
W=ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c'
GLOBAL=ROOT/'work/sources/Quantenna-GPL/include/qtn/qtn_global.h'
UAPI=ROOT/'work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h'
CONFIG=Path('/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/f363.config')
KERNEL='/home/user/openmitrastar-build/f358-flash-arbitration-20260921T173956Z/linux/kernel/time/timer.c'
REUSED=ROOT/'outputs/preflight/f367r4-hostlink-ack-20260922T150651Z/result.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <setjmp.h>
typedef uint32_t u32;typedef uint32_t u_int32_t;typedef uintptr_t dma_addr_t;
#define DBGPRINTF(...) do{}while(0)
#define DBGPRINTF_E(...) do{}while(0)
#define pr_info(...) do{}while(0)
#define pr_err(...) do{}while(0)
#define pr_err_ratelimited(...) do{}while(0)
#define printk(...) do{}while(0)
#define KASSERT(v,unused) assert(v)
#define READ_ONCE(v) (v)
#define WRITE_ONCE(x,v) ((x)=(v))
#define dma_wmb() do{}while(0)
#define wmb() do{}while(0)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define from_timer(v,p,m) container_of(p,__typeof__(*v),m)
#define QNET_HLRING_ENTRIES 4
#define IEEE80211_CHAN_DFS_CAC_DONE 1
#define IEEE80211_CHAN_DFS_CAC_IN_PROGRESS 2
#define IEEE80211_IS_CHAN_CACDONE(c) ((c)->ic_flags&IEEE80211_CHAN_DFS_CAC_DONE)
#define IEEE80211_IS_CHAN_CAC_IN_PROGRESS(c) ((c)->ic_flags&IEEE80211_CHAN_DFS_CAC_IN_PROGRESS)
#define IEEE80211_F_CHANSWITCH 4
#define IEEE80211_F_SCAN 8
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)-1)
#define IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED 0
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_S_RUN 5
#define IEEE80211_S_SCAN 1
#define QEVT_COMMON_PREFIX ""
#define TAILQ_FIRST(h) ((h)->first)
#define TAILQ_FOREACH(v,h,n) for((v)=(h)->first;(v);(v)=(v)->n)
struct hlist_node{struct hlist_node*next;};struct hlist_head{struct hlist_node*first;};
struct timer_list{struct hlist_node entry;unsigned flags;void(*function)(struct timer_list*);};
struct timer_base{unsigned long clk;int lock;struct timer_list*running_timer;};
struct host_ioctl{u32 ioctl_command,ioctl_dev,ioctl_arg1,ioctl_arg2,ioctl_rc,ioctl_status;};
struct ieee80211_channel{unsigned ic_flags,ic_freq,ic_ieee,ic_maxpower_normal;};
struct ieee80211vap{int iv_opmode,iv_state;void*iv_dev;struct ieee80211vap*iv_next;};
struct ieee80211com{
 int ic_pm_enabled;unsigned ic_flags,ic_csa_count,ic_csa_reason,ic_csw_reason;
 struct ieee80211_channel*ic_curchan,*ic_bsschan,*ic_des_chan,*ic_prevchan,*ic_csa_chan;
 struct{struct ieee80211vap*first;}ic_vaps;struct{bool allow_measurement_report;}sta_dfs_info;
 struct timer_list ic_timer_csa;void(*ic_finish_csa)(unsigned long);void(*ic_set_channel)(struct ieee80211com*);
 bool(*ic_dfs_is_eu_region)(void);bool(*ic_chan_compare_equality)(struct ieee80211com*,struct ieee80211_channel*,struct ieee80211_channel*);
 void(*ic_mark_channel_dfs_cac_status)(struct ieee80211com*,struct ieee80211_channel*,int,bool);
 void(*ic_mark_channel_availability_status)(struct ieee80211com*,struct ieee80211_channel*,int);
 void(*ic_beacon_update)(struct ieee80211vap*);
 void(*ic_chan_switch_record)(struct ieee80211com*,struct ieee80211_channel*,int);
 void(*ic_chan_switch_reason_record)(struct ieee80211com*,int);
};
struct qdrv_mac{bool dead;unsigned ioctl_fail_count;};
struct qdrv_wlan{struct ieee80211com ic;struct qdrv_mac*mac;int unit,flowlock,rf_chipid;
 struct{u32 tx_mbox[1];struct host_ioctl*hl_ring;uintptr_t hl_ring_dma;int hl_flowlock;}tx_if;
 struct{unsigned tx_channel;}tx_stats;};
static struct{unsigned calstate;}shared,*soc_shared_params=&shared;
static struct qdrv_wlan live;static struct qdrv_mac mac;static struct host_ioctl ring[4];
static struct ieee80211_channel oldchan,newchan;static struct ieee80211vap vap;
static struct timer_base base;static struct hlist_head head;
static bool irq_enabled,freeze_ticks,mailbox_busy;static int context;
static uint32_t jiffies;static unsigned sleeps,delays,polls,checks,faults,after_radar,beacons;
static unsigned commands[8],command_count,stalled_command,ack_after_ticks;static int last_fault;
static unsigned locked,lock_max,wait_with_lock,wait_irq_disabled,softirq_seen;
static struct host_ioctl*pending;static uint32_t command_started,loop_start;
static unsigned command_elapsed[256];static jmp_buf bounded_loop;static bool loop_cap;
static bool in_irq(void){return context==2;}static bool in_interrupt(void){return context!=0;}
static bool of_machine_is_compatible(const char*s){(void)s;return false;}
static void clock_step(void){
 polls++;if(locked)wait_with_lock++;if(!irq_enabled)wait_irq_disabled++;
 if(context==1)softirq_seen++;
 if(freeze_ticks){if(polls>10000){loop_cap=true;longjmp(bounded_loop,1);}return;}
 jiffies++;
 if(pending&&pending->ioctl_command==stalled_command&&ack_after_ticks&&jiffies-command_started>=ack_after_ticks)pending->ioctl_rc=QTN_HLINK_RC_DONE;
}
#define time_after(a,b) (clock_step(),((int32_t)((uint32_t)(b)-(uint32_t)(a))<0))
static void msleep(unsigned n){(void)n;sleeps++;}
static void udelay(unsigned n){(void)n;delays++;}
#define spin_lock_irqsave(l,f) do{assert(!*(l));(f)=irq_enabled;irq_enabled=false;*(l)=1;locked++;if(locked>lock_max)lock_max=locked;}while(0)
#define spin_unlock_irqrestore(l,f) do{assert(*(l));*(l)=0;locked--;irq_enabled=(f);}while(0)
static void qdrv_mac_interrupt_muc(struct qdrv_mac*m){
 assert(m==&mac);assert(!irq_enabled&&locked==1);pending=NULL;
 for(unsigned i=0;i<4;i++)if(ring[i].ioctl_status!=QTN_HLINK_STATUS_AVAIL){pending=&ring[i];break;}
 assert(pending);assert(command_count<8);commands[command_count++]=pending->ioctl_command;
 command_started=jiffies;live.tx_if.tx_mbox[0]=0;
 pending->ioctl_rc=pending->ioctl_command==stalled_command?0:QTN_HLINK_RC_DONE;
}
static void qdrv_mac_die_action(struct qdrv_mac*m){m->dead=true;}
static void dump_hring(struct qdrv_wlan*q){(void)q;}
#define DBG_LOG_FUNC_TEST(x) 0
static bool eu(void){return true;}
static bool equal(struct ieee80211com*i,struct ieee80211_channel*a,struct ieee80211_channel*b){(void)i;return a==b;}
static void beacon(struct ieee80211vap*v){(void)v;beacons++;}
static void record(struct ieee80211com*i,struct ieee80211_channel*c,int r){(void)i;(void)c;(void)r;}
static void reason_record(struct ieee80211com*i,int r){(void)i;(void)r;}
static uint32_t qdrv_set_channel_setup(const struct ieee80211com*i,const struct ieee80211_channel*c){(void)i;return c->ic_ieee;}
static uint32_t qdrv_set_channel_freqband_setup(const struct ieee80211com*i,const struct ieee80211_channel*c){(void)i;(void)c;return 1;}
static struct ieee80211_channel*qdrv_radar_get_current_cac_chan(void){return &oldchan;}
static void qdrv_radar_stop_active_cac(void){}
static void qdrv_radar_before_newchan(void){}
static void qdrv_radar_on_newchan(void){after_radar++;}
static void qdrv_f367_channel_fault(int rc){faults++;last_fault=rc;}
static void qdrv_chan_occupy_record_finish(struct ieee80211com*i,unsigned c){(void)i;(void)c;}
#define qdrv_eventf(...) do{}while(0)
#define TIMER_IRQSAFE 1
#define hlist_empty(h) (!(h)->first)
#define hlist_entry(p,t,m) container_of(p,t,m)
static void detach_timer(struct timer_list*t,bool clear){(void)t;(void)clear;head.first=NULL;}
#define raw_spin_unlock(l) do{assert(*(l));*(l)=0;}while(0)
#define raw_spin_lock(l) do{assert(!*(l));*(l)=1;}while(0)
#define raw_spin_unlock_irq(l) do{raw_spin_unlock(l);irq_enabled=true;}while(0)
#define raw_spin_lock_irq(l) do{irq_enabled=false;raw_spin_lock(l);}while(0)
static void timer_sync_wait_running(struct timer_base*b){(void)b;}
static int preempt_count(void){return context;}
static void preempt_count_set(int n){context=n;}
#define lock_map_acquire(x) do{}while(0)
#define lock_map_release(x) do{}while(0)
#define trace_timer_expire_entry(t,c) do{(void)(t);(void)(c);assert(context==1&&irq_enabled);}while(0)
#define trace_timer_expire_exit(t) do{(void)(t);}while(0)
#define WARN_ONCE(...) do{assert(0);}while(0)
#define CHECK(v) do{checks++;assert(v);}while(0)
'''

TEST=r'''
static void reset(unsigned cal,unsigned stall,unsigned late,bool frozen,bool busy){
 memset(&live,0,sizeof(live));memset(&mac,0,sizeof(mac));memset(ring,0,sizeof(ring));memset(&base,0,sizeof(base));memset(command_elapsed,0,sizeof(command_elapsed));
 for(unsigned i=0;i<4;i++)ring[i].ioctl_status=QTN_HLINK_STATUS_AVAIL;
 oldchan=(struct ieee80211_channel){.ic_ieee=36,.ic_freq=5180};newchan=(struct ieee80211_channel){.ic_ieee=52,.ic_freq=5260,.ic_maxpower_normal=21};
 vap=(struct ieee80211vap){.iv_opmode=IEEE80211_M_HOSTAP,.iv_state=IEEE80211_S_RUN};
 live.mac=&mac;live.unit=0;live.rf_chipid=4;live.tx_if.hl_ring=ring;live.tx_if.hl_ring_dma=0x100000;
 live.ic.ic_curchan=live.ic.ic_bsschan=live.ic.ic_des_chan=&oldchan;live.ic.ic_csa_chan=&newchan;live.ic.ic_vaps.first=&vap;
 live.ic.ic_dfs_is_eu_region=eu;live.ic.ic_chan_compare_equality=equal;live.ic.ic_set_channel=qdrv_set_channel;
 live.ic.ic_beacon_update=beacon;live.ic.ic_chan_switch_record=record;live.ic.ic_chan_switch_reason_record=reason_record;
 live.ic.ic_timer_csa.function=ieee80211_finish_csa_timer;live.ic.ic_timer_csa.flags=0;
 head.first=&live.ic.ic_timer_csa.entry;base.clk=101;base.lock=1;shared.calstate=cal;jiffies=100;
 context=1;irq_enabled=false;freeze_ticks=frozen;mailbox_busy=busy;live.tx_if.tx_mbox[0]=busy?1:0;
 sleeps=delays=polls=faults=after_radar=beacons=command_count=locked=lock_max=wait_with_lock=wait_irq_disabled=softirq_seen=0;
 pending=NULL;stalled_command=stall;ack_after_ticks=late;last_fault=0;loop_cap=false;loop_start=jiffies;
}
static void run(const char*label){
 if(setjmp(bounded_loop)==0)expire_timers(&base,&head);
 printf("CASE name=%s calstate=%u context=softirq in_irq=0 ticks_elapsed=%u virtual_ms=%lu polls=%u msleep_calls=%u udelay_calls=%u wait_with_lock=%u wait_irq_disabled=%u cmd0=%u cmd1=%u faults=%u radar_after=%u timer_returned=%u bounded_loop_cap=%u\n",label,shared.calstate,jiffies-loop_start,(jiffies-loop_start)*1000/HZ,polls,sleeps,delays,wait_with_lock,wait_irq_disabled,command_count>0?commands[0]:0,command_count>1?commands[1]:0,faults,after_radar,!loop_cap,loop_cap);
}
int main(void){
 CHECK(QTN_CALSTATE_DEFAULT==3&&HZ==100);
 reset(3,0,0,false,false);run("immediate_ack");CHECK(command_count==2&&commands[0]==38&&commands[1]==17&&after_radar==1&&!faults&&!polls);CHECK(beacons==1&&live.ic.ic_curchan==&newchan);
 reset(3,17,10,false,false);run("delayed_channel_ack");CHECK(jiffies-loop_start==10&&after_radar==1&&!faults&&!sleeps&&!delays);CHECK(softirq_seen==10&&!wait_with_lock&&!wait_irq_disabled);
 reset(3,17,0,false,false);run("missing_channel_ack_default");CHECK(jiffies-loop_start==51&&faults==1&&last_fault==-1&&!after_radar);CHECK(!sleeps&&!delays&&!wait_with_lock&&!wait_irq_disabled);
 reset(1,17,0,false,false);run("missing_channel_ack_nondefault");CHECK(jiffies-loop_start==5001&&faults==1&&!after_radar);CHECK(!sleeps&&!delays&&!wait_with_lock&&!wait_irq_disabled);
 reset(3,38,0,false,false);run("missing_txpow_ack_default");CHECK(jiffies-loop_start==51&&command_count==2&&commands[0]==38&&commands[1]==17&&!faults&&after_radar==1);
 reset(1,38,0,false,false);run("missing_txpow_ack_nondefault");CHECK(jiffies-loop_start==5001&&command_count==2&&!faults&&after_radar==1);
 reset(1,0,0,false,true);run("mailbox_busy_nondefault");CHECK(jiffies-loop_start==102&&!command_count&&faults==1&&!after_radar);
 reset(3,17,0,true,false);run("undelivered_ticks");CHECK(loop_cap&&polls==10001&&jiffies==100&&!sleeps&&!delays&&!wait_with_lock&&!wait_irq_disabled&&!faults&&!after_radar);
 printf("F367R8_CSA_HOSTLINK_WAIT_PASS checks=%u kernel_timer_dispatch=actual csa_callback=actual channel_callback=actual hostlink_macro=actual calstate_default=3 hardware=0 reset_cause_proven=0\n",checks);return 0;
}
'''

def main():
 out=ROOT/'outputs/preflight'/('f367r8-csa-hostlink-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 h=(Q/'qdrv_hostlink.c').read_text();w=(Q/'qdrv_wlan.c').read_text();wire=W.read_text();glob=GLOBAL.read_text();uapi=UAPI.read_text()
 assert 'CONFIG_HZ=100' in CONFIG.read_text() and '# CONFIG_SMP is not set' in CONFIG.read_text() and 'CONFIG_PREEMPT_NONE=y' in CONFIG.read_text()
 constants='#define HZ 100ul\n'
 for name in ('QTN_CALSTATE_PROD','QTN_CALSTATE_DEFAULT'):
  constants+=re.search(r'^#define\s+'+name+r'\s+[^\n]+',glob,re.M)[0]+'\n'
 for name in ('QTN_HLINK_RC_DONE','QTN_HLINK_RC_ERR','QTN_HLINK_STATUS_AVAIL','IOCTL_DEV_STORE_TXPOW','IOCTL_DEV_CHANGE_CHANNEL','IOCTL_DEV_BEACON_START'):
  constants+=re.search(r'^#define\s+'+name+r'\s+[^\n]+',uapi,re.M)[0]+'\n'
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',KERNEL],capture_output=True,text=True,check=True);timer=p.stdout;(out/'kernel-timer.c').write_text(timer)
 names=('qdrv_alloc_ioctl','qdrv_free_ioctl','qdrv_completed_ack_result','qdrv_send_ioctl_owned','qdrv_send_ioctl','qdrv_send_ioctl_ack','qdrv_hostlink_store_txpow','qdrv_hostlink_setchan')
 definitions=h[h.index('#define QDRV_IOCTL_EVNT_TIMEOUT'):h.index('/* F367r4:')]
 timer_call=timer[timer.index('static void call_timer_fn('):timer.index('static void expire_timers(')]
 code=constants+PRE+definitions+'\n'.join(extract(h,n) for n in names)+'\n'+extract(w,'qdrv_set_channel')+extract(wire,'ieee80211_finish_csa')+extract(wire,'ieee80211_finish_csa_timer')+timer_call+extract(timer,'expire_timers')+TEST
 (out/'test.c').write_text(code)
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh','-c',"cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable -Wno-pointer-to-int-cast -Wno-int-to-pointer-cast '"+linux(out/'test.c')+"' -o '"+linux(out/'test')+"' && '"+linux(out/'test')+"'"]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/'stdout.txt').write_text(p.stdout);(out/'stderr.txt').write_text(p.stderr)
 pins={str(path):sha(path) for path in (Path(__file__).resolve(),Q/'qdrv_hostlink.c',Q/'qdrv_wlan.c',Q/'qdrv_soc.c',W,GLOBAL,UAPI,CONFIG,REUSED)}
 result=dict(schema='openmitrastar.f367r8-csa-hostlink-wait/v1',status='PASS_ACTUAL_CSA_CHANNEL_HOSTLINK_WAIT_REPLAY' if p.returncode==0 else 'FAIL',stdout=p.stdout,stderr=p.stderr[-8000:],source_pins=pins,kernel_timer_source=dict(path=KERNEL,sha256=hashlib.sha256(timer.encode()).hexdigest()),reused_ack_qualification=dict(path=str(REUSED),sha256=sha(REUSED),rerun=False),functions=names+('qdrv_set_channel','ieee80211_finish_csa','ieee80211_finish_csa_timer','call_timer_fn','expire_timers'),fake_boundary='mailbox/doorbell, delivered tick/IRQ primitives and loop cap; channel packing, radar hooks and notification callbacks; actual CSA/channel/hostlink function bodies and timeout macro unchanged',hardware_actions=False,physical_elapsed_time_measured=False,reset_cause_proven=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return p.returncode
if __name__=='__main__':raise SystemExit(main())
