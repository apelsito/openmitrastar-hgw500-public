"""ActualCcase/default/ADDBA predicate fixtures for typedVAP484 SOURCEcandidate.

ExhaustivepeerHT/VHTflag combinations and realisticbooleans retainbasepolicy;
setterforwardsoriginalintvalue onlyonbooleantransition. Hostfixture, notARCABI.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();src=a.candidate/'source/wlan'
 text=(src/'ieee80211_wireless.c').read_text();start=text.index('\tcase OM_OEM_PARAM_TX_AMSDU_11N:');end=text.index('\n\tcase ',start+1);setter=text[start:end];start=text.index('\tcase OM_OEM_PARAM_TX_AMSDU_11N:',end);end=text.index('\n\tcase ',start+1);getter=text[start:end]
 output=(src/'ieee80211_output.c').read_text();start=output.index('\t\t\t\tif (vap->iv_tx_amsdu &&');end=output.index('\n',output.index('temp16 |= IEEE80211_A_BA_AMSDU_SUPPORTED;',start));predicate=output[start:end]
 setup=(src/'ieee80211.c').read_text();assert'vap->iv_tx_amsdu_11n = 1;'in setup
 root=Path(__file__).resolve().parents[1];header=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();baseline=(root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h').read_text();append='\t/* OEM484distinctVAP11n A-MSDUpolicy; noexistingmemberoffset changes. */\n\tu8 iv_tx_amsdu_11n;\n';assert header.replace(append,'',1)==baseline
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#define OM_OEM_PARAM_TX_AMSDU_11N 484
#define IEEE80211_NODE_HT 0x8
#define IEEE80211_NODE_VHT 0x4000
#define IEEE80211_A_BA_AMSDU_SUPPORTED 1
struct ieee80211vap{uint8_t iv_tx_amsdu,iv_tx_amsdu_11n;};
struct ieee80211_node{uint32_t ni_flags;};
static int sent_id,sent_value;static unsigned sends,reassocs;
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int p,int val,void*d,int n){sent_id=p;sent_value=val;sends++;assert(d==NULL&&n==0);}
static void ieee80211_wireless_reassoc(struct ieee80211vap*v,int a,int b){reassocs++;assert(a==0&&b==1);}
static void actual_set(struct ieee80211vap*vap,int param,int value){switch(param){
'''+setter+'''\n default:break;}}
static void actual_get(struct ieee80211vap*vap,int*param){switch(param[0]&0xffff){
'''+getter+'''\n default:break;}}
static uint16_t actual_addba(struct ieee80211vap*vap,struct ieee80211_node*ni,uint16_t baseline){uint16_t temp16=baseline;
'''+predicate+'''\nreturn temp16;}
int main(void){unsigned flags,base,n;int vals[]={0,1,2,255,-1,INT32_MIN,INT32_MAX};unsigned i;int result;struct ieee80211vap v;struct ieee80211_node ni;
v.iv_tx_amsdu=1;v.iv_tx_amsdu_11n=1;assert(v.iv_tx_amsdu==1&&v.iv_tx_amsdu_11n==1);
for(base=0;base<2;base++)for(n=0;n<2;n++)for(flags=0;flags<65536;flags++){
v.iv_tx_amsdu=base;v.iv_tx_amsdu_11n=n;ni.ni_flags=flags;uint16_t before=0xa5a0;uint16_t out=actual_addba(&v,&ni,before);int expected=base&&(((flags&0x4008)!=8)||n);assert(out==(uint16_t)(before|(expected?1:0)));assert(v.iv_tx_amsdu==base&&v.iv_tx_amsdu_11n==n);}
for(base=0;base<2;base++)for(n=0;n<2;n++)for(i=0;i<sizeof(vals)/sizeof(vals[0]);i++){
v.iv_tx_amsdu=base;v.iv_tx_amsdu_11n=n;sends=0;reassocs=0;actual_set(&v,484,vals[i]);assert(v.iv_tx_amsdu==base&&v.iv_tx_amsdu_11n==!!vals[i]);assert(sends==(n!=!!vals[i])&&reassocs==sends);if(sends)assert(sent_id==484&&sent_value==vals[i]);result=484;actual_get(&v,&result);assert(result==!!vals[i]);}
/* Explicitcounterexamples: disabling11n leavesVHT/legacybasepolicy untouched. */
v.iv_tx_amsdu=1;v.iv_tx_amsdu_11n=0;ni.ni_flags=8;assert(actual_addba(&v,&ni,0)==0);ni.ni_flags=0x4008;assert(actual_addba(&v,&ni,0)==1);v.iv_tx_amsdu=0;assert(actual_addba(&v,&ni,0)==0);return0;}
'''.replace('return0;','return 0;')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);proc=subprocess.run([str(a.compiler),'-std=c11','-O1',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr
 proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert proc.returncode==0,proc.stderr
 result=dict(status='PASS_ACTUAL_HOST_TYPED_AMSDU11N_CASES_AND_ADDBA_PREDICATE',hardware_accessed=False,firmware_eligible=False,peer_flag_cases=262144,setter_cases=28,explicit_counterexamples=3,base_amsdu_preserved=True,header_prefix_text_preserved=True,default_11n_flag=1,limits=['HostCfixtureonly; ARCfield/typealignment/enclosingstructoffset andancillaryusers notcompiled','Noaggregation/traffic/RF/physicalproof','Fullpairedsourcebuild/dependencyclosure mandatory'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
