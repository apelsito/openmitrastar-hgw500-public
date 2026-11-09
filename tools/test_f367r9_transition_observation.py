"""Verify observation-only restoration, wrapper forwarding and unchanged JSON."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import f367r9_boundary_patch as patch
from prepare_f367r9_transition_observation import ROOT,BASE,DST,OVERLAY,CTRL,STATUS
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def restored(original,changed,ops):
 for before,after in reversed(ops(original)):
  assert changed.count(after)==1
  changed=changed.replace(after,before,1)
 return changed==original
PRE=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#include <stdarg.h>
typedef uint32_t u32;typedef int atomic_t;
#define ATOMIC_INIT(x) (x)
#define READ_ONCE(v) (*(volatile __typeof__(v) *)&(v))
#define F367R9_NO_RESULT (-4096)
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)-1)
struct ieee80211_channel{unsigned ic_ieee;};
struct ieee80211com{struct ieee80211_channel*ic_curchan;unsigned ic_radar_bw,ic_phymode;};
static struct ieee80211_channel channel={52};static struct ieee80211com ic={&channel,20,11};
static struct{struct ieee80211com*ic;bool enabled;}qdrv_radar_cb={&ic,true};
static bool active;static unsigned logs,calls,last_channel,last_bw,last_kind;static int answer;static unsigned long jiffies;
static int atomic_inc_return(atomic_t*p){return ++*p;}
static bool qdrv_f367r9_hostlink_trace_active(void){return active;}
static int in_irq(void){return 0;}static int in_serving_softirq(void){return 1;}static int irqs_disabled(void){return 0;}static unsigned preempt_count(void){return 256;}
static uint64_t ktime_get_ns(void){return 100;}
static void trace_printf(const char*format,...){char out[1024];va_list ap;int n;va_start(ap,format);n=vsnprintf(out,sizeof(out),format,ap);va_end(ap);assert(n>0&&n<(int)sizeof(out));logs++;}
#define pr_info(...) trace_printf(__VA_ARGS__)
static bool qdrv_f367_context_admit(struct ieee80211_channel*c){assert(c==&channel);calls++;return answer;}
static int radar_set_scan_context(uint8_t c){last_channel=c;calls++;return answer;}
static int radar_set_context(uint8_t c,uint32_t b){last_channel=c;last_bw=b;calls++;return answer;}
static u32 qdrv_f332_wait_ready(unsigned kind,unsigned c,unsigned b){last_kind=kind;last_channel=c;last_bw=b;calls++;return answer;}
'''
TEST=r'''
int main(void){unsigned i,before;
 active=false;qdrv_radar_cb.ic=(struct ieee80211com*)1;qdrv_f367r9_boundary("inactive-invalid-pointer",F367R9_NO_RESULT);assert(!logs);qdrv_radar_cb.ic=&ic;
 active=false;answer=1;assert(f367r9_context_admit(&channel)&&calls==1&&!logs);
 answer=-16;assert(f367r9_scan_context(0)==-16&&last_channel==0&&calls==2&&!logs);
 answer=-22;assert(f367r9_native_context(52,20)==-22&&last_channel==52&&last_bw==20&&calls==3&&!logs);
 answer=7;assert(f367r9_wait_ready(1,52,20)==7&&last_kind==1&&last_channel==52&&last_bw==20&&calls==4&&!logs);
 active=true;before=calls;answer=0;assert(!f367r9_context_admit(&channel)&&calls==before+1&&logs==2);
 answer=-1;assert(f367r9_native_context(52,20)==-1&&calls==before+2&&logs==4);
 for(i=0;i<100;i++)qdrv_f367r9_boundary("test",F367R9_NO_RESULT);
 assert(logs==32);assert(ic.ic_radar_bw==20&&ic.ic_phymode==11&&channel.ic_ieee==52);
 puts("F367R9_BOUNDARY_FORWARDING_PASS call_once=1 original_returns=1 inactive_quiet=1 max_lines=32 state_unchanged=1");return 0;}
'''
def main():
 out=ROOT/'outputs/preflight'/('f367r9-transition-observation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 pairs=[('driver',BASE/'qdrv/qdrv/qdrv_wlan.c',DST/'qdrv/qdrv/qdrv_wlan.c',patch.driver_operations),('radar',BASE/'qdrv/qdrv/qdrv_radar.c',DST/'qdrv/qdrv/qdrv_radar.c',patch.radar_operations),('controller',CTRL,OVERLAY/'usr/sbin/om-f367-control',patch.controller_operations),('status',STATUS,OVERLAY/'usr/sbin/om-f367-status',patch.status_operations)]
 checks={name+'_original_recovered':restored(old.read_text(),new.read_text(),ops) for name,old,new,ops in pairs};assert all(checks.values())
 (out/'forward.c').write_bytes((PRE+patch.RADAR_HELPERS+TEST).encode())
 (out/'run.sh').write_bytes(('set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-variable -Wno-unused-function -Wno-unused-parameter '+linux(out/'forward.c')+' -o '+linux(out/'forward')+'\n'+linux(out/'forward')+'\n').encode())
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e'];run=subprocess.run(cmd+['sh',linux(out/'run.sh')],capture_output=True,text=True)
 checks['wrappers_forward_once_and_preserve_results']=run.returncode==0
 fixture=out/'fixture';fixture.mkdir();(fixture/'provider').mkdir()
 (fixture/'kernel').write_bytes(b'{"schema":"openmitrastar.f367-kernel-state/v1","channel":52,"filter_bw":20}\n')
 (fixture/'provider/status').write_bytes(b'schema=openmitrastar.f341-provider/v1\nstarted=1\nhardware_ready=1\nready=0\ncallbacks=0\njobs_completed=1\n')
 env=['OM_F367_KERNEL_STATE='+linux(fixture/'kernel'),'OM_F367_PROVIDER='+linux(fixture/'provider')]
 old=subprocess.run(cmd+['env',*env,'sh',linux(STATUS)],capture_output=True,text=True)
 quiet=subprocess.run(cmd+['env',*env,'sh',linux(OVERLAY/'usr/sbin/om-f367-status')],capture_output=True,text=True)
 traced=subprocess.run(cmd+['env',*env,'OM_F367_R9_READ_TRACE=1','sh',linux(OVERLAY/'usr/sbin/om-f367-status')],capture_output=True,text=True)
 checks['status_stdout_identical']=old.returncode==quiet.returncode==traced.returncode==0 and old.stdout==quiet.stdout==traced.stdout
 checks['status_default_quiet']=not old.stderr and not quiet.stderr
 checks['status_trace_stderr_only']=len(traced.stderr.splitlines())==6 and all(x.startswith('OMF367R9_SNAPSHOT ') for x in traced.stderr.splitlines())
 json.loads(traced.stdout)
 pins={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f367r9_boundary_patch.py',DST/'qdrv/qdrv/qdrv_f367r9_trace.h',*[p for _,old,new,_ in pairs for p in (old,new)]]}
 result=dict(schema='openmitrastar.f367r9-transition-observation-test/v1',status='PASS_TRANSITION_OBSERVATION_PRESERVES_SEMANTICS' if all(checks.values()) else 'FAIL',checks=checks,stdout=run.stdout,stderr=run.stderr,trace_stderr=traced.stderr,source_pins=pins,hardware_actions=False,no_policy_or_deadline_changes=True)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return 0 if all(checks.values()) else 1
if __name__=='__main__':raise SystemExit(main())
