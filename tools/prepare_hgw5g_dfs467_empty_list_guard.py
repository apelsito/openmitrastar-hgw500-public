"""Refuse empty or out-of-range refreshed467 scan lists before provider pick.

The retained APpick fallback can use ss_chans[0] when the BSS is ANYC even if
the refreshed list has zero entries. Avoid a stale-pointer success; document
this deviation from inherited/OEM fallback without changing its normal path.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');path=a.output/'source/wlan/ieee80211_scan.c';text=path.read_text();needle='    ops->scan_start(ss,vap);\n    picked=ieee80211_scan_pickchannel(ic,0x130000);';assert text.count(needle)==1;text=text.replace(needle,'    ops->scan_start(ss,vap);\n    if(!ss->ss_last||ss->ss_last>IEEE80211_SCAN_MAX)return -EOPNOTSUPP;\n    picked=ieee80211_scan_pickchannel(ic,0x130000);',1);path.write_text(text,newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_DFS467_5GHZ_REFRESHED_LIST_BOUNDS_PENDING_MODULES',parent_source=str(a.parent),changed_sources={**proof['changed_sources'],'source/wlan/ieee80211_scan.c':sha(path)},safety_deviations=proof['safety_deviations']+['Empty/out-of-range refreshedscanlist refuses beforepick toavoid retained/OEM ANYCfallbacksuccessfromstale ss_chans0'],limits=proof['limits']+['Validinitializedscannerobjectlifetime assumed; nohotdetach/overlapscanproof']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
