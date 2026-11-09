"""Only R2 calstate compilation/observation and exact R1 peer preservation."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess
import f367r9_hostlink_trace_patch_r2 as patch
import test_f367r9_hostlink_trace_patch as previous_test
ROOT=previous_test.ROOT
sha=previous_test.sha
linux=previous_test.linux

TEST=r'''
int main(void){struct qdrv_f367r9_wait_trace t;int selected;
 now_ns=1;qdrv_f367r9_hostlink_trace_arm(52);
 t=qdrv_f367r9_wait_begin(38,"waiting for empty mbox",50,jiffies,-1);
 assert(strstr(last,"cal_wait_available=0 cal_wait=-1 cal_shared_available=1 cal_shared_current=1 cal_default=3"));
 shared_value.calstate=3;selected=soc_shared_params->calstate;shared_value.calstate=1;
 t=qdrv_f367r9_wait_begin(17,"waiting for ioctl completion",50,jiffies,selected);
 assert(strstr(last,"cal_wait_available=1 cal_wait=3 cal_shared_available=1 cal_shared_current=1 cal_default=3"));
 now_ns+=1000000000ULL;qdrv_f367r9_wait_progress(&t);
 assert(strstr(last,"event=progress")&&strstr(last,"cal_wait=3")&&strstr(last,"delta_ticks=0"));
 qdrv_f367r9_wait_end(&t,0);assert(strstr(last,"event=after")&&strstr(last,"timeout=0"));
 soc_shared_params=NULL;t=qdrv_f367r9_wait_begin(35,"waiting for empty mbox",50,jiffies,-1);
 assert(strstr(last,"cal_shared_available=0 cal_shared_current=-1"));
 puts("F367R9_CALSTATE_R2_PASS muc_global_absent=1 consumed_snapshot_stable=1 shared_current_distinct=1 unavailable_explicit=1 hardware=0");return 0;}
'''

def main():
 out=ROOT/'outputs/preflight'/('f367r9-hostlink-trace-r2-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 host=previous_test.HOST.read_text();peer=previous_test.PEER.read_text();changed=patch.patch_hostlink(host)
 assert patch.strip_observation(changed)==host
 assert patch.patch_peer_csa(peer)==patch.previous.patch_peer_csa(peer)
 assert 'g_qtn_params' not in changed
 assert changed.count(patch.CAPTURED_IF)==1 and changed.count(patch.ORIGINAL_IF)==0
 pre=previous_test.PRE.replace('static struct{unsigned g_calstate;}g_qtn_params={3};','')
 assert 'g_qtn_params' not in pre
 (out/'test.c').write_text(pre+patch.HOST_HELPERS+TEST)
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh','-c',"cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-variable '"+linux(out/'test.c')+"' -o '"+linux(out/'test')+"' && '"+linux(out/'test')+"'"]
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/'stdout.txt').write_text(run.stdout);(out/'stderr.txt').write_text(run.stderr)
 checks=dict(original_hostlink_recovered_exactly=True,peer_patch_byte_identical=True,one_shared_read_for_branch=True,no_muc_global=True,calstate_observer_pass=run.returncode==0)
 inputs=[Path(__file__).resolve(),Path(patch.__file__).resolve(),Path(patch.previous.__file__).resolve(),Path(previous_test.__file__).resolve(),previous_test.HOST,previous_test.PEER]
 result=dict(schema='openmitrastar.f367r9-hostlink-trace-r2-test/v1',status='PASS_R2_SHARED_CALSTATE_OBSERVATION' if all(checks.values()) else 'FAIL',checks=checks,source_pins={str(p):sha(p) for p in inputs},stdout_tail=run.stdout.splitlines()[-1:],stderr=run.stderr[-4000:],hardware_actions=False,firmware_sources_modified=False,firmware_compiled=False,peer_recompile_required=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
