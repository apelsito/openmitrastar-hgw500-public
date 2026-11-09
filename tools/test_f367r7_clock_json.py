"""One affected serialization check; do not rerun the clock-policy bank."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/preflight/f367r7-clock-publication-20260922T193631Z'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 out=ROOT/'outputs/preflight'/('f367r7-clock-json-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 code=(BASE/'test.c').read_text();code=code[:code.index('int main(void)')]+r'''
int main(void){struct{unsigned char pre[16];char json[4096];unsigned char post[16];}b;int n;unsigned i;
 reset();memset(&b,0xa5,sizeof(b));now_ns=0;jiffies_64=0xffffffffULL;generation=ctx_epoch=ctx_channel=ctx_bw=0xffffffffU;
 f367_policy.initialized=true;f367_policy.nop=true;f367_policy.cac_pending=true;f367_policy.cac_done=false;f367_policy.cac_generation=0xffffffffU;
 f367_policy.boot_until=f367_policy.cac_until=f367_policy.nop_until=0x7ffffffeU;
 f367_quarantine_start_ns=f367_quarantine_deadline_ns=f367_cac_start_ns=f367_cac_deadline_ns=f367_nop_start_ns=f367_nop_deadline_ns=0x7fffffffffffffffULL;
 f367_transition_prepared=f367_switch_inflight=true;f367_software_injections=f367_native_callbacks=0xffffffffU;
 n=f367_state_get(b.json,NULL);assert(n>0&&n<4095&&b.json[n]==0);for(i=0;i<16;i++)assert(b.pre[i]==0xa5&&b.post[i]==0xa5);
 printf("%s",b.json);printf("F367R7_MAX_CLOCK_JSON_PASS bytes=%d limit=4096 canaries=unchanged\n",n);return 0;}
'''
 for n in ('f367_ap_policy.h','qdrv_f367_ap.inc','qdrv_f367_control.inc','f367r5_oem_ioctl.h','om-f367-dfs-profile.c'):shutil.copyfile(BASE/n,out/n)
 (out/'max-json.c').write_bytes(code.encode())
 script='set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-variable -Wno-unused-const-variable -Wno-unused-parameter -Wno-sign-compare '+linux(out/'max-json.c')+' -o '+linux(out/'max-json')+'\n'+linux(out/'max-json')+'\n'
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True)
 rows=run.stdout.splitlines();parsed=json.loads(rows[0]) if not run.returncode else {}
 if not run.returncode:
  assert parsed['jiffies_u32']==parsed['cac_generation']==4294967295
  assert parsed['quarantine_deadline_ms']==9223372036854
  assert parsed['quarantine_remaining_ms']==parsed['cac_remaining_ms']==parsed['nop_remaining_ms']==9223372036855
  assert all(parsed[name]>0 for name in ('quarantine_tick_remaining_ms','cac_tick_remaining_ms','nop_tick_remaining_ms'))
 result=dict(schema='openmitrastar.f367r7-max-clock-json/v1',status='PASS_MAX_CLOCK_JSON_BELOW_PAGE_SIZE' if not run.returncode else 'FAIL',bytes=len(rows[0].encode())+1 if rows else 0,page_size=4096,canaries_unchanged=not run.returncode,stdout_tail=rows[-1:] if rows else [],stderr=run.stderr[-3000:],source_pins={str(p):sha(p) for p in [Path(__file__),BASE/'test.c',ROOT/'work/kernel-port/f367r7-clock-publication/qdrv/qdrv/qdrv_f367_control.inc']},hardware_actions=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
