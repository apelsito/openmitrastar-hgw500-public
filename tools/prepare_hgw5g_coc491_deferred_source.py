"""SOURCE25 Linux5.10 adaptation: timer QoS deferral and producer stop gate.

Copy a prior immutable SOURCE25 only. Existing PM work owns sleeping QoS and
event publication; timer callback only completes CSA and schedules the worker.
Spinlock serializes queue publication with stop. Quiesce worker before cancel
CSA timer, refuse every later queue producer, preserve physical firmware.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

CALLBACK='''static void om_coc_finish_csa(unsigned long arg)
{
    struct ieee80211com *ic=(struct ieee80211com *)arg;
    unsigned long flags;
    int level;
    if(READ_ONCE(ic->om_coc_stopping))return;
    level=ieee80211_is_idle_state(ic)?BOARD_PM_LEVEL_IDLE:PM_QOS_DEFAULT_VALUE;
    if(ic->ic_csa_reason!=9U){
        WRITE_ONCE(ic->om_coc_last_switch,0U);
        return;
    }
    ieee80211_finish_csa(arg);
    /* Timer context cannot call the mutex/blocking-notifier QoS provider.
     * Preserve the sampled pre-completion PM level until process work runs. */
    spin_lock_irqsave(&ic->om_coc_queue_lock,flags);
    if(!ic->om_coc_stopping){
        ic->om_coc_completed_level=level;
        ic->om_coc_completion_pending=true;
        pm_queue_work(&ic->pm_work,0);
    }
    spin_unlock_irqrestore(&ic->om_coc_queue_lock,flags);
}

static bool om_coc_publish_completion(struct ieee80211com *ic)
{
    struct ieee80211vap *vap;
    struct ieee80211_channel *chan;
    unsigned long flags;
    int level;
    bool pending;
    spin_lock_irqsave(&ic->om_coc_queue_lock,flags);
    pending=ic->om_coc_completion_pending;
    level=ic->om_coc_completed_level;
    ic->om_coc_completion_pending=false;
    spin_unlock_irqrestore(&ic->om_coc_queue_lock,flags);
    if(!pending)return false;
    pm_qos_update_requirement(PM_QOS_POWER_SAVE,BOARD_PM_GOVERNOR_WLAN,level);
    chan=READ_ONCE(ic->ic_bsschan);
    if(chan&&chan!=IEEE80211_CHAN_ANYC){
        printk("CoC: Channel changed to %d as PM level changed to %d\\n",
               chan->ic_ieee,level);
        vap=TAILQ_FIRST(&ic->ic_vaps);
        ieee80211_eventf(vap?vap->iv_dev:NULL,
               "CoC: Channel changed to %d as PM level changed to %d\\n",
               chan->ic_ieee,level);
    }
    return true;
}

void om_ieee80211_coc_quiesce(struct ieee80211com *ic)
{
    unsigned long flags;
    spin_lock_irqsave(&ic->om_coc_queue_lock,flags);
    ic->om_coc_stopping=true;
    spin_unlock_irqrestore(&ic->om_coc_queue_lock,flags);
    /* Existing provider is cancel_delayed_work_sync. Producers are gated
     * before cancellation; teardown then joins the preexisting CSA timer. */
    pm_flush_work(&ic->pm_work);
}
EXPORT_SYMBOL(om_ieee80211_coc_quiesce);

'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_entries_added']==25;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');changes={};patch=[]
 def change(rel,text):
  path=a.output/rel;old=path.read_text();path.write_text(text,newline='\n');changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 rel='headers/net80211/ieee80211_var.h';old=(a.output/rel).read_text();anchor='\tu32 om_coc_pm_trigger;\n';assert old.count(anchor)==1;new=old.replace(anchor,anchor+'\tspinlock_t om_coc_queue_lock;\n\tbool om_coc_stopping;\n\tbool om_coc_completion_pending;\n\tint om_coc_completed_level;\n',1);proto='void om_ieee80211_pm_queue_node_join(struct ieee80211com *ic);';assert new.count(proto)==1;new=new.replace(proto,proto+'\nvoid om_ieee80211_coc_quiesce(struct ieee80211com *ic);',1);change(rel,new)
 rel='source/wlan/ieee80211.c';old=(a.output/rel).read_text();start=old.index('static void om_coc_finish_csa(');end=old.index('static int om_coc_channel_switch(',start);new=old[:start]+CALLBACK+old[end:];needle='    bool dfs,move=false;\n';assert new.count(needle)==1;new=new.replace(needle,needle+'    if(READ_ONCE(ic->om_coc_stopping))return 0;\n',1)
 needle='    int switched;\n';assert new.count(needle)==1;new=new.replace(needle,needle+'    if(READ_ONCE(ic->om_coc_stopping))return;\n    if(om_coc_publish_completion(ic))return;\n',1)
 start=new.index('static void\nom_coc_pm_queue(');end=new.index('void ieee80211_pm_queue_work(',start);fragment=new[start:end];fragment=fragment.replace('\tunsigned long delay;','\tunsigned long delay;\n\tunsigned long flags;',1);fragment=fragment.replace('\tWRITE_ONCE(ic->om_coc_pm_trigger,trigger);\n','\tif(READ_ONCE(ic->om_coc_stopping))return;\n',1);fragment=fragment.replace('\tpm_queue_work(&ic->pm_work, delay);','''\tspin_lock_irqsave(&ic->om_coc_queue_lock,flags);
\tif(!ic->om_coc_stopping){
\t\tWRITE_ONCE(ic->om_coc_pm_trigger,trigger);
\t\tpm_queue_work(&ic->pm_work,ic->om_coc_completion_pending?0:delay);
\t}
\tspin_unlock_irqrestore(&ic->om_coc_queue_lock,flags);''',1);new=new[:start]+fragment+new[end:];needle='\tINIT_DELAYED_WORK(&ic->pm_work, ieee80211_update_pm);';assert new.count(needle)==1;new=new.replace(needle,'''\tspin_lock_init(&ic->om_coc_queue_lock);
\tic->om_coc_stopping=false;
\tic->om_coc_completion_pending=false;
\tic->om_coc_completed_level=PM_QOS_DEFAULT_VALUE;
'''+needle,1);needle='\tpm_flush_work(&ic->pm_work);';assert new.count(needle)==1;new=new.replace(needle,'\tom_ieee80211_coc_quiesce(ic);',1);change(rel,new)
 rel='source/qdrv/qdrv_wlan.c';old=(a.output/rel).read_text();start=old.index('static int qdrv_wlan_80211_exit(');end=old.index('static void qdrv_show_wlan_stats(',start);fragment=old[start:end];needle='\tdel_timer_sync(&ic->ic_timer_csa);';assert fragment.count(needle)==1;fragment=fragment.replace(needle,'\tom_ieee80211_coc_quiesce(ic);\n'+needle,1);change(rel,old[:start]+fragment+old[end:])
 (a.output/'coc491-deferred-recovery.patch').write_text(''.join(patch),newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COC491_PM_DEFERRED_QUIESCE_25_RECORDS_PENDING_GATES',changed_sources={**proof['changed_sources'],**changes},parent_source=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),linux510_adaptation='CSA timer queues completion; existingprocessPMworker owns mutexQoS/log/event; sampledlevel preserved',lifetime='queuepublicationserializedwithstop; quiesce marksstopping beforecancel_delayed_work_sync; joinCSAtimer afterPMproducerclosure; reuseexistingwork/timer',new_host_state='3u32policy/last/trigger plusqueue_spinlock/stop/pending/completedlevel; fullABIneeded',limits='CompletionQoS/log are deferredasrequiredLinux5.10 safetychange; scalarsampling notcoherenttuple; noHW/RF/PM/CSAcompletion proof')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
