"""Hostactual492 flag/IE fixtures andSOURCEcapacity/descriptor boundaries.

Doesnotreplace ARC/fullmodule/firmware physical qualification. The generated
fakefixture extracts current sourcecases andhelper toavoidbehavioral copy.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 src=a.candidate/'source/wlan';text=(src/'ieee80211_wireless.c').read_text();start=text.index('\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:');end=text.index('\n\tcase ',start+1);setter=text[start:end];start=text.index('\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:',end);end=text.index('\n\tcase ',start+1);getter=text[start:end]
 helper=(src/'openmitrastar_bss_tm.h').read_text();helper=helper[helper.index('static inline u8 *om_neighbor_rrm_ie'):helper.rfind('#endif')]
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint8_t u8;typedef uint32_t u32;
#define OM_OEM_PARAM_NEIGHBOR_REPORT 492
struct ieee80211com{u32 om_neighbor_report_flags;};
static unsigned updates;
static void ieee80211_beacon_update_all(struct ieee80211com*ic){updates++;}
'''+helper+'''static void actual_set(struct ieee80211com*ic,int param,int value){switch(param){
'''+setter+'''\n default:break;}}
static void actual_get(struct ieee80211com*ic,int*param){switch(param[0]&0xffff){
'''+getter+'''\n default:break;}}
int main(void){struct ieee80211com ic;u8 bytes[9],before[9];unsigned i;int result;
for(i=0;i<65536;i++){ic.om_neighbor_report_flags=i;updates=0;actual_set(&ic,492,1);assert(ic.om_neighbor_report_flags==(i|1U)&&updates==1);result=(i<<16)|492;actual_get(&ic,&result);assert(result==1);memset(bytes,0xa5,sizeof(bytes));assert(om_neighbor_rrm_ie(bytes+1,ic.om_neighbor_report_flags)==bytes+8);assert(bytes[0]==0xa5&&bytes[8]==0xa5&&bytes[1]==70&&bytes[2]==5&&bytes[3]==2);actual_set(&ic,492,2);assert(ic.om_neighbor_report_flags==(i&~1U)&&updates==2);assert(om_neighbor_rrm_ie(bytes+1,ic.om_neighbor_report_flags)==bytes+8&&bytes[3]==0);for(result=4;result<8;result++)assert(bytes[result]==0);}
return0;}
'''.replace('return0;','return 0;')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr
 run=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert run.returncode==0
 beacon=(src/'ieee80211_beacon.c').read_text();assert '+ 7 /* RecoveredRRMIE70 descriptor reserve */'in beacon and 'bo->bo_om_rrm = frm;'in beacon and 'om_neighbor_rrm_ie(bo->bo_om_rrm' in beacon
 output=(src/'ieee80211_output.c').read_text();assert output.count('+ 7 /* recoveredRRMIE reserve */')==2 and output.count('frm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);')==2
 desc=(src/'ieee80211_beacon_desc.c').read_text();assert 'case 70:'in desc and 'frm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);'in desc
 result=dict(status='PASS_HOST_NEIGHBOR_FLAG_IE_CASES_SOURCE_CAPACITY_CHECKS',hardware_accessed=False,firmware_eligible=False,flag_cases=65536,capacity_checks='7Breservedbeacon/APprobe/APassocresponse',beacon_wire_struct_changed=False,limits=['Noactualbeaconallocation/transmitexecution.','FullARCstructoffsets/headerclosure/modules pending.','DisabledIEpresence explicitbehavior difference; no80211kmanagementhandlerclaim.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
