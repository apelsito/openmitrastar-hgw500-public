"""Focal preservation and observer tests; no firmware build or hardware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import f367r9_hostlink_trace_patch as patch

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'work/kernel-port/f367r7-clock-publication/qdrv/qdrv/qdrv_hostlink.c'
PEER=ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
typedef uint32_t u32;typedef uint64_t u64;
typedef struct{int value;}atomic_t;
#define ATOMIC_INIT(n) {n}
static int atomic_cmpxchg(atomic_t*a,int old,int new){int v=a->value;if(v==old)a->value=new;return v;}
static void atomic_set(atomic_t*a,int n){a->value=n;}
static int atomic_read(atomic_t*a){return a->value;}
static int atomic_inc_return(atomic_t*a){return ++a->value;}
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v,n) ((v)=(n))
#define smp_wmb() do{}while(0)
#define smp_rmb() do{}while(0)
static u64 now_ns;static u32 jiffies=123;
static u64 ktime_get_ns(void){return now_ns;}
static bool in_irq(void){return false;}static bool in_serving_softirq(void){return true;}
static bool irqs_disabled(void){return false;}static unsigned preempt_count(void){return 256;}
static struct{unsigned g_calstate;}g_qtn_params={3};
struct shared{unsigned calstate;};static struct shared shared_value={1},*soc_shared_params=&shared_value;
#define QTN_CALSTATE_DEFAULT 3
static unsigned lines;static char last[1024];
static void trace_print(const char*fmt,...){va_list a;va_start(a,fmt);vsnprintf(last,sizeof(last),fmt,a);va_end(a);lines++;puts(last);}
#define pr_info(...) trace_print(__VA_ARGS__)
'''
TEST=r'''
int main(void){struct qdrv_f367r9_wait_trace t,ignored;
 assert(!qdrv_f367r9_hostlink_trace_active());qdrv_f367r9_hostlink_trace_arm(36);assert(!qdrv_f367r9_hostlink_trace_active());
 ignored=qdrv_f367r9_wait_begin(38,"waiting for empty mbox",50,jiffies);assert(!ignored.active&&!lines);
 now_ns=1;qdrv_f367r9_hostlink_trace_arm(52);assert(qdrv_f367r9_hostlink_trace_active());
 t=qdrv_f367r9_wait_begin(38,"waiting for ioctl completion",5000,jiffies);assert(t.active&&lines==1&&t.budget_ticks==5000);
 assert(strstr(last,"cal_global=3 cal_shared=1 cal_default=3")&&strstr(last,"event=before"));
 now_ns=1000000001ULL;qdrv_f367r9_wait_progress(&t);assert(lines==2&&strstr(last,"delta_ticks=0"));
 jiffies+=7;now_ns+=1000000000ULL;qdrv_f367r9_wait_progress(&t);assert(lines==3&&strstr(last,"delta_ticks=7"));
 qdrv_f367r9_wait_end(&t,1);assert(lines==4&&strstr(last,"event=after")&&strstr(last,"timeout=1"));
 ignored=qdrv_f367r9_wait_begin(6,"waiting for empty mbox",50,jiffies);assert(!ignored.active&&lines==4);
 f367r9_csa_timer_trace("before",now_ns);assert(strstr(last,"OMF367R9_CSA event=before")&&strstr(last,"softirq=1"));
 f367r9_csa_timer_trace("after",now_ns);assert(strstr(last,"OMF367R9_CSA event=after"));
 now_ns=7000000001ULL;qdrv_f367r9_hostlink_trace_arm(52);assert(qdrv_f367r9_hostlink_trace_active());
 for(unsigned i=0;i<100;i++)qdrv_f367r9_wait_begin(17,"waiting for MuC dequeue",50,jiffies);
 assert(lines==51); /* 48 bounded host lines + 1 exhaustion + 2 peer lines */
 now_ns=8000000001ULL;assert(!qdrv_f367r9_hostlink_trace_active());
 ignored=qdrv_f367r9_wait_begin(17,"waiting for empty mbox",50,jiffies);assert(!ignored.active&&lines==51);
 assert(jiffies==130&&g_qtn_params.g_calstate==3&&soc_shared_params->calstate==1);
 puts("F367R9_TRACE_HELPERS_PASS arm_once=1 window_ms=8000 progress_ns_and_ticks=1 opcode_filter=1 bounded_host_lines=49 peer_lines=2 state_unmodified=1 hardware=0");return 0;}
'''

def main():
 out=ROOT/'outputs/preflight'/('f367r9-hostlink-trace-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 h=HOST.read_text();w=PEER.read_text();hp=patch.patch_hostlink(h);wp=patch.patch_peer_csa(w)
 assert patch.strip_observation(hp)==h,'hostlink semantics changed'
 assert patch.strip_observation(wp)==w,'peer semantics changed'
 for method,text in ((patch.patch_hostlink,hp),(patch.patch_peer_csa,wp)):
  try:method(text)
  except ValueError:pass
  else:raise AssertionError('duplicate patch accepted')
 (out/'hostlink-patched.c').write_text(hp);(out/'peer-patched.c').write_text(wp)
 (out/'test.c').write_text(PRE+patch.HOST_HELPERS+patch.PEER_HELPERS+TEST)
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh','-c',"cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-variable '"+linux(out/'test.c')+"' -o '"+linux(out/'test')+"' && '"+linux(out/'test')+"'"]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/'stdout.txt').write_text(p.stdout);(out/'stderr.txt').write_text(p.stderr)
 checks=dict(host_original_recovered_exactly=True,peer_original_recovered_exactly=True,duplicate_patch_rejected=True,trace_helpers_pass=p.returncode==0)
 pins={str(path):sha(path) for path in (Path(__file__).resolve(),Path(patch.__file__).resolve(),HOST,PEER)}
 result=dict(schema='openmitrastar.f367r9-hostlink-trace-test/v1',status='PASS_OBSERVATION_PATCH_PRESERVES_ORIGINAL' if all(checks.values()) else 'FAIL',checks=checks,source_pins=pins,stdout_tail=p.stdout.splitlines()[-1:] if p.stdout else [],stderr=p.stderr[-5000:],hardware_actions=False,firmware_sources_modified=False,firmware_compiled=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return p.returncode
if __name__=='__main__':raise SystemExit(main())
