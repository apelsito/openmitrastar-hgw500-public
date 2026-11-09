"""Derive immutable r14 from r13: remove typed40 double channel advance only."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();oldproof=json.loads((a.parent/'result.json').read_text())
    for rel,h in oldproof['changed_sources'].items():assert sha(a.parent/rel)==h
    a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
    rel='source/wlan/ieee80211_scan.c';target=a.output/rel;old=target.read_text();needle='ss->ss_next++;goto again;';assert old.count(needle)==1;new=old.replace(needle,'goto again; /* The channel fetch already advanced ss_next once. */',1);target.write_text(new,newline='\n')
    patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel));(a.output/'chanset461-kernel.patch').write_text(patch,newline='\n');shutil.copyfile(a.parent/'chanset461-kernel.patch',a.output/'chanset461-parent-r13.patch')
    proof=dict(oldproof);proof['changed_sources']=dict(oldproof['changed_sources']);proof['changed_sources'][rel]=sha(target);proof['derived_parent']=str(a.parent.resolve());proof['derived_parent_result_sha256']=sha(a.parent/'result.json');proof['patch_scope']='EXACT_INCREMENTAL_R13_TO_R14';proof['patch_sha256']=sha(a.output/'chanset461-kernel.patch');proof['changed_variable']='Typed40 secondary-disallowed branch no longer advances ss_next twice.';proof['corrections']=list(oldproof['corrections'])+['Typed40 rejectedchannel advancesexactlyonce atfetch; followingallowedchannelisnot skipped.'];proof['status']='SOURCE_ONLY_CHANSET461_R14_SINGLE_ADVANCE_PENDING_FIXTURE_ARC';(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],'changed_source_sha256':sha(target),'patch_sha256':proof['patch_sha256'],'parent_result_sha256':proof['derived_parent_result_sha256']},indent=2))

if __name__=='__main__':main()
