"""Actual VAP detach/powersave tasklet counterexample with scheduled interleave.

Windows threads pause the real tasklet body after entry stop-check. Actual detach
joins timers then tasklet; the resumed body can rearm an already joined timer.
Source-only, no candidate modification or real driver/hardware operations.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <windows.h>
typedef unsigned spinlock_t;static unsigned locks;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define spin_lock_irqsave(l,f) do{(f)=0;(*(l))++;locks++;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);assert(*(l));(*(l))--;locks--;}while(0)
#define ISCAN_CANCEL 4
#define ISCAN_START 8
#define IEEE80211_F_SCAN 128
#define IEEE80211_PARAM_BEACON_ALLOW 0
struct timer_list{volatile LONG pending;};struct tasklet_struct{unsigned unused;};
struct ieee80211com;struct ieee80211_scan_state;
struct ieee80211_scanner{void(*scan_detach)(struct ieee80211_scan_state*);};
struct ieee80211vap{struct ieee80211com*iv_ic;void*iv_bss;};
struct ieee80211_scan_state{struct ieee80211vap*ss_vap;const struct ieee80211_scanner*ss_ops;void*ss_priv;};
struct scan_state{struct ieee80211_scan_state base;bool om_chanset_stopping;unsigned char om_scan_detaching;spinlock_t om_chanset_lock;struct ieee80211vap*om_chanset_owner;unsigned ss_iflags,ss_scanend,ss_duration;struct timer_list ss_scan_timer,ss_probe_timer;struct tasklet_struct ss_pwrsav;};
struct ieee80211com{struct ieee80211_scan_state*ic_scan;spinlock_t ic_comlock;unsigned ic_flags;void(*ic_setparam)(void*,int,int,void*,int);void(*ic_scan_start)(struct ieee80211com*);};
#define SCAN_PRIVATE(s) ((struct scan_state*)(s))
static HANDLE entered,resume,thread;static unsigned joinedscan,joinedprobe,taskletjoined;static unsigned long jiffies;
static void ieee80211_sta_pwrsave(struct ieee80211vap*v,int e){(void)v;(void)e;SetEvent(entered);assert(WaitForSingleObject(resume,5000)==WAIT_OBJECT_0);}
static int msecs_to_jiffies(int v){return v;}
static void mod_timer(struct timer_list*t,unsigned long when){(void)when;InterlockedExchange(&t->pending,1);}
static int del_timer_sync(struct timer_list*t){assert(!locks);InterlockedExchange(&t->pending,0);joinedscan++;return 0;}
static void tasklet_kill(struct tasklet_struct*t){(void)t;assert(!locks);SetEvent(resume);assert(WaitForSingleObject(thread,5000)==WAIT_OBJECT_0);taskletjoined++;}
static void om_chanset_kernel_cancel(struct ieee80211com*ic){SCAN_PRIVATE(ic->ic_scan)->om_chanset_owner=NULL;}
static void setparam(void*n,int p,int v,void*d,int s){(void)n;(void)p;(void)v;(void)d;(void)s;}
static void scanstart(struct ieee80211com*ic){(void)ic;}
'''

TEST=r'''
static struct scan_state scan;static DWORD WINAPI run(LPVOID p){scan_restart_pwrsav((unsigned long)(uintptr_t)p);return 0;}
int main(void){struct ieee80211com ic={0};struct ieee80211vap vap={0};ic.ic_scan=&scan.base;ic.ic_setparam=setparam;ic.ic_scan_start=scanstart;vap.iv_ic=&ic;scan.base.ss_vap=&vap;scan.om_chanset_owner=&vap;scan.ss_duration=10;entered=CreateEvent(NULL,TRUE,FALSE,NULL);resume=CreateEvent(NULL,TRUE,FALSE,NULL);thread=CreateThread(NULL,0,run,&scan,0,NULL);assert(WaitForSingleObject(entered,5000)==WAIT_OBJECT_0);
ieee80211_scan_vdetach(&vap);assert(taskletjoined==1&&joinedscan==2&&scan.ss_scan_timer.pending==1&&scan.base.ss_vap==NULL&&!scan.om_chanset_stopping&&!locks);
printf("{\"cases\":1,\"timer_pending_after_actual_vdetach\":true,\"tasklet_joined\":true}\n");CloseHandle(thread);CloseHandle(entered);CloseHandle(resume);return 0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixed',action='store_true');a=p.parse_args();source=a.candidate/'source/wlan/ieee80211_scan.c';s=source.read_text();task='static void '+function(s,'scan_restart_pwrsav(unsigned long arg)');detach='void '+function(s,'ieee80211_scan_vdetach(struct ieee80211vap *vap)');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-vdetach-rearm.c';test=TEST
    if a.fixed:test=test.replace('scan.ss_scan_timer.pending==1','scan.ss_scan_timer.pending==0').replace('\\\"timer_pending_after_actual_vdetach\\\":true','\\\"timer_pending_after_actual_vdetach\\\":false')
    f.write_text(PRE+task+detach+test)
    # unsigned long is64-bit onARC? TargetARC is32, WindowsLLP64 pointer truncates.
    # Change tasklet argument scalar to uintptr_t only for hostpointer transport.
    t=f.read_text().replace('scan_restart_pwrsav(unsigned long arg)','scan_restart_pwrsav(uintptr_t arg)').replace('scan_restart_pwrsav((unsigned long)(uintptr_t)p)','scan_restart_pwrsav((uintptr_t)p)');f.write_text(t)
    r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True,timeout=15);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
    result=dict(status='PASS_ACTUAL_TASKLET_VDETACH_TASKLET_FIRST_JOIN_SCHEDULE'if a.fixed else'PASS_ACTUAL_TASKLET_VDETACH_REPRODUCED_REARM_AFTER_TIMER_JOIN',hardware_accessed=False,firmware_eligible=False,**obs,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actual complete tasklet/vdetach C bodies, Windows synchronization fake. Hosttasklet argument uintptr_t substitution only. Scheduled rearm counterexample, no actual kernel scheduling orruntime.')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
