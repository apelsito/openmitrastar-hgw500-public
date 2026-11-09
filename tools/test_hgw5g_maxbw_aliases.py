"""Test actual source maxbandwidth460 cases and compile full ARC WLAN unit."""
import argparse
import json
from pathlib import Path
from build_wlan_txmaxmpdu_alias_module import command,run
from compile_hgw5g_cca_abi_fixture import sha
import compile_f368_changed_objects as context


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 proof=json.loads((a.candidate/'result.json').read_text());source=a.candidate/'ieee80211_wireless.c';assert sha(source)==proof['candidate_sha256']
 text=source.read_text();getstart=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');start=text.index('\tcase OM_OEM_PARAM_MAX_BANDWIDTH:',getstart);end=text.index('\n\tcase ',start+1);get=text[start:end]
 setstart=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');start=text.index('\tcase OM_OEM_PARAM_MAX_BANDWIDTH:',setstart);end=text.index('\n\tcase ',start+1);setter=text[start:end]
 fixture='''#include <assert.h>
#include <stdint.h>
typedef uint8_t u_int8_t;
#define OM_OEM_PARAM_MAX_BANDWIDTH 460
struct ieee80211com{uint8_t ic_max_system_bw;};
static void actual_set(struct ieee80211com*ic,int param,int value){switch(param){
'''+setter+'''\n default:break;}}
static void actual_get(struct ieee80211com*ic,int*param){switch(param[0]&0xffff){
'''+get+'''\n default:break;}}
int main(void){struct ieee80211com ic;unsigned i;int result;for(i=0;i<65536;i++){
actual_set(&ic,460,i);assert(ic.ic_max_system_bw==(uint8_t)i);result=(i<<16)|460;actual_get(&ic,&result);assert(result==(uint8_t)i);
actual_set(&ic,460,-(int)i);assert(ic.ic_max_system_bw==(uint8_t)(-(int)i));}return 0;}
'''
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);result=dict(status='NO_GO',hardware_accessed=False,firmware_eligible=False)
 try:
  run(['gcc','-std=c11','-O1','-g','-fsanitize=address,undefined',str(f),'-o',str(a.output/'fixture')],a.output,a.output/'compile-fixture');run([str(a.output/'fixture')],a.output,a.output/'run-fixture')
  run(command('ieee80211_wireless',a.output,source),context.CONTEXT,a.output/'compile-arc-source')
  result.update(status='PASS_OFFLINE_MAXBW_ALIAS_FIXTURE_ARC_UNIT',source_unchanged=sha(source)==proof['candidate_sha256'],cases=65536,checks=196608,limits='Fullmodule/pair/policy-context qualification pending; no runtimeorRFmutation')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))


if __name__=='__main__':raise SystemExit(main())
