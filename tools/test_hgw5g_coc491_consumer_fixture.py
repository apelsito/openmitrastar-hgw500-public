"""Actual OEM491 recovered worker/consumer/CSA-callback transaction fixture.

Independent scalar reference selects QoS, SCS flags, check-channel and CSA.
Real extracted C helpers run with typed fake callbacks and explicit IRQ balance.
No hostpointer fuzzing or actual PM/RF/CSA completion is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211.c';text=source.read_text();start=text.index('static void om_coc_finish_csa(');end=text.index('\nstatic void\nieee80211_update_pm(',start);helper=text[start:end];queue_start=text.index('static void\nom_coc_pm_queue(');queue_end=text.index('EXPORT_SYMBOL(om_ieee80211_pm_queue_node_join);',queue_start)+len('EXPORT_SYMBOL(om_ieee80211_pm_queue_node_join);');queue=text[queue_start:queue_end];pins={str(source):sha(source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)}
 hosthelper=helper.replace('unsigned long arg','uintptr_t arg')
 c=r'''#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdarg.h>
typedef uint32_t u32;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define BOARD_PM_LEVEL_IDLE 5
#define PM_QOS_DEFAULT_VALUE (-1)
#define PM_QOS_POWER_SAVE 4
#define BOARD_PM_GOVERNOR_WLAN "wlan"
#define IEEE80211_M_STA 1
#define IEEE80211_S_RUN 4
#define IEEE80211_CHAN_DFS 0x00100000U
#define IEEE80211_CHAN_DFS_CAC_IN_PROGRESS 0x01000000U
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel *)(uintptr_t)0xffff)
#define QBMPS_ENABLE 1
#define IEEE80211_QTN_BMPS 0x20
#define BOARD_PM_WLAN_STA_IDLE_TIMEOUT 15
#define BOARD_PM_WLAN_IDLE_TIMEOUT 120
#define BOARD_PM_WLAN_DEFAULT_TIMEOUT 0
#define EXPORT_SYMBOL(x)
struct net_device {int unused;};
struct ieee80211_channel {u32 ic_flags;int ic_ieee;};
struct ieee80211vap {int iv_opmode,iv_state;struct ieee80211vap *iv_next;struct net_device*iv_dev;};
struct vaphead {struct ieee80211vap*first;};
struct ieee80211com {struct vaphead ic_vaps;struct ieee80211_channel*ic_bsschan;u32 om_coc_move_ndfs,om_coc_last_switch,om_coc_pm_trigger,ic_csa_reason;struct {unsigned ocac_running;}ic_ocac;unsigned ic_sta_assoc,ic_flags_qtn,ic_opmode;bool(*ic_dfs_is_eu_region)(void);int(*ic_check_channel)(struct ieee80211com*,struct ieee80211_channel*,int,int);int pm_work;unsigned om_coc_queue_lock;bool om_coc_stopping,om_coc_completion_pending,om_coc_pm_pending;int om_coc_completed_level;};
#define TAILQ_FIRST(h) ((h)->first)
#define TAILQ_FOREACH(v,h,next) for((v)=(h)->first;(v);(v)=(v)->next)
static unsigned irqdepth,irqentered,irqrestored;
#define local_irq_save(flags) do{(flags)=irqdepth;irqdepth++;irqentered++;}while(0)
#define local_irq_restore(flags) do{assert(irqdepth==(flags)+1);irqdepth=(flags);irqrestored++;}while(0)
#define spin_lock_irqsave(lock,flags) do{assert(*(lock)==0);*(lock)=1;local_irq_save(flags);}while(0)
#define spin_unlock_irqrestore(lock,flags) do{assert(*(lock)==1);*(lock)=0;local_irq_restore(flags);}while(0)
static bool eu;static int idle,lookup_kind,check_ok,csa_rc;static unsigned qos_count,pick_count,check_count,csa_count,finish_count,event_count,print_count,queue_count,flush_count;static unsigned long delay_seen;static int qos_level,flags_seen;static unsigned trace;
static void (*last_finish)(uintptr_t);static struct ieee80211_channel picked={0,44};static struct net_device dev;
static bool eu_cb(void){return eu;}
static int ieee80211_is_idle_state(struct ieee80211com*ic){return idle;}
static int pm_qos_update_requirement(int id,const char*name,int level){assert(!irqdepth&&id==4&&!strcmp(name,"wlan"));qos_count++;qos_level=level;trace=trace*10+1;return 0;}
static int ieee80211_scs_pick_channel(struct ieee80211com*ic,int flags,int unused){assert(!unused);pick_count++;flags_seen=flags;trace=trace*10+2;return 44;}
static struct ieee80211_channel*ieee80211_find_channel_by_ieee(struct ieee80211com*ic,int ieee){assert(ieee==44);return lookup_kind==0?NULL:(lookup_kind==1?IEEE80211_CHAN_ANYC:&picked);}
static int check_cb(struct ieee80211com*ic,struct ieee80211_channel*c,int a,int b){assert(c==&picked&&!a&&!b);check_count++;trace=trace*10+3;return check_ok;}
static int ieee80211_enter_csa(struct ieee80211com*ic,struct ieee80211_channel*c,void(*finish)(uintptr_t),u32 reason,int count,int mode,u32 flags){assert(c==&picked&&finish&&reason==9&&count==10&&mode==1&&flags==3);csa_count++;trace=trace*10+4;last_finish=finish;ic->ic_csa_reason=9;return csa_rc;}
static void ieee80211_finish_csa(uintptr_t arg){finish_count++;trace=trace*10+5;}
static int printk(const char*fmt,...){print_count++;return 0;}
static int ieee80211_eventf(struct net_device*d,const char*fmt,...){assert(d==NULL||d==&dev);event_count++;return 0;}
static void pm_queue_work(int*p,unsigned long delay){queue_count++;delay_seen=delay;}
static void pm_flush_work(int*p){assert(!irqdepth);flush_count++;}
'''+hosthelper+'\n'+queue+r'''
static void reset(void){irqdepth=irqentered=irqrestored=qos_count=pick_count=check_count=csa_count=finish_count=event_count=print_count=queue_count=flush_count=trace=0;flags_seen=qos_level=-999;last_finish=NULL;}
static unsigned long tested;
int main(void){struct ieee80211com ic;struct ieee80211_channel bss;struct ieee80211vap vap;unsigned pointer_kind,dfs,cac,euval,sta_run,idleval,policy,last,trig,ocac,assoc,lookup,check,csa;
 const u32 policies[]={0,1,0x80000000U,0xffffffffU},lasts[]={0,9,10},triggers[]={0,13,14};
 for(pointer_kind=0;pointer_kind<3;pointer_kind++)for(dfs=0;dfs<2;dfs++)for(cac=0;cac<2;cac++)for(euval=0;euval<2;euval++)for(sta_run=0;sta_run<2;sta_run++)for(idleval=0;idleval<2;idleval++)for(policy=0;policy<4;policy++)for(last=0;last<3;last++)for(trig=0;trig<3;trig++)for(ocac=0;ocac<2;ocac++)for(assoc=0;assoc<2;assoc++)for(lookup=0;lookup<3;lookup++)for(check=0;check<2;check++)for(csa=0;csa<2;csa++){
 memset(&ic,0,sizeof(ic));memset(&vap,0,sizeof(vap));bss.ic_flags=(dfs?IEEE80211_CHAN_DFS:0)|(cac?IEEE80211_CHAN_DFS_CAC_IN_PROGRESS:0);bss.ic_ieee=52;ic.ic_bsschan=pointer_kind==0?NULL:(pointer_kind==1?IEEE80211_CHAN_ANYC:&bss);ic.ic_vaps.first=&vap;vap.iv_opmode=sta_run?1:6;vap.iv_state=sta_run?4:0;vap.iv_dev=&dev;ic.ic_dfs_is_eu_region=eu_cb;ic.ic_check_channel=check_cb;ic.om_coc_move_ndfs=policies[policy];ic.om_coc_last_switch=lasts[last];ic.om_coc_pm_trigger=triggers[trig];ic.om_coc_pm_pending=true;ic.ic_ocac.ocac_running=ocac;ic.ic_sta_assoc=assoc;eu=euval;idle=idleval;lookup_kind=lookup;check_ok=check;csa_rc=csa?-1:0;reset();
 bool active=pointer_kind==2&&!cac;int level=idle?5:-1;bool defer=active&&assoc&&eu&&idle&&dfs;bool ready=eu&&!sta_run;bool move=active&&policies[policy]&&ready&&(idle?dfs:(!ocac&&!dfs&&lasts[last]==9&&triggers[trig]==13));bool succeeded=move&&lookup==2&&check&&!csa;unsigned wanttrace=active&&!defer?1:0;if(move){wanttrace=wanttrace*10+2;if(lookup==2){wanttrace=wanttrace*10+3;if(check)wanttrace=wanttrace*10+4;}}
 om_coc_update_pm(&ic);assert(irqdepth==0&&irqentered==irqrestored);assert(qos_count==(active&&!defer)&&(!qos_count||qos_level==level));assert(pick_count==move&&(!pick_count||flags_seen==(defer?0x12:0x14)));assert(check_count==(move&&lookup==2)&&csa_count==(move&&lookup==2&&check));assert(trace==wanttrace);assert(ic.om_coc_last_switch==(succeeded?(defer?9U:0U):lasts[last]));assert(!finish_count&&!event_count&&!print_count);
 if(succeeded){assert(last_finish==om_coc_finish_csa);void(*saved_finish)(uintptr_t)=last_finish;reset();saved_finish((uintptr_t)&ic);assert(finish_count==1&&qos_count==0&&trace==5&&event_count==0&&print_count==0&&queue_count==1&&delay_seen==0&&irqdepth==0&&ic.om_coc_completion_pending);reset();int sampled_level=ic.om_coc_completed_level;idle=!idle;om_coc_update_pm(&ic);assert(finish_count==0&&qos_count==1&&trace==1&&event_count==1&&print_count==1&&qos_level==sampled_level&&!ic.om_coc_completion_pending&&!pick_count);}
 tested++;}
 assert(tested==165888UL);
 for(unsigned reason=0;reason<11;reason++)for(unsigned ptr=0;ptr<3;ptr++)for(unsigned idlecase=0;idlecase<2;idlecase++){memset(&ic,0,sizeof(ic));ic.ic_csa_reason=reason;ic.om_coc_last_switch=9;ic.ic_bsschan=ptr==0?NULL:(ptr==1?IEEE80211_CHAN_ANYC:&bss);idle=idlecase;reset();om_coc_finish_csa((uintptr_t)&ic);assert(finish_count==(reason==9)&&qos_count==0);assert(ic.om_coc_last_switch==(reason==9?9U:0U));assert(!print_count&&!event_count&&queue_count==(reason==9));reset();om_coc_update_pm(&ic);assert(qos_count==(reason==9)&&print_count==(reason==9&&ptr==2)&&event_count==print_count&&!ic.om_coc_completion_pending);}
 for(unsigned id=0;id<2;id++)for(unsigned flags=0;flags<2;flags++)for(unsigned op=0;op<8;op++)for(unsigned nodejoin=0;nodejoin<2;nodejoin++){memset(&ic,0,sizeof(ic));idle=id;ic.ic_flags_qtn=flags?32:0;ic.ic_opmode=op;reset();if(nodejoin)om_ieee80211_pm_queue_node_join(&ic);else ieee80211_pm_queue_work(&ic);assert(ic.om_coc_pm_trigger==(nodejoin?13U:0U)&&queue_count==1&&delay_seen==(id?(flags&&(op&1)?15UL:120UL):0UL));}
 memset(&ic,0,sizeof(ic));reset();om_ieee80211_coc_quiesce(&ic);assert(ic.om_coc_stopping&&flush_count==1&&!irqdepth);ieee80211_pm_queue_work(&ic);om_ieee80211_pm_queue_node_join(&ic);om_coc_update_pm(&ic);om_coc_finish_csa((uintptr_t)&ic);assert(!queue_count&&!qos_count&&!finish_count&&!event_count);om_ieee80211_coc_quiesce(&ic);assert(flush_count==2);
 return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert r.returncode==0,(r.returncode,r.stderr)
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_COC491_DEFERRED_WORK_CONSUMER_CALLBACK_QUEUE_HOST_REFERENCE',hardware_accessed=False,firmware_eligible=False,worker_cases=165888,callback_cases=66,queue_cases=64,stop_gate_cases=6,source_sha256=pins[str(source)],helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),queue_sha256=hashlib.sha256(queue.encode()).hexdigest(),host_adapter='Onlyunsignedlongcallbackargumentbecomesuintptr_t onWindowsLLP64 toavoidhostpointertruncation; bodyunchanged',limits='Fakecallbacks; scalar sampledstate; stopgate basicnotfullconcurrency; noCoherenttuple/lifetimehardware/RF/CSAcompletion/PMbackendacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
