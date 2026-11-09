"""Exercise actual F367 pair publication, controls, policy and RAM snapshots."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'work/kernel-port/f367-functional'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
CONTEXT=r'''
#include <assert.h>
#include <pthread.h>
#include <errno.h>
#include <stdio.h>
#include "f327_oem_requests.h"
static pthread_mutex_t request_lock=PTHREAD_MUTEX_INITIALIZER;
static struct f327_oem_requests requests;static bool ready,hardware_enable=true;
static unsigned wakes,queued;static int system_wq,poll_work;
#define spin_lock_irqsave(l,f) do{(f)=0;pthread_mutex_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);pthread_mutex_unlock(l);}while(0)
#define EXPORT_SYMBOL(x) typedef int export_##x
static void f338_ipc_wake(void){__sync_fetch_and_add(&wakes,1);}
static void mod_delayed_work(int q,int*w,int d){(void)q;assert(w==&poll_work&&!d);__sync_fetch_and_add(&queued,1);}
#include "f367_context.inc"
static void*reader(void*p){unsigned i;uint32_t c,b,g;(void)p;for(i=0;i<20000;i++){g=radar_get_context(&c,&b);assert(g&&((c==36&&b==80)||(c==52&&b==20)));}return NULL;}
int main(void){pthread_t t;unsigned i;uint32_t c,b,g;uint64_t epoch;
 f327_oem_init(&requests,36,80);ready=true;
 assert(!radar_set_context(36,80)&&requests.epoch==1&&ready&&!wakes);
 assert(radar_set_context(52,80)==-EINVAL&&requests.epoch==1);
 assert(!radar_set_context(52,20)&&requests.epoch==2&&!ready&&wakes==1&&queued==1);
 assert(radar_get_context(&c,&b)==2&&c==52&&b==20);
 pthread_create(&t,NULL,reader,NULL);
 for(i=0;i<10000;i++)assert(!radar_set_context(i&1?36:52,i&1?80:20));
 pthread_join(t,NULL);epoch=requests.epoch;
 assert(!radar_set_context(36,80)&&requests.epoch==epoch);
 requests.exhausted=true;assert(radar_set_context(52,20)==-EOVERFLOW);
 g=radar_get_context(&c,&b);assert(!g&&c==36&&b==80);
 puts("F367_CONTEXT_PASS coherent_pair_reads=20000 transitions=10000 invalid_and_exhausted=blocked hardware=0");return 0;}
'''
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;
#define HZ 200u
#define PAGE_SIZE 4096
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_MODE_11AC_VHT20PM 11
#define IEEE80211_F_DOTH 1
#define IEEE80211_FEXT_TPC 2
#define IEEE80211_CHAN_DFS 4
#define IEEE80211_CHAN_RADAR 8
#define DFS_RQMT_EU 2
#define CTRY_SPAIN 724
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)-1)
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v,x) ((v)=(x))
#define DEFINE_SPINLOCK(x) int x
#define spin_lock_irqsave(l,f) do{assert((l)!=NULL);(f)=0;}while(0)
#define spin_unlock_irqrestore(l,f) do{assert((l)!=NULL);(void)(f);}while(0)
#define pr_info(...) do{}while(0)
#define pr_err_ratelimited(...) do{}while(0)
#define module_param_cb(a,b,c,d) typedef int parameter_##a
#define scnprintf snprintf
struct kernel_param{int unused;};struct kernel_param_ops{int(*get)(char*,const struct kernel_param*);int(*set)(const char*,const struct kernel_param*);};
struct ieee80211_channel{unsigned ic_ieee,ic_flags;};
struct ieee80211com{struct ieee80211_channel*ic_curchan;unsigned ic_opmode,ic_radar_bw,ic_phymode,ic_flags,ic_flags_ext,ic_country_code;bool repeater;};
static struct ieee80211_channel c36={36,0},c52={52,IEEE80211_CHAN_DFS};static struct ieee80211com ic;
static struct{struct ieee80211com*ic;struct ieee80211_channel*cac_chan;bool enabled,xmit_stopped;unsigned region;}qdrv_radar_cb;
static struct{u32 cac_generation;bool timed_out;}qdrv_f332;
static struct{bool tx_fault,needs_cac;}qdrv_f338_health;
static bool qdrv_radar_configured,stop_fails;static u64 now_ns;static u32 jiffies,generation,ctx_channel,ctx_bw,ctx_epoch;
static unsigned stops,disables,cancels,software_dispatches,checks;
static u64 ktime_get_ns(void){return now_ns;}
static u64 div_u64(u64 n,u32 d){return n/d;}
static bool ieee80211_is_repeater(struct ieee80211com*p){return p->repeater;}
static bool ieee80211_is_chan_radar_detected(struct ieee80211_channel*p){return !!(p->ic_flags&IEEE80211_CHAN_RADAR);}
static struct ieee80211_channel*ieee80211_find_channel_by_ieee(struct ieee80211com*p,unsigned ch){assert(p==&ic);return ch==52?&c52:ch==36?&c36:NULL;}
static u32 qdrv_f332_generation(void){return generation;}
static bool qdrv_f332_ready_stopping(void){return false;}
static bool qdrv_f332_complete_cac(struct ieee80211_channel*ch){return ch&&ch==ic.ic_curchan&&generation&&generation==qdrv_f332.cac_generation;}
static bool qdrv_f338_needs_cac(void){return qdrv_f338_health.needs_cac;}
static bool qdrv_f338_force_tx_off(void){stops++;if(stop_fails){qdrv_f338_health.tx_fault=true;return false;}qdrv_radar_cb.xmit_stopped=true;return true;}
static void sys_disable_rdetection(void){disables++;generation=0;}
static void stop_cac(void){cancels++;qdrv_radar_cb.cac_chan=NULL;}
static bool sysfs_streq(const char*a,const char*b){size_t n=strlen(a);return !strcmp(a,b)||(n&&a[n-1]=='\n'&&n==strlen(b)+1&&!strncmp(a,b,n-1));}
static u32 radar_get_context(u32*c,u32*b){*c=ctx_channel;*b=ctx_bw;return ctx_epoch;}
static void qdrv_radar_detected(struct ieee80211com*,u8);
#include "qdrv_f367_ap.inc"
#include "qdrv_f367_control.inc"
static void qdrv_radar_detected(struct ieee80211com*p,u8 escape){assert(p==&ic&&escape==36);software_dispatches++;qdrv_f367_mark_radar();c52.ic_flags|=IEEE80211_CHAN_RADAR;ic.ic_curchan=&c36;f367_on_dfs=false;generation=0;ctx_channel=36;ctx_epoch++;}
#define CHECK(x) do{checks++;assert(x);}while(0)
static void time_ms(u64 n){now_ns=n*1000000ULL;jiffies=(u32)(n*HZ/1000);}
static void snapshot(const char*label){char b[4096];int n=f367_state_get(b,NULL);assert(n>0&&n<(int)sizeof(b));printf("SNAPSHOT %s %s",label,b);}
'''
TEST=r'''
int main(void){u64 deadline;unsigned before;
 memset(&ic,0,sizeof(ic));ic.ic_curchan=&c36;ic.ic_opmode=6;ic.ic_radar_bw=80;ic.ic_phymode=13;ic.ic_country_code=724;ic.ic_flags=1;ic.ic_flags_ext=2;
 qdrv_radar_cb.ic=&ic;qdrv_radar_cb.enabled=true;qdrv_radar_cb.region=2;qdrv_radar_configured=true;ctx_channel=36;ctx_bw=80;ctx_epoch=7;
 time_ms(100);qdrv_f367_init();CHECK(f367_quarantine_deadline_ns-f367_quarantine_start_ns==1800000000000ULL);snapshot("initial");
 CHECK(f367_control_set("PREPARE52",NULL)==-EBUSY&&!stops&&!f367_transition_prepared);
 time_ms(1800099);CHECK(f367_control_set("PREPARE52",NULL)==-EBUSY&&!stops);
 time_ms(1800100);CHECK(!f367_control_set("PREPARE52",NULL)&&stops==1&&f367_transition_prepared);CHECK(!qdrv_f367_tx_allowed());
 ic.ic_curchan=&c52;ic.ic_radar_bw=80;CHECK(!qdrv_f367_context_admit(&c52));
 ic.ic_radar_bw=20;ic.ic_phymode=11;ic.ic_country_code=826;CHECK(!qdrv_f367_context_admit(&c52));ic.ic_country_code=724;
 CHECK(qdrv_f367_context_admit(&c52)&&!f367_transition_prepared&&f367_on_dfs);
 generation=8;ctx_epoch=8;ctx_channel=52;ctx_bw=20;qdrv_f332.cac_generation=8;qdrv_radar_cb.cac_chan=&c52;
 CHECK(qdrv_f367_cac_begin(&c52));snapshot("cac");deadline=f367_cac_deadline_ns;
 time_ms(1870099);CHECK(!qdrv_f367_cac_finish(&c52)&&!qdrv_f367_tx_allowed());
 time_ms(1870100);CHECK(qdrv_f367_cac_finish(&c52)&&qdrv_f367_tx_allowed());qdrv_radar_cb.cac_chan=NULL;snapshot("service");
 generation=9;CHECK(!qdrv_f367_tx_allowed());qdrv_f332.cac_generation=9;CHECK(qdrv_f367_cac_begin(&c52));CHECK(f367_cac_deadline_ns>deadline);
 time_ms(1940100);CHECK(qdrv_f367_cac_finish(&c52)&&qdrv_f367_tx_allowed());
 CHECK(!f367_control_set("RADAR",NULL)&&software_dispatches==1&&f367_software_injections==1);snapshot("nop");deadline=f367_nop_deadline_ns;before=stops;
 CHECK(f367_control_set("PREPARE52",NULL)==-EBUSY&&f367_nop_deadline_ns==deadline&&stops==before&&!f367_control_fault);
 time_ms(3740099);c52.ic_flags=IEEE80211_CHAN_DFS;CHECK(f367_control_set("PREPARE52",NULL)==-EBUSY&&f367_nop_deadline_ns==deadline);
 time_ms(3740100);CHECK(!f367_control_set("PREPARE52",NULL)&&f367_transition_prepared);
 ic.ic_curchan=&c52;CHECK(qdrv_f367_context_admit(&c52));generation=11;qdrv_f332.cac_generation=11;qdrv_radar_cb.cac_chan=&c52;
 CHECK(qdrv_f367_cac_begin(&c52)&&!qdrv_f367_tx_allowed());time_ms(3810099);CHECK(!qdrv_f367_cac_finish(&c52));time_ms(3810100);CHECK(qdrv_f367_cac_finish(&c52));
 CHECK(f367_control_set("RADAR",NULL)==-EPERM);CHECK(!f367_control_set("ABORT",NULL)&&f367_control_fault&&!qdrv_f367_tx_allowed());CHECK(f367_control_set("PREPARE52",NULL)==-EIO);snapshot("aborted");
 printf("F367_FUNCTIONAL_CONTROL_PASS checks=%u hardware=0 real_time_elapsed_not_claimed=1\n",checks);return 0;}
'''
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367-functional-'+stamp);out.mkdir(parents=True,exist_ok=False)
 for name in ('f327_oem_requests.h','f316_portable.h','f367_context.inc'):shutil.copyfile(SOURCE/'kernel'/name,out/name)
 for name in ('f367_ap_policy.h','qdrv_f367_ap.inc','qdrv_f367_control.inc'):shutil.copyfile(SOURCE/'qdrv/qdrv'/name,out/name)
 (out/'context.c').write_bytes(CONTEXT.encode());(out/'control.c').write_bytes((PRE+TEST).encode())
 script=f"set -eu\ncc -std=c11 -O2 -pthread -Wall -Wextra -Werror -pedantic '{linux(out/'context.c')}' -o '{linux(out/'context')}'\n'{linux(out/'context')}'\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-const-variable -Wno-unused-parameter -pedantic '{linux(out/'control.c')}' -o '{linux(out/'control')}'\n'{linux(out/'control')}'\n"
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=40)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 snapshots={}
 if not run.returncode:
  for line in run.stdout.splitlines():
   if line.startswith('SNAPSHOT '):_,name,data=line.split(' ',2);snapshots[name]=json.loads(data)
  assert snapshots['initial']['quarantine_remaining_ms']==1800000 and snapshots['initial']['tx_admission']==1
  assert snapshots['cac']['cac_valid_continuity']==1 and snapshots['cac']['tx_admission']==0
  assert snapshots['cac']['cac_deadline_ms']-snapshots['cac']['cac_started_ms']==70000
  assert snapshots['nop']['nop_target_channel']==52 and snapshots['nop']['channel']==36 and snapshots['nop']['nop_remaining_ms']==1800000
  assert snapshots['nop']['nop_deadline_ms']-snapshots['nop']['nop_started_ms']==1800000
  assert snapshots['aborted']['control_fault']==1 and snapshots['aborted']['tx_admission']==0
 source_pins={str(p.relative_to(SOURCE)):sha(p) for sub in ('kernel','qdrv','uapi') for p in (SOURCE/sub).rglob('*') if p.is_file()}
 result={'schema':'openmitrastar.f367-functional-tests/v1','status':'PASS_ACTUAL_CONTEXT_POLICY_CONTROLS_AND_SNAPSHOT' if not run.returncode else 'FAIL','source_pins':source_pins,'evidence':[line for line in run.stdout.splitlines() if not line.startswith('SNAPSHOT ')],'snapshot_cases':list(snapshots),'errors':run.stderr[-4000:],'hardware_actions':False,'clock':'simulated monotonic ns and kernel ticks; no physical CAC/NOP claim'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**{k:v for k,v in result.items() if k!='source_pins'}},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
