"""Exercise the actual F332 teardown function with controlled kernel services."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from test_f329_watchdog import function
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f332_dfs_provider/provider/f332_provider.c'
def main():
 out=ROOT/('outputs/preflight/f332-lifetime-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
 src=SOURCE.read_text()
 pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
struct work_struct{int unused;};static struct{struct work_struct work;}poll_work;
static struct work_struct other_work;
static bool atom,irq,self,ready,engine_fault_latched,sample_source_registered;
static int state_lock,request_lock,last_error,engine_error,stops,joins,held,retired,ends;
static struct{bool initialized;}pipe_state;
static struct{struct{bool initialized;}pipeline;}storage,*workspace=&storage;
static struct{unsigned registrations;bool exhausted,started;}requests;
static struct{unsigned phase;}events;
enum{F332_OFF=0};
static void *dfs_callback,*is_dfs_channel,*is_weather_channel,*stats_callback,*stats_argument,*owner_shared;
static bool in_atomic(void){return atom;}
static bool irqs_disabled(void){return irq;}
static struct work_struct*current_work(void){return self?&poll_work.work:&other_work;}
static void stop_request(bool stop){assert(stop);stops++;requests.started=false;ready=false;}
static void cancel_delayed_work_sync(void*p){assert(p==&poll_work&&stops==1&&!requests.started);joins++;}
static void mutex_lock(void*p){assert(p==&state_lock&&joins==1&&!held);held=1;}
static void mutex_unlock(void*p){assert(p==&state_lock&&held);held=0;}
#define spin_lock_irqsave(lock,flags) do{assert((lock)==&request_lock&&held);(flags)=0;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{assert((lock)==&request_lock&&(flags)==0&&held);}while(0)
static int f332_pipeline_end(void*p){assert(p==&workspace->pipeline&&held);ends++;workspace->pipeline.initialized=false;return engine_error;}
static void f332_hw_retire(void){assert(held&&joins==1);retired++;}
static void reset(void){atom=irq=self=false;ready=sample_source_registered=true;engine_fault_latched=false;last_error=engine_error=stops=joins=held=retired=ends=0;requests.registrations=7;requests.started=true;requests.exhausted=false;workspace->pipeline.initialized=true;events.phase=1;dfs_callback=is_dfs_channel=is_weather_channel=stats_callback=stats_argument=owner_shared=(void*)1;}
'''
 tests=r'''
int main(void){
 reset();atom=true;assert(radar_wait_stopped()==-EWOULDBLOCK&&!stops&&!joins&&dfs_callback);
 reset();irq=true;assert(radar_wait_stopped()==-EWOULDBLOCK&&!stops&&!joins&&dfs_callback);
 reset();self=true;assert(radar_wait_stopped()==-EDEADLK&&!stops&&!joins&&dfs_callback);
 reset();assert(!radar_wait_stopped());assert(stops==1&&joins==1&&ends==1&&retired==1&&!held&&!dfs_callback&&!owner_shared&&!requests.registrations&&!ready&&!engine_fault_latched&&sample_source_registered);
 reset();engine_error=-1;assert(!radar_wait_stopped());assert(stops==1&&joins==1&&ends==1&&retired==1&&!held&&!dfs_callback&&!owner_shared&&engine_fault_latched&&requests.exhausted&&last_error==-EIO);
 reset();workspace->pipeline.initialized=false;assert(!radar_wait_stopped()&&joins==1&&!ends&&retired==1&&!dfs_callback);
 puts("F332_LIFETIME_PASS cases=6 join_before_free=1 math_fault_distinct=1 hardware=0");return 0;
}
'''
 (out/'harness.c').write_text(pre+function(src,'radar_wait_stopped')+tests,newline='\n')
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-variable '{linux(out/'harness.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=40)
 (out/'run.log').write_text(p.stdout+p.stderr)
 report={'status':'PASS_ACTUAL_TEARDOWN_FUNCTION' if p.returncode==0 and 'F332_LIFETIME_PASS' in p.stdout else 'FAIL','provider_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'hardware':False,'evidence':p.stdout.strip(),'errors':p.stderr[-1500:]}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'path':str(out/'result.json'),**report},indent=2));return report['status']=='FAIL'
if __name__=='__main__':raise SystemExit(main())
