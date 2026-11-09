"""Execute actual F341 stop/PM wrappers with bounded fake kernel primitives."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f341/kernel/f332_provider.c'
def main():
 out=ROOT/'outputs/preflight'/('f341-control-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 src=SOURCE.read_text();old=(ROOT/'work/kernel-port/f338/kernel/f332_provider.c').read_text()
 assert function(src,'radar_wait_stopped')==function(old,'radar_wait_stopped'),'F338 lifetime drain changed'
 pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
typedef long long loff_t;
#define __user
#define CAP_SYS_ADMIN 1
#define WRITE_ONCE(v,x) ((v)=(x))
struct file {int unused;};
static bool administrative=true,copy_failure,diagnostic_stopped,pm_active,acquire_success;
static unsigned long pm_attempts,pm_acquisitions,pm_releases,pm_busy;
static unsigned drained,owned;
static int capable(int cap){assert(cap==CAP_SYS_ADMIN);return administrative;}
static int copy_from_user(void*d,const void*s,size_t n){if(copy_failure)return 1;memcpy(d,s,n);return 0;}
static int radar_wait_stopped(void){assert(diagnostic_stopped);drained++;return 0;}
static bool f332_hw_duty_acquire(uint32_t gen){assert(gen==4&&!owned);if(acquire_success)owned=1;return acquire_success;}
static void f332_hw_duty_release(void){assert(owned);owned=0;}
'''
 test=r'''
int main(void){
 const char good[]="STOP_DIAGNOSTIC\n",bad[]="ARM!_DIAGNOSTIC\n";
 administrative=false;assert(diagnostic_control(0,good,16,0)==-EPERM&&!drained&&!diagnostic_stopped);
 administrative=true;assert(diagnostic_control(0,good,15,0)==-EINVAL&&!drained);
 assert(diagnostic_control(0,bad,16,0)==-EINVAL&&!drained);
 copy_failure=true;assert(diagnostic_control(0,good,16,0)==-EFAULT&&!drained);
 copy_failure=false;assert(diagnostic_control(0,good,16,0)==16&&drained==1&&diagnostic_stopped);
 acquire_success=false;assert(!f341_duty_acquire(4)&&pm_attempts==1&&pm_busy==1&&!pm_active&&!owned);
 acquire_success=true;assert(f341_duty_acquire(4)&&pm_attempts==2&&pm_acquisitions==1&&pm_active&&owned);
 f341_duty_release();assert(pm_releases==1&&!pm_active&&!owned);
 puts("F341_CONTROL_PASS cases=8 stop_is_software_drain=1 original_drain_unchanged=1 hardware=0");return 0;
}
'''
 (out/'harness.c').write_bytes((pre+'\n'.join(function(src,n) for n in ('f341_duty_acquire','f341_duty_release','diagnostic_control'))+test).encode())
 (out/'run.sh').write_bytes((f"set -eu\ncc -std=c11 -Wall -Wextra -Werror -Wno-sign-compare -O2 '{linux(out/'harness.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n").encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'status':'PASS_ACTUAL_F341_CONTROL' if not p.returncode else 'FAIL','provider_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'evidence':p.stdout.strip(),'errors':p.stderr[-2500:],'hardware':False,'wifi_physical':'USER_DEFERRED'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
