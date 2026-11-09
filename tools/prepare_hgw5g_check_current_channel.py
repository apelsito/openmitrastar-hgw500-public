"""Recover OEM464 setter to existing ic_chan_is_set, source only.

The exact exported OEM qdrv_wlan_cleanup_before_reload clears the same4e2c
offset as464 setter. The retained equivalent source names it ic_chan_is_set.
No scan/channel/RF command is introduced by this field setter.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.parent)=='022dc5388da1dddc161673c13faaca5de468054ee9ed071bf0286a1d3ae22f6b'
 original=a.parent.read_text();macro='#define OM_OEM_PARAM_CHECK_CURRENT_CHANNEL 464\n'
 candidate=original.replace('#define OM_OEM_PARAM_DEVICE_MODE 451',macro+'#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 start=candidate.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=candidate.index('{',candidate.index('switch (param)',start))
 code='\n\tcase OM_OEM_PARAM_CHECK_CURRENT_CHANNEL:\n\t\tic->ic_chan_is_set = value;\n\t\tbreak;\n'
 candidate=candidate[:brace+1]+code+candidate[brace+1:]
 start=candidate.index('static const struct iw_priv_args ieee80211_priv_args[]');end=candidate.index('\n};',start)
 entry='\n\t{ OM_OEM_PARAM_CHECK_CURRENT_CHANNEL,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "check_cur_chan" },'
 candidate=candidate[:end]+entry+candidate[end:]
 assert candidate.replace(macro,'',1).replace(code,'',1).replace(entry,'',1)==original
 a.output.mkdir(parents=True,exist_ok=False);source=a.output/'ieee80211_wireless.c';source.write_text(candidate,newline='\n')
 patch=''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'));(a.output/'check-current-channel.patch').write_text(patch,newline='\n')
 fixture='''#include <assert.h>
#include <stdint.h>
#define OM_OEM_PARAM_CHECK_CURRENT_CHANNEL 464
struct ieee80211com {int ic_chan_is_set;};
static void actual(struct ieee80211com*ic,int param,int value){switch(param){
'''+code+'''\n default:break;}}
int main(void){struct ieee80211com ic;unsigned i;for(i=0;i<65536;i++){actual(&ic,464,i);assert(ic.ic_chan_is_set==(int)i);actual(&ic,464,-(int)i);assert(ic.ic_chan_is_set==-(int)i);}actual(&ic,464,INT32_MIN);assert(ic.ic_chan_is_set==INT32_MIN);actual(&ic,464,INT32_MAX);assert(ic.ic_chan_is_set==INT32_MAX);return0;}
'''.replace('return0;','return 0;')
 (a.output/'fixture.c').write_text(fixture)
 result=dict(status='SOURCE_ONLY_15_TABLE_RECORDS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,parent_sha256=sha(a.parent),candidate_sha256=sha(source),total_original_entries_added=15,functional_ops_added=13,faithful_unsupported=2,remaining_original_table_gaps=29,field='ic->ic_chan_is_set',evidence='OEMexportcleanup_before_reload clear4e2c +464setterwrite4e2c; sourceequivalent clearsnamedfield',limits='Fullpairmodules andprefixedpolicyintegration gatepending, noRFactivations')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
