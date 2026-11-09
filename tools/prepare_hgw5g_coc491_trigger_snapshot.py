"""Bind each consumed PM request to its trigger under the same queue lock.

A producer arriving after request consumption remains pending for a later run
and cannot change the cause interpreted by the already running transaction.
New source version only; no router or original source modification.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['status']=='SOURCE_ONLY_COC491_COALESCED_COMPLETION_25_RECORDS_PENDING_GATES';a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');rel='source/wlan/ieee80211.c';path=a.output/rel;old=path.read_text();new=old
 needle='static int om_coc_channel_switch(struct ieee80211com *ic,int level,int pick_flags)';assert new.count(needle)==1;new=new.replace(needle,needle[:-1]+',u32 trigger)',1)
 needle='READ_ONCE(ic->om_coc_pm_trigger)==13U';assert new.count(needle)==1;new=new.replace(needle,'trigger==13U',1)
 start=new.index('static void om_coc_update_pm(');end=new.index('\nstatic void\nieee80211_update_pm(',start);fragment=new[start:end];fragment=fragment.replace('    bool pending;','    bool pending;\n    u32 trigger;',1);fragment=fragment.replace('    pending=ic->om_coc_pm_pending;','    pending=ic->om_coc_pm_pending;\n    trigger=ic->om_coc_pm_trigger;',1);fragment=fragment.replace('om_coc_channel_switch(ic,level,0x12)','om_coc_channel_switch(ic,level,0x12,trigger)',1).replace('om_coc_channel_switch(ic,level,0x14)','om_coc_channel_switch(ic,level,0x14,trigger)',1);new=new[:start]+fragment+new[end:];path.write_text(new,newline='\n');(a.output/'coc491-trigger-snapshot.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)),newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COC491_REQUEST_TRIGGER_SNAPSHOT_25_RECORDS_PENDING_GATES',parent_source=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),changed_sources={**proof['changed_sources'],rel:sha(path)},request_snapshot='pendingandtrigger capturedtogetherunderqueue_lock; currentrun consumesit, concurrentproducer remains pending forlaterworker',limits='Stillrequirescontrolledinterleavingfixture/fullARCABI+modules/globaldelta; noHW/RF/CSAcompletion proof');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
