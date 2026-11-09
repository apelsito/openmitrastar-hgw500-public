"""Fresh BSS snapshot after deferred CSA publication for coalesced PM work.

The completion path can finish CSA and update BSS before a pending request is
evaluated. Snapshot the current BSS after publication, not before it. Preserve
previous candidate/fixtures, create one new source version only.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['status']=='SOURCE_ONLY_COC491_REQUEST_TRIGGER_SNAPSHOT_25_RECORDS_PENDING_GATES';a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');path=a.output/'source/wlan/ieee80211.c';old=path.read_text();start=old.index('static void om_coc_update_pm(');end=old.index('\nstatic void\nieee80211_update_pm(',start);fragment=old[start:end];fragment=fragment.replace('    struct ieee80211_channel *chan=READ_ONCE(ic->ic_bsschan);','    struct ieee80211_channel *chan;',1);fragment=fragment.replace('    if(!pending)return;','    if(!pending)return;\n    chan=READ_ONCE(ic->ic_bsschan);',1);new=old[:start]+fragment+old[end:];path.write_text(new,newline='\n');(a.output/'coc491-postcompletion-channel.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/source/wlan/ieee80211.c',tofile='b/source/wlan/ieee80211.c')),newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COC491_POSTCOMPLETION_BSS_SNAPSHOT_25_RECORDS_PENDING_GATES',parent_source=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),changed_sources={**proof['changed_sources'],'source/wlan/ieee80211.c':sha(path)},postcompletion_channel='BSSresampledaftercompletionpublication beforeactualpendingrequestdecision',limits='FullARCABI/pairedmodules/controlglobaldelta/review/physicalgates remain separate');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
