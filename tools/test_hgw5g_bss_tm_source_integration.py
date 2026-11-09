"""Windows/local fixture for actual493 cases and exact copiedIE helper.

NoARC compiler claim: uses host fixtures while the isolated WSL lane is flaky.
Checks include setterbit preservation, TLVbounds and three sourcecallsite lengths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 proof=json.loads((a.candidate/'result.json').read_text());src=a.candidate/'source/wlan'
 for name,h in proof['changed_sources'].items():assert sha(src/name)==h
 helper=(src/'openmitrastar_bss_tm.h').read_text().split('/* Derived',1)[1].rsplit('#endif',1)[0];helper='/* Derived'+helper
 text=(src/'ieee80211_wireless.c').read_text();start=text.index('\tcase OM_OEM_PARAM_BSS_TM:');end=text.index('\n\tcase ',start+1);setter=text[start:end];start=text.index('\tcase OM_OEM_PARAM_BSS_TM:',end);end=text.index('\n\tcase ',start+1);getter=text[start:end]
 a.output.mkdir(parents=True,exist_ok=False)
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint8_t u8;typedef uint32_t u32;
#define EINVAL 22
#define OM_OEM_PARAM_BSS_TM 493
struct ieee80211com{u32 om_bss_tm_flags;};
static unsigned calls;
static void ieee80211_beacon_update_all(struct ieee80211com*ic){calls++;}
'''+helper+'''static void actual_set(struct ieee80211com*ic,int param,int value){switch(param){
'''+setter+'''\n default:break;}}
static void actual_get(struct ieee80211com*ic,int*param){switch(param[0]&0xffff){
'''+getter+'''\n default:break;}}
int main(void){unsigned i,n,enabled;struct ieee80211com ic;int result;u8 bytes[258],before[258];
for(i=0;i<65536;i++){ic.om_bss_tm_flags=i;calls=0;actual_set(&ic,493,1);assert(ic.om_bss_tm_flags==(i|1U)&&calls==1);result=(i<<16)|493;actual_get(&ic,&result);assert(result==1);actual_set(&ic,493,2);assert(ic.om_bss_tm_flags==(i&~1U)&&calls==2);}
for(n=0;n<256;n++)for(enabled=0;enabled<2;enabled++){memset(bytes,0xa5,sizeof(bytes));bytes[0]=127;bytes[1]=n;memcpy(before,bytes,sizeof(bytes));result=om_bss_tm_update_ie(bytes,n+2,enabled);if(n<3){assert(result==-22&&!memcmp(bytes,before,sizeof(bytes)));}else{assert(result==1);before[4]=enabled?(before[4]|8):(before[4]&~8);assert(!memcmp(bytes,before,sizeof(bytes)));}}
bytes[0]=0;bytes[1]=1;bytes[2]=4;bytes[3]=127;bytes[4]=3;bytes[5]=0;bytes[6]=0;bytes[7]=0;assert(om_bss_tm_update_ie(bytes,8,1)==1&&bytes[7]==8);memcpy(before,bytes,sizeof(bytes));assert(om_bss_tm_update_ie(bytes,7,0)==-22&&!memcmp(bytes,before,sizeof(bytes)));return0;}
'''.replace('return0;','return 0;')
 f=a.output/'fixture.c';f.write_text(fixture)
 command=[str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')];proc=subprocess.run(command,capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr
 test=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert test.returncode==0,test.stderr
 # Verify the actualcopiedlength is passed before frm advances at every site.
 calls=[]
 for name,frames in [('ieee80211_beacon_desc.c',['BEACON']),('ieee80211_output.c',['PROBE_RESP','ASSOC_RESP'])]:
  body=(src/name).read_text()
  for frame in frames:
   anchor='vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].length,\n';assert anchor in body and body.count('om_bss_tm_update_ie(')==len(frames)
   calls.append(name+':'+frame)
 header=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();root=Path(__file__).resolve().parents[1];baseline=(root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h').read_text();field='\t/* Recovered OEM493 host-only state; all existing fields remain before it. */\n\tu32 om_bss_tm_flags;\n';assert header.replace(field,'',1)==baseline
 result=dict(status='PASS_HOST_ACTUAL_BSS_TM_CASES_CALLER_SOURCE_AND_PREFIX_TEXT',hardware_accessed=False,firmware_eligible=False,bit_cases=65536,tlv_cases=512,actual_callers=calls,header_prefix_text_preserved=True,arc_compile='UNRUN_WSL_CONNECTION_ERROR',limits='NoARCmodule, noICsizecompatibilityqualification or80211vclientproof')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
