"""Replay the actual periodic kernel tick producer against the sealed policy."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess,shutil
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/preflight/f367r5-regulatory-route-20260922T174157Z'
KERNEL='/home/user/openmitrastar-build/f358-flash-arbitration-20260921T173956Z/linux'
CONFIG=Path('/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/f363.config')
QDRV=Path('/workspace/OpenMitraStar-build/f367r5/f367r5-profile-20260922T174325Z/a/qdrv.ko')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def wsl(*args):return subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',*args],capture_output=True,text=True,check=True).stdout
PRE=r'''
typedef int64_t ktime_t;
typedef int irqreturn_t;
#define IRQ_HANDLED 1
#define TIMER_CTRL_NH 2
#define ARC_REG_TIMER0_CTRL 1
#define TICK_NSEC (1000000000LL/HZ)
#define CPU_PROFILING 0
static int tick_do_timer_cpu=0,jiffies_lock,jiffies_seq;
static ktime_t tick_next_period;
static unsigned delivered_irqs,control_writes;
struct clock_event_device {ktime_t next_event;bool periodic;void(*event_handler)(struct clock_event_device*);};
static struct clock_event_device arc_clockevent_device;
#define this_cpu_ptr(p) (p)
#define raw_spin_lock(p) ((void)(p))
#define raw_spin_unlock(p) ((void)(p))
#define write_seqcount_begin(p) ((void)(p))
#define write_seqcount_end(p) ((void)(p))
static ktime_t ktime_add_ns(ktime_t a,u64 b){return a+b;}
static void update_wall_time(void){}
static void update_process_times(int mode){(void)mode;}
static int get_irq_regs(void){return 0;}
static int user_mode(int unused){(void)unused;return 0;}
static void profile_tick(int unused){(void)unused;}
static void calc_global_load(void){}
static int smp_processor_id(void){return 0;}
static bool clockevent_state_oneshot(struct clock_event_device*p){return !p->periodic;}
static bool clockevent_state_periodic(struct clock_event_device*p){return p->periodic;}
static int clockevents_program_event(struct clock_event_device*dev,ktime_t next,bool force){(void)dev;(void)next;(void)force;return 0;}
static bool timekeeping_valid_for_hres(void){return true;}
static void qtn_topaz_timer_wdt_pet(void){}
static void write_aux_reg(unsigned reg,unsigned value){assert(reg==ARC_REG_TIMER0_CTRL&&value==3);control_writes++;}
'''
TEST=r'''
static void start_at(unsigned uptime_seconds){reset();memset(&f367_policy,0,sizeof(f367_policy));jiffies_64=(u64)INITIAL_JIFFIES+(u64)uptime_seconds*HZ;now_ns=(u64)uptime_seconds*1000000000ULL;qdrv_f367_init();
 arc_clockevent_device.periodic=true;arc_clockevent_device.event_handler=tick_handle_periodic;delivered_irqs=control_writes=0;
 {int channel52=52;assert(!ieee80211_subioctl_set_chan_dfs_required(&dev,&channel52,1));}
}
static void elapsed(unsigned ticks,unsigned missed){unsigned i;assert(missed<=ticks);for(i=0;i<ticks;i++){now_ns+=TICK_NSEC;if(i>=missed){assert(timer_irq_handler(0,NULL)==IRQ_HANDLED);delivered_irqs++;}}}
int main(void){char state_text[4096];u32 deadline;u64 nsdeadline;unsigned checks=0;
#define VERIFY(c) do{checks++;assert(c);}while(0)
 VERIFY(sizeof(u32)==4&&sizeof(f367_u32)==4&&sizeof(f367_s32)==4&&HZ==100);
 start_at(146);deadline=f367_policy.boot_until;nsdeadline=f367_quarantine_deadline_ns;
 VERIFY((u32)jiffies==0xffffc3d8U&&deadline==164600U);
 elapsed(1800*HZ,0);VERIFY(f367_dfs_clear(&f367_policy,(u32)jiffies));VERIFY(store_value("PREPARE52\n")==10);
 start_at(146);deadline=f367_policy.boot_until;nsdeadline=f367_quarantine_deadline_ns;
 elapsed(1800*HZ,1000);f367_state_get(state_text,NULL);
 VERIFY(strstr(state_text,"\"quarantine_active\":0")&&strstr(state_text,"\"quarantine_remaining_ms\":0"));
 VERIFY(f367_policy.initialized&&!f367_policy.nop&&!f367_transition_prepared&&now_ns>=nsdeadline);
 VERIFY(!f367_dfs_clear(&f367_policy,(u32)jiffies));VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(reject_reason,"prepare-policy-clock-nop-or-transition"));
 printf("CLOCK_DISCREPANCY source=ARC_TIMER0_PERIODIC hz=%u initial_jiffies=%u jiffies=%u boot_until=%u monotonic_ns=%llu ns_deadline=%llu old_quarantine_ms=0 ticks_remaining=%u irq_events=%u\n",HZ,(u32)INITIAL_JIFFIES,(u32)jiffies,deadline,(unsigned long long)now_ns,(unsigned long long)nsdeadline,deadline-(u32)jiffies,delivered_irqs);
 elapsed(5*HZ,0);VERIFY(store_value("PREPARE52\n")==-EBUSY);VERIFY(f367_policy.boot_until==deadline&&f367_quarantine_deadline_ns==nsdeadline);
 elapsed(5*HZ,0);VERIFY(f367_dfs_clear(&f367_policy,(u32)jiffies)&&store_value("PREPARE52\n")==10);
 VERIFY(f367_policy.boot_until==deadline&&f367_quarantine_deadline_ns==nsdeadline);
 start_at(146);elapsed(1800*HZ-1,0);VERIFY(store_value("PREPARE52\n")==-EBUSY);elapsed(1,0);VERIFY(store_value("PREPARE52\n")==10);
 VERIFY(control_writes==delivered_irqs);
 printf("F367R6_CLOCK_CONTRACT_REPLAY_PASS checks=%u policy_and_tick_producer=actual width32=1 initial_jiffies_wrap=covered hardware=0 physical_tick_loss_not_measured=1\n",checks);
 return 0;
}
'''
def main():
 config=CONFIG.read_text();assert 'CONFIG_HZ=100\n' in config and 'CONFIG_HZ_PERIODIC=y' in config and '# CONFIG_HIGH_RES_TIMERS is not set' in config and '# CONFIG_OPENMITRASTAR_BOOT_TRACE is not set' in config
 out=ROOT/'outputs/preflight'/('f367r6-clock-contract-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 texts={n:wsl('cat',KERNEL+'/'+p) for n,p in {'jiffies.h':'include/linux/jiffies.h','tick-common.c':'kernel/time/tick-common.c','timekeeping.c':'kernel/time/timekeeping.c','arc_timer.c':'drivers/clocksource/arc_timer.c'}.items()}
 for n,s in texts.items():(out/n).write_bytes(s.encode())
 initial=re.search(r'^#define INITIAL_JIFFIES [^\n]+',texts['jiffies.h'],re.M).group(0)
 code=(BASE/'route.c').read_text();a=code.index('int main(int argc,char**argv)');code=code[:a]
 code=code.replace('#define HZ 200u','#define HZ 100u\n'+initial+'\nstatic uint64_t jiffies_64;\n#define jiffies ((uint32_t)jiffies_64)')
 code=code.replace('static u32 jiffies,generation,ctx_channel,ctx_bw,ctx_epoch;','static u32 generation,ctx_channel,ctx_bw,ctx_epoch;')
 code=code.replace('jiffies=20;','jiffies_64=20;').replace('jiffies=380000;','jiffies_64=380000;')
 producer=extract(texts['timekeeping.c'],'do_timer')+extract(texts['tick-common.c'],'tick_periodic')+extract(texts['tick-common.c'],'tick_handle_periodic')+extract(texts['arc_timer.c'],'timer_irq_handler')
 code+=PRE+producer+TEST
 for n in ('f367_ap_policy.h','qdrv_f367_ap.inc','qdrv_f367_control.inc','f367r5_oem_ioctl.h','om-f367-dfs-profile.c'):shutil.copyfile(BASE/n,out/n)
 (out/'clock.c').write_bytes(code.encode())
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={linux(out)}
cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-variable -Wno-unused-const-variable -Wno-unused-parameter -Wno-sign-compare "$out/clock.c" -o "$out/clock-host"
"$out/clock-host" > "$out/host.log"
{tc}gcc --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=gnu11 -Os -mno-atomic -static -ffunction-sections -fdata-sections -Wl,--gc-sections -Wl,--build-id=none "$out/clock.c" -o "$out/clock-arc"
{tc}objdump -d "$out/clock-arc" > "$out/clock-arc.disassembly"
{tc}objdump -dr --disassemble=f367_control_set {linux(QDRV)} > "$out/sealed-control.disassembly"
{tc}objdump -dr --disassemble=qdrv_radar_init {linux(QDRV)} > "$out/sealed-init.disassembly"
'''
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 result=dict(schema='openmitrastar.f367r6-clock-contract/v1',status='PASS_OFFLINE_ACTUAL_TICK_PRODUCER_AND_32BIT_POLICY' if run.returncode==0 else 'FAIL',host_output=(out/'host.log').read_text() if (out/'host.log').exists() else '',stderr=run.stderr[-4000:],kernel_source_pins={n:hashlib.sha256(s.encode()).hexdigest() for n,s in texts.items()},source_pins={str(p):sha(p) for p in [Path(__file__),CONFIG,QDRV,BASE/'route.c']},arc_binary={'path':str(out/'clock-arc'),'sha256':sha(out/'clock-arc')} if (out/'clock-arc').exists() else None,hardware_actions=False,physical_tick_loss_measured=False,conclusion='Status and PREPARE use different predicates; actual periodic tick producer allows a ktime deadline to pass before delivered jiffies reach the retained tick deadline. Signed32 wrap itself passes.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
