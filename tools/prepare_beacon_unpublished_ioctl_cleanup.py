"""Create a new R10 source candidate with two unpublished-slot cleanup fixes.

Do not edit R9, allocated wire arena, host ABI or firmware. Both paths own an
ioctl reserved by vnet_alloc_ioctl and return before vnet_send_ioctl_owned.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 source=a.parent/'source/qdrv/qdrv_wlan.c';raw=source.read_bytes();text=raw.decode('utf-8')
 assert sha(source)=='bd89f8b4fe774b43c747f91fe907f684a398ba85a191ca0cde38f4c4e4d8f739'
 changed=text
 for branch in ('if (preflight) {','if (encode) {'):
  start=changed.index(branch,changed.index('static int qdrv_wlan_80211_beacon_update_run('));end=changed.index('\n\t\t}',start)
  block=changed[start:end];needle='\t\t\tqdrv_hostlink_free_coherent(NULL, sizeof(*bc_args),'
  assert needle in block and 'vnet_free_ioctl(ioctl)' not in block
  changed=changed[:start]+block.replace(needle,'\t\t\tvnet_free_ioctl(ioctl);\n'+needle,1)+changed[end:]
 a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 output=a.output/'source/qdrv/qdrv_wlan.c';output.write_text(changed,encoding='utf-8',newline='\n')
 assert changed.replace('\t\t\tvnet_free_ioctl(ioctl);\n\t\t\tqdrv_hostlink_free_coherent(NULL, sizeof(*bc_args),','\t\t\tqdrv_hostlink_free_coherent(NULL, sizeof(*bc_args),')==text
 (a.output/'unpublished-ioctl-cleanup.patch').write_text(''.join(difflib.unified_diff(text.splitlines(True),changed.splitlines(True),fromfile='a/source/qdrv/qdrv_wlan.c',tofile='b/source/qdrv/qdrv_wlan.c')),encoding='utf-8')
 result={'status':'SOURCE_ONLY_BEACON_R10_UNPUBLISHED_IOCTL_CLEANUP_PENDING_BUILD','hardware_accessed':False,'firmware_eligible':False,'parent_result_sha256':sha(a.parent/'result.json'),'parent_source_sha256':hashlib.sha256(raw).hexdigest(),'candidate_qdrv_source_sha256':sha(output),'added_calls':2,'wire_or_header_changes':False,'fixed_paths':['optional preflight error','v89 encoding error'],'ownership_precondition':'vnet_alloc_ioctl reserved hostlink slot; coherent args and skb/param allocated; no vnet_send_ioctl_owned reached','limits':'Needs actual source cleanup fixture and minimum changed-unit/relink qualification; no hardware or published-owner release claim.'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');assert source.read_bytes()==raw;print(json.dumps(result,indent=2))
if __name__=='__main__':main()
