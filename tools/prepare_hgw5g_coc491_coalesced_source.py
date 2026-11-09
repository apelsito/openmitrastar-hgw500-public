"""SOURCE25 PM worker multiplexing without losing producer events at CSA finish.

Only actual queue producers mark a PM request pending. Completion publication
and PM-request consumption share the existing work item, using the queue lock.
Concurrent producers retain a later request; completion-only work does not
invent a second PM transaction. New immutable candidate, no hardware access.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['status']=='SOURCE_ONLY_COC491_PM_DEFERRED_QUIESCE_25_RECORDS_PENDING_GATES';a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');patch=[];changes={}
 def change(rel,text):
  path=a.output/rel;old=path.read_text();path.write_text(text,newline='\n');changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 rel='headers/net80211/ieee80211_var.h';old=(a.output/rel).read_text();anchor='\tbool om_coc_completion_pending;\n';assert old.count(anchor)==1;change(rel,old.replace(anchor,anchor+'\tbool om_coc_pm_pending;\n',1))
 rel='source/wlan/ieee80211.c';old=(a.output/rel).read_text();needle='    if(om_coc_publish_completion(ic))return;';assert old.count(needle)==1
 new=old.replace('    int switched;\n    if(READ_ONCE(ic->om_coc_stopping))return;\n'+needle,'''    int switched;
    unsigned long flags;
    bool pending;
    if(READ_ONCE(ic->om_coc_stopping))return;
    /* Consume one actual producer request before publishing completion.
     * A producer arriving later owns a newly queued run and stays pending. */
    spin_lock_irqsave(&ic->om_coc_queue_lock,flags);
    pending=ic->om_coc_pm_pending;
    ic->om_coc_pm_pending=false;
    spin_unlock_irqrestore(&ic->om_coc_queue_lock,flags);
    om_coc_publish_completion(ic);
    if(!pending)return;''',1)
 needle='\t\tWRITE_ONCE(ic->om_coc_pm_trigger,trigger);';assert new.count(needle)==1;new=new.replace(needle,needle+'\n\t\tic->om_coc_pm_pending=true;',1)
 needle='\tic->om_coc_completion_pending=false;';assert new.count(needle)==1;new=new.replace(needle,needle+'\n\tic->om_coc_pm_pending=false;',1);change(rel,new)
 (a.output/'coc491-coalesced-recovery.patch').write_text(''.join(patch),newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COC491_COALESCED_COMPLETION_25_RECORDS_PENDING_GATES',changed_sources={**proof['changed_sources'],**changes},parent_source=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),completion_coalescing='OnlyactualPMqueueproducersmarkpending; workeratomicallytakesrequest, drainscompletion thenevaluatesrequestifpresent; laterproducersstaypendingandqueueafutureworker',limits='Requiresactualdeferredworker/queuedproducerinterleavingfixture, fullARCABIandmodules; noHW/RF/PM/CSAcompletion proof')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
