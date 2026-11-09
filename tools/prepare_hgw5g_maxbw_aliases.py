"""Recover max-bandwidth460 aliases to existing namedfield; no new policy.

OEM setter/getter store/read ic+0x4df1. Its existing exported max-bandwidth
function reads the same byte. Port exported function names it ic_max_system_bw.
This establishes the correspondence without importing numerical OEM offsets.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.parent)=='7a128781902eb6cc58f71e2b4a30ae005de7ebf168a10a9ae4139557b93a9be8'
 original=a.parent.read_text();macro='#define OM_OEM_PARAM_MAX_BANDWIDTH 460\n'
 candidate=original.replace('#define OM_OEM_PARAM_DEVICE_MODE 451',macro+'#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 getstart=candidate.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=candidate.index('{',candidate.index('switch (param[0] & 0xffff)',getstart))
 get='\n\tcase OM_OEM_PARAM_MAX_BANDWIDTH:\n\t\tparam[0] = ic->ic_max_system_bw;\n\t\tbreak;\n'
 candidate=candidate[:brace+1]+get+candidate[brace+1:]
 setstart=candidate.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=candidate.index('{',candidate.index('switch (param)',setstart))
 setter='\n\t/* OEM460 stores the lowbyte only; no channel/RF command is sent. */\n\tcase OM_OEM_PARAM_MAX_BANDWIDTH:\n\t\tic->ic_max_system_bw = (u_int8_t)value;\n\t\tbreak;\n'
 candidate=candidate[:brace+1]+setter+candidate[brace+1:]
 start=candidate.index('static const struct iw_priv_args ieee80211_priv_args[]');end=candidate.index('\n};',start)
 entries='\n\t{ OM_OEM_PARAM_MAX_BANDWIDTH,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "set_max_bw" },\n\t{ OM_OEM_PARAM_MAX_BANDWIDTH,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_max_bw" },'
 candidate=candidate[:end]+entries+candidate[end:]
 assert candidate.replace(macro,'',1).replace(get,'',1).replace(setter,'',1).replace(entries,'',1)==original
 a.output.mkdir(parents=True,exist_ok=False);source=a.output/'ieee80211_wireless.c';source.write_text(candidate,newline='\n')
 patch=''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'));(a.output/'maxbw-aliases.patch').write_text(patch,newline='\n')
 result=dict(status='SOURCE_ONLY_TWELVE_TABLE_ENTRIES_TEN_FUNCTIONAL_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,parent_sha256=sha(a.parent),candidate_sha256=sha(source),total_original_records_recovered=12,functional_original_ops_recovered=10,faithful_unsupported=2,remaining_original_table_gaps=32,field='ic->ic_max_system_bw',fieldproof='OEMcase460 setter/getter and exportedieee80211_get_max_system_bw all read/write byte4df1; same sourcefunction names field',limits='Storelowbyte policy only, no validation added; fullmodule delta and policy context remain required')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
