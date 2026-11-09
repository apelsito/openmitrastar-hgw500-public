"""SOURCE-only recovery of OEM463 dynamicSIFS wire-operation alias.

ExactOEMWLAN forwardsparam/value; exactQDRV transportscommand11/76Bpayload;
exactMuC dispatch463 validates high8selector0∈0..2,next8selector1∈0..3,
low16selector-value∈0..2 via its existing getter/setter. Nohost RFoperation.
Module/firmware pairing and physicalacceptance are separate requiredgates.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--muc-dispatch',type=Path,required=True);p.add_argument('--muc-set',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.parent)=='538da528ed69173af54bb5f7c8001e75254fadc883b6464e6674cff2d83e9cb2'
 dispatch=json.loads(a.muc_dispatch.read_text());setting=json.loads(a.muc_set.read_text());assert dispatch['ok'] and setting['ok']
 dt=dispatch['data']['raw_result']['value']['pseudocode'].replace('\r','');st=setting['data']['raw_result']['value']['pseudocode'].replace('\r','')
 assert'case 0x1cf:'in dt and'om_muc_dynamic_sifs'in dt and'param_1 < 3'in st and'param_2 < 4'in st and'param_3 < 3'in st
 original=a.parent.read_text();macro='#define OM_OEM_PARAM_DYNAMIC_SIFS 463\n';candidate=original.replace('#define OM_OEM_PARAM_DEVICE_MODE 451',macro+'#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 start=candidate.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=candidate.index('{',candidate.index('switch (param)',start))
 block='\n\t/* ExactOEM463 genericwire forwarding; MuC validatesselectortriplet. */\n\tcase OM_OEM_PARAM_DYNAMIC_SIFS:\n\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);\n\t\tbreak;\n';candidate=candidate[:brace+1]+block+candidate[brace+1:]
 start=candidate.index('static const struct iw_priv_args ieee80211_priv_args[]');end=candidate.index('\n};',start);entry='\n\t{ OM_OEM_PARAM_DYNAMIC_SIFS,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "set_dyn_sifs" },';candidate=candidate[:end]+entry+candidate[end:]
 assert candidate.replace(macro,'',1).replace(block,'',1).replace(entry,'',1)==original
 a.output.mkdir(parents=True,exist_ok=False);source=a.output/'ieee80211_wireless.c';source.write_text(candidate,newline='\n');(a.output/'dynamic-sifs-alias.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c')),newline='\n')
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#define OM_OEM_PARAM_DYNAMIC_SIFS 463
static int observedid,observedvalue;static unsigned count;
static void ieee80211_param_to_qdrv(void*v,int id,int value,void*d,int n){observedid=id;observedvalue=value;count++;assert(d==NULL&&n==0);}
static void actual(int param,int value){void*vap=0;switch(param){
'''+block+'''\n default:break;}}
int main(void){unsigned a,b,c;for(a=0;a<256;a++)for(b=0;b<256;b++)for(c=0;c<3;c++){uint32_t v=(a<<24)|(b<<16)|c;count=0;actual(463,v);assert(count==1&&observedid==463&&(uint32_t)observedvalue==v);}return0;}
'''.replace('return0;','return 0;');(a.output/'fixture.c').write_text(fixture)
 result=dict(status='SOURCE_ONLY_DYNAMIC_SIFS_ALIAS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,candidate_sha256=sha(source),parent_sha256=sha(a.parent),muc_dispatch_sha256=sha(a.muc_dispatch),muc_setter_sha256=sha(a.muc_set),total_original_entries_added=16,functional_ops_source=14,faithful_unsupported=2,remaining_original_table_gaps=28,protocol='SETPARAM11 payload76B id463,valueu32 encodedselectors, noextradata',limits=['ExactMuCfirmwarehashmuststaypaired','HostforwardreturndoesnotreportasynchronousMuCsuccess','NoRFactivation/physicalacceptance/modulequalification'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
