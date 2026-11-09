"""Compile actual dev-mode/stub case blocks and full ARC WLAN source offline."""
import argparse
import json
from pathlib import Path

from build_wlan_txmaxmpdu_alias_module import command,run
import compile_f368_changed_objects as context
from compile_hgw5g_cca_abi_fixture import sha


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--candidate",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 source=a.candidate/"ieee80211_wireless.c";proof=json.loads((a.candidate/"result.json").read_text());assert sha(source)==proof["candidate_sha256"]
 text=source.read_text();start=text.index("\tcase OM_OEM_PARAM_DEVICE_MODE:");end=text.index("\n\t/* Output handling lives",start);get=text[start:end]
 start=text.index("\tcase OM_OEM_PARAM_IGNORE_ICAC_SELECTION:");end=text.index("\n\tcase ",start+1);setbody=text[start:end]
 a.output.mkdir(parents=True,exist_ok=False)
 fixture='''#include <assert.h>
#include <stdint.h>
#define EOPNOTSUPP 95
#define IEEE80211_EXTENDER_ROLE_MBS 1
#define IEEE80211_EXTENDER_ROLE_RBS 2
#define OM_OEM_PARAM_DEVICE_MODE 451
#define OM_OEM_PARAM_IGNORE_ICAC_SELECTION 465
#define OM_OEM_PARAM_FT_OVER_DS 495
struct ieee80211com {uint8_t ic_extender_role;uint32_t flags;};
static int ieee80211_is_repeater(struct ieee80211com *ic){return !!(ic->flags&0x40000);}
static int actual_get(struct ieee80211com *ic,int *param){switch(param[0]&0xffff){
'''+get+'''\n default:break;}return0;}
static int actual_set(int param){switch(param){
'''+setbody+'''\n default:break;}return0;}
int main(void){unsigned role,f,high;int result,expected;struct ieee80211com ic;
for(role=0;role<256;role++)for(f=0;f<2;f++){
ic.ic_extender_role=role;ic.flags=f?0x40000:0;expected=role==1?1:role==2?2:f?3:0;
for(high=0;high<65536;high+=257){result=(high<<16)|451;assert(actual_get(&ic,&result)==0);assert(result==expected);assert(ic.ic_extender_role==role);}}
for(high=0;high<65536;high++){result=(high<<16)|495;assert(actual_get(&ic,&result)==-95);assert(result==(int)((high<<16)|495));}
assert(actual_set(465)==-95);return0;}
'''
 fixture=fixture.replace("return0;","return 0;");path=a.output/"fixture.c";path.write_text(fixture)
 result=dict(status="NO_GO_FIXTURE",hardware_accessed=False,firmware_eligible=False)
 try:
  run(["gcc","-std=c11","-O1","-g","-fsanitize=address,undefined",str(path),"-o",str(a.output/"fixture")],a.output,a.output/"compile-fixture")
  run([str(a.output/"fixture")],a.output,a.output/"run-fixture")
  run(command("ieee80211_wireless",a.output,source),context.CONTEXT,a.output/"compile-arc-unit")
  assert sha(source)==proof["candidate_sha256"]
  result.update(status="PASS_OFFLINE_DEVMODE_STUB_FIXTURE_AND_ARC_UNIT",candidate_sha256=sha(source),actual_source_compiled=True,role_cases=256,flag_cases=2,high16_samples_per_role=256,unsupported_high16_cases=65536,source_unchanged=True,limit="FullWLAN/QDRV modules remain unqualified; setter stubs activate nofeature")
 except Exception as ex:result["error"]=str(ex)
 (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result));return int(not result["status"].startswith("PASS_"))


if __name__=="__main__":raise SystemExit(main())
