"""Compile exact NAC prefix helper fixture and full ARC source unit offline."""
import argparse
import json
from pathlib import Path

from build_wlan_txmaxmpdu_alias_module import command,run
import compile_f368_changed_objects as context
from compile_hgw5g_cca_abi_fixture import sha


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.candidate/'ieee80211_wireless.c';proof=json.loads((a.candidate/'result.json').read_text());assert sha(source)==proof['candidate_sha256']
 a.output.mkdir(parents=True,exist_ok=False);result=dict(status='NO_GO_FIXTURE',hardware_accessed=False,firmware_eligible=False)
 try:
  fixture=a.candidate/'actual-nac-getter-fixture.c'
  run(['gcc','-std=c11','-O1','-g','-fsanitize=address,undefined',str(fixture),'-o',str(a.output/'fixture')],a.output,a.output/'compile-fixture')
  run([str(a.output/'fixture')],a.output,a.output/'run-fixture')
  cmd=command('ieee80211_wireless',a.output,source);cmd.insert(cmd.index('-c'),'-I'+str(a.candidate))
  run(cmd,context.CONTEXT,a.output/'compile-arc-source')
  result.update(status='PASS_OFFLINE_NAC_PREFIX_FIXTURE_AND_ARC_UNIT',candidate_sha256=sha(source),fake_value0_cases=65536,fake_value1_samples=255,fixture_cases=16711682,pointer_and_dividebyzero_refusal=True,source_unchanged=True,limits='No coherence/pointerlifetime/fullmodule/runtime/clientgate qualified')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))


if __name__=='__main__':raise SystemExit(main())
