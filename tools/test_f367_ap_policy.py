"""Execute the F367 production admission policy with controlled time/contexts."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
HEADER=ROOT/'work/kernel-port/f367/qdrv/qdrv/f367_ap_policy.h'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
TEST=r'''
#include "f367_ap_policy.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{checks++;assert(x);}while(0)
int main(void){struct f367_ap_policy p;unsigned hz,k;uint32_t b,n;
 for(hz=100;hz<=1000;hz+=100){
  memset(&p,0,sizeof(p));CHECK(!f367_tx_allowed(&p,0,1,52,20,true,true,false));
  b=0xffff0000u;f367_policy_init(&p,b,hz);
  CHECK(f367_tx_allowed(&p,b,0,36,80,true,false,false));
  CHECK(!f367_tx_allowed(&p,b,0,36,80,false,false,false));
  CHECK(!f367_begin_cac(&p,b+1800*hz-1,hz,7,52,20));
  n=b+1800*hz;CHECK(f367_begin_cac(&p,n,hz,7,52,20));
  CHECK(!f367_finish_cac(&p,n+70*hz-1,7,52,20));
  CHECK(!f367_finish_cac(&p,n+70*hz,8,52,20));
  CHECK(!f367_finish_cac(&p,n+70*hz,7,52,40));
  CHECK(f367_finish_cac(&p,n+70*hz,7,52,20));
  CHECK(f367_tx_allowed(&p,n+70*hz,7,52,20,true,true,false));
  CHECK(!f367_tx_allowed(&p,n+70*hz,7,52,20,true,false,false));
  CHECK(!f367_tx_allowed(&p,n+70*hz,8,52,20,true,true,false));
  CHECK(!f367_tx_allowed(&p,n+70*hz,7,52,20,true,true,true));
  CHECK(!f367_tx_allowed(&p,n+70*hz,7,52,20,false,true,false));
  for(k=1;k<=196;k++)if(k!=36&&k!=52)CHECK(!f367_tx_allowed(&p,n+70*hz,7,k,20,true,true,false));
  n+=71*hz;f367_mark_radar(&p,n,hz);
  CHECK(!p.cac_done&&!p.cac_pending&&p.nop);
  CHECK(f367_tx_allowed(&p,n,0,36,80,true,false,false));
  CHECK(!f367_begin_cac(&p,n+1800*hz-1,hz,9,52,20));
  CHECK(!f367_tx_allowed(&p,n+1800*hz,7,52,20,true,true,false));
  CHECK(f367_begin_cac(&p,n+1800*hz,hz,9,52,20));
  CHECK(!f367_finish_cac(&p,n+1870*hz-1,9,52,20));
  CHECK(f367_finish_cac(&p,n+1870*hz,9,52,20));
  CHECK(f367_tx_allowed(&p,n+1870*hz,9,52,20,true,true,false));
  f367_invalidate_cac(&p);CHECK(!f367_tx_allowed(&p,n+1870*hz,9,52,20,true,true,false));
  f367_policy_init(&p,n,hz);CHECK(!f367_begin_cac(&p,n+1800*hz-1,hz,10,52,20));
 }
 printf("F367_AP_POLICY_PASS checks=%u hardware=0 boot_quarantine_is_local_policy=1\n",checks);return 0;}
'''
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367-policy-'+stamp);out.mkdir(parents=True,exist_ok=False)
 (out/'f367_ap_policy.h').write_bytes(HEADER.read_bytes());(out/'test.c').write_bytes(TEST.encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -pedantic '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'schema':'openmitrastar.f367-ap-policy-tests/v1','status':'PASS_ACTUAL_C_AP_DFS_POLICY' if not run.returncode else 'FAIL','source':{'path':str(HEADER),'sha256':sha(HEADER)},'stdout':run.stdout.strip(),'stderr':run.stderr[-3000:],'hardware_actions':False,'test_time':'simulated ticks, including wrap; not real CAC/NOP acceptance'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
