"""Test both clocks, real periodic tick delivery, wrap and conservative state."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/preflight/f367r6-clock-contract-20260922T193202Z'
SRC=ROOT/'work/kernel-port/f367r7-clock-publication'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
TEST=r'''
static char state_text[4096];static unsigned checks;
#define VERIFY(c) do{checks++;assert(c);}while(0)
static unsigned field(const char*name){unsigned value;f367_state_get(state_text,NULL);assert(!number(state_text,name,&value));return value;}
static void cac_start(void){ic.ic_curchan=&ic.ic_channels[1];ic.ic_radar_bw=20;ic.ic_phymode=11;ic.ic_flags=1;ic.ic_flags_ext=2;qdrv_radar_cb.enabled=true;qdrv_f332.cac_generation=generation=7;qdrv_radar_cb.cac_chan=ic.ic_curchan;assert(qdrv_f367_cac_begin(ic.ic_curchan));}
int main(void){u32 ticks_deadline;u64 ns_deadline;unsigned i;
 VERIFY(HZ==100&&sizeof(f367_u32)==4&&sizeof(f367_s32)==4);
 start_at(146);ticks_deadline=f367_policy.boot_until;ns_deadline=f367_quarantine_deadline_ns;
 VERIFY(field("tick_hz")==100&&field("jiffies_u32")==0xffffc3d8U&&field("boot_until_ticks")==164600);
 elapsed(1800*HZ-1,0);VERIFY(field("quarantine_active")==1&&field("quarantine_remaining_ms")==10);
 elapsed(1,0);VERIFY(field("quarantine_active")==0&&field("quarantine_remaining_ms")==0&&store_value("PREPARE52\n")==10);
 start_at(146);ticks_deadline=f367_policy.boot_until;ns_deadline=f367_quarantine_deadline_ns;
 elapsed(1800*HZ,1000);VERIFY(field("quarantine_ns_remaining_ms")==0&&field("quarantine_tick_remaining_ms")==10000&&field("quarantine_remaining_ms")==10000&&field("quarantine_active")==1);
 VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(last_clock_reason,"boot-ticks"));
 elapsed(999,0);VERIFY(field("quarantine_remaining_ms")==10&&field("quarantine_active")==1);
 elapsed(1,0);VERIFY(field("quarantine_remaining_ms")==0&&field("quarantine_active")==0&&store_value("PREPARE52\n")==10);
 VERIFY(f367_policy.boot_until==ticks_deadline&&f367_quarantine_deadline_ns==ns_deadline);
 start_at(146);elapsed(1800*HZ,0);now_ns=f367_quarantine_deadline_ns-1;
 VERIFY(field("quarantine_tick_remaining_ms")==0&&field("quarantine_ns_remaining_ms")==1&&field("quarantine_remaining_ms")==1&&field("quarantine_active")==1);
 VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(last_clock_reason,"boot-ns"));now_ns++;
 VERIFY(field("quarantine_remaining_ms")==0&&store_value("PREPARE52\n")==10);
 start_at(146);elapsed(1800*HZ,0);cac_start();ticks_deadline=f367_policy.cac_until;ns_deadline=f367_cac_deadline_ns;
 elapsed(70*HZ,5);VERIFY(field("cac_ns_remaining_ms")==0&&field("cac_tick_remaining_ms")==50&&field("cac_remaining_ms")==50);
 VERIFY(!qdrv_f367_cac_finish(ic.ic_curchan));elapsed(5,0);VERIFY(field("cac_remaining_ms")==0&&qdrv_f367_cac_finish(ic.ic_curchan));
 VERIFY(f367_policy.cac_until==ticks_deadline&&f367_cac_deadline_ns==ns_deadline);
 start_at(146);elapsed(1800*HZ,0);cac_start();elapsed(70*HZ,0);now_ns=f367_cac_deadline_ns-1;
 VERIFY(field("cac_tick_remaining_ms")==0&&field("cac_ns_remaining_ms")==1&&field("cac_remaining_ms")==1&&!qdrv_f367_cac_finish(ic.ic_curchan));now_ns++;
 VERIFY(field("cac_remaining_ms")==0&&qdrv_f367_cac_finish(ic.ic_curchan));
 start_at(146);elapsed(1800*HZ,0);qdrv_f367_mark_radar();ticks_deadline=f367_policy.nop_until;ns_deadline=f367_nop_deadline_ns;
 elapsed(1800*HZ,1000);VERIFY(field("nop_ns_remaining_ms")==0&&field("nop_tick_remaining_ms")==10000&&field("nop_remaining_ms")==10000&&field("nop_active")==1);
 VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(last_clock_reason,"nop-ticks"));elapsed(1000,0);
 VERIFY(field("nop_active")==0&&field("nop_remaining_ms")==0&&f367_policy.nop_until==ticks_deadline&&f367_nop_deadline_ns==ns_deadline);
 start_at(146);elapsed(1800*HZ,0);qdrv_f367_mark_radar();elapsed(1800*HZ,0);now_ns=f367_nop_deadline_ns-1;
 VERIFY(field("nop_tick_remaining_ms")==0&&field("nop_ns_remaining_ms")==1&&field("nop_remaining_ms")==1&&field("nop_active")==1);
 VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(last_clock_reason,"nop-ns"));now_ns++;
 VERIFY(field("nop_active")==0&&field("nop_remaining_ms")==0);
 start_at(146);elapsed(1800*HZ,0);jiffies_64=0xffffffffULL-10;qdrv_f367_mark_radar();ticks_deadline=f367_policy.nop_until;
 elapsed(1800*HZ-1,0);VERIFY(field("nop_active")==1&&field("nop_remaining_ms")==10);elapsed(1,0);
 VERIFY(field("nop_active")==0&&field("nop_remaining_ms")==0&&f367_policy.nop_until==ticks_deadline);
 start_at(146);elapsed(1800*HZ,0);f367_transition_prepared=true;VERIFY(store_value("PREPARE52\n")==-EBUSY&&!strcmp(last_clock_reason,"transition"));
 for(i=0;i<sizeof(state_text);i++){if(!state_text[i])break;}
 VERIFY(i<4095);
 printf("F367R7_DUAL_CLOCK_PUBLICATION_PASS checks=%u hz=%u producer=actual_arc_periodic initial_jiffies_wrap=covered ns_lag=covered tick_lag=covered deadlines_unchanged=1 hardware=0\n",checks,HZ);
 return 0;
}
'''
def main():
 out=ROOT/'outputs/preflight'/('f367r7-clock-publication-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 code=(BASE/'clock.c').read_text();code=code[:code.index('int main(void)')]
 old='static void trace_warning(const char *format,const char *reason,int error){(void)format;(void)error;snprintf(reject_reason,sizeof(reject_reason),"%s",reason);}'
 new='static char last_clock_reason[80];\nstatic void trace_warning(const char *format,const char *reason,...){snprintf(reject_reason,sizeof(reject_reason),"%s",reason);if(strstr(format,"POLICY_CLOCK_REJECT"))snprintf(last_clock_reason,sizeof(last_clock_reason),"%s",reason);}'
 assert code.count(old)==1;code=code.replace(old,new)+TEST
 for n in ('f367_ap_policy.h','qdrv_f367_ap.inc','qdrv_f367_control.inc'):shutil.copyfile(SRC/'qdrv/qdrv'/n,out/n)
 for n in ('f367r5_oem_ioctl.h','om-f367-dfs-profile.c'):shutil.copyfile(BASE/n,out/n)
 (out/'test.c').write_bytes(code.encode())
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={linux(out)}
cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-variable -Wno-unused-const-variable -Wno-unused-parameter -Wno-sign-compare "$out/test.c" -o "$out/clock-host"
"$out/clock-host" > "$out/host.log"
{tc}gcc --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=gnu11 -Os -mno-atomic -static -ffunction-sections -fdata-sections -Wl,--gc-sections -Wl,--build-id=none "$out/test.c" -o "$out/clock-arc"
{tc}objdump -d "$out/clock-arc" > "$out/clock-arc.disassembly"
'''
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 source=json.loads((SRC/'source-manifest.json').read_text())
 result=dict(schema='openmitrastar.f367r7-clock-publication-test/v1',status='PASS_F367R7_DUAL_CLOCK_PUBLICATION' if not run.returncode else 'FAIL',host_output=(out/'host.log').read_text() if (out/'host.log').exists() else '',stderr=run.stderr[-5000:],reused_actual_clock_producer={'path':str(BASE/'result.json'),'sha256':sha(BASE/'result.json')},source_pins={str(p):sha(p) for p in [Path(__file__),BASE/'clock.c',SRC/'qdrv/qdrv/qdrv_f367_control.inc',SRC/'qdrv/qdrv/qdrv_f367_ap.inc',SRC/'qdrv/qdrv/f367_ap_policy.h']},admission_guard_unchanged=source['admission_guard_unchanged'],deadline_producers_unchanged=source['deadline_producers_unchanged'],arc_binary={'path':str(out/'clock-arc'),'sha256':sha(out/'clock-arc')} if (out/'clock-arc').exists() else None,hardware_actions=False,physical_tick_loss_measured=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return run.returncode
if __name__=='__main__':main()
