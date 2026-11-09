"""Exercise actual F338 callback admission and teardown C with interleavings."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from test_f329_watchdog import function
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f338/kernel/f332_provider.c'
def main():
 out=ROOT/('outputs/preflight/f338-lifetime-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
 src=SOURCE.read_text()
 pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
struct work_struct{int unused;};static struct{struct work_struct work;}poll_work;
static struct work_struct availability_work,other_work;
static bool atom,irq,ready,engine_fault_latched,callbacks_closing,loss_pending,loss_running;
static int self,state_lock,request_lock,last_error,stops,joins,held,retired,ends,queued,called,lock_depth,ipc_cancels;
static uint32_t loss_generation,loss_reason,seen_generation,seen_reason;
static struct{struct{bool initialized;}pipeline;}storage,*workspace=&storage;
static struct{unsigned registrations;bool exhausted,started;uint64_t epoch,applied_epoch;}requests;
static struct{unsigned phase;}events;
enum{F332_OFF=0,F338_HARDWARE_FAULT=4};
static void *dfs_callback,*is_dfs_channel,*is_weather_channel,*stats_callback,*stats_argument,*owner_shared;
static void (*availability_callback)(uint32_t,uint32_t);
static bool in_atomic(void){return atom;}
static bool irqs_disabled(void){return irq;}
static struct work_struct*current_work(void){return self==1?&poll_work.work:self==2?&availability_work:&other_work;}
static void stop_request(bool stop){assert(stop);stops++;requests.started=false;ready=false;}
static void cancel_delayed_work_sync(void*p){assert(p==&poll_work&&callbacks_closing&&!requests.started);joins++;}
static void service_lost(unsigned);
static void cancel_work_sync(void*p){assert(p==&availability_work&&callbacks_closing&&joins==1);joins++;queued=0;service_lost(1);assert(!queued);}
static void f338_ipc_cancel(void){assert(joins==2);ipc_cancels++;}
static void f338_ipc_wake(void){}
static void mutex_lock(void*p){assert(p==&state_lock&&joins==2&&!held);held=1;}
static void mutex_unlock(void*p){assert(p==&state_lock&&held);held=0;}
#define spin_lock_irqsave(lock,flags) do{assert((lock)==&request_lock&&!lock_depth);lock_depth=1;(flags)=0;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{assert((lock)==&request_lock&&(flags)==0&&lock_depth==1);lock_depth=0;}while(0)
static void schedule_work(void*p){assert(p==&availability_work&&lock_depth&&!callbacks_closing);queued++;}
static int f327_oem_invalidate(void*p){assert(p==&requests&&lock_depth);requests.epoch++;requests.applied_epoch=0;return 1;}
static int system_wq;
static void mod_delayed_work(int w,void*p,int delay){(void)w;assert(p==&poll_work&&!delay&&!lock_depth&&!callbacks_closing);}
static int f332_pipeline_end(void*p){assert(p==&workspace->pipeline&&held);ends++;workspace->pipeline.initialized=false;return 0;}
static void f332_hw_retire(void){assert(held&&joins==2);retired++;}
static void cb(uint32_t gen,uint32_t reason){assert(!held&&!lock_depth);called++;seen_generation=gen;seen_reason=reason;}
static void reset(void){atom=irq=false;self=0;ready=true;engine_fault_latched=callbacks_closing=loss_pending=loss_running=false;last_error=stops=joins=held=retired=ends=queued=called=lock_depth=ipc_cancels=0;requests.registrations=7;requests.started=true;requests.exhausted=false;requests.epoch=requests.applied_epoch=9;workspace->pipeline.initialized=true;events.phase=1;dfs_callback=is_dfs_channel=is_weather_channel=stats_callback=stats_argument=owner_shared=(void*)1;availability_callback=cb;}
'''
 tests=r'''
int main(void){
 reset();atom=true;assert(radar_wait_stopped()==-EWOULDBLOCK&&!stops);
 reset();irq=true;assert(radar_wait_stopped()==-EWOULDBLOCK&&!stops);
 reset();self=1;assert(radar_wait_stopped()==-EDEADLK&&!stops);
 reset();self=2;assert(radar_wait_stopped()==-EDEADLK&&!stops);
 reset();service_lost(1);assert(!ready&&queued==1&&loss_pending&&loss_generation==9);availability_worker(&availability_work);assert(called==1&&seen_generation==9&&seen_reason==1&&!loss_running&&!loss_pending);
 reset();service_lost(2);assert(!radar_wait_stopped());assert(joins==2&&ipc_cancels==1&&ends==1&&retired==1&&!dfs_callback&&!availability_callback&&!owner_shared&&!ready&&!requests.started&&!queued);
 service_lost(1);assert(!queued&&!availability_callback&&callbacks_closing);
 reset();assert(!radar_register_availability(0)&&!ready&&!availability_callback);assert(!radar_register_availability(cb)&&availability_callback==cb&&!callbacks_closing);
 puts("F338_LIFETIME_PASS cases=8 late_close_after_join=blocked callbacks_outside_locks=1 hardware=0");return 0;
}
'''
 (out/'harness.c').write_text(pre+'\n'.join(function(src,n) for n in ('availability_worker','service_lost','radar_register_availability','radar_wait_stopped'))+tests,newline='\n')
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-variable '{linux(out/'harness.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=40)
 (out/'run.log').write_text(p.stdout+p.stderr)
 report={'status':'PASS_ACTUAL_F338_LIFETIME' if not p.returncode and 'F338_LIFETIME_PASS' in p.stdout else 'FAIL','provider_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'hardware':False,'evidence':p.stdout.strip(),'errors':p.stderr[-2500:]}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'path':str(out/'result.json'),**report},indent=2));return report['status']=='FAIL'
if __name__=='__main__':raise SystemExit(main())
