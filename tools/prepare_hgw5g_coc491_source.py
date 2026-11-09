"""Recover OEM CoC491 policy plus its actual PM/CSA consumer atop SOURCE23.

New immutable directory only. The PM trigger is a decision projection: the
OEM consumer distinguishes node-join 13 from all other event reasons only.
Keep that exact distinction with one public queue helper, not an unrelated
channel reason alias. Append host state, rebuild every header user. No device.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

HELPERS='''/* Recovered OEM491 PM/CSA consumer, analysis entries 0x83da0/0x83f28/
 * 0x84028. Host state is separate from channel-switch diagnostics. The sole
 * consumed PM-trigger distinction is node-join13 versus every other reason.
 * Invalid/ANYC BSS pointers are explicitly refused instead of OEM dereference.
 * Existing channel validation and CSA completion remain authoritative. */
static void om_coc_finish_csa(unsigned long arg)
{
    struct ieee80211com *ic=(struct ieee80211com *)arg;
    struct ieee80211vap *vap;
    struct ieee80211_channel *chan;
    int level=ieee80211_is_idle_state(ic)?BOARD_PM_LEVEL_IDLE:PM_QOS_DEFAULT_VALUE;
    if(ic->ic_csa_reason!=9U){
        WRITE_ONCE(ic->om_coc_last_switch,0U);
        return;
    }
    ieee80211_finish_csa(arg);
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
}

static int om_coc_channel_switch(struct ieee80211com *ic,int level,int pick_flags)
{
    struct ieee80211vap *vap;
    struct ieee80211_channel *chan=READ_ONCE(ic->ic_bsschan);
    unsigned long irqflags;
    bool eu_ready=ic->ic_dfs_is_eu_region();
    bool dfs,move=false;
    if(!chan||chan==IEEE80211_CHAN_ANYC)return 0;
    if(eu_ready){
        local_irq_save(irqflags);
        TAILQ_FOREACH(vap,&ic->ic_vaps,iv_next){
            if(vap->iv_opmode==IEEE80211_M_STA&&vap->iv_state==IEEE80211_S_RUN){
                eu_ready=false;
                break;
            }
        }
        local_irq_restore(irqflags);
    }
    dfs=!!(chan->ic_flags&IEEE80211_CHAN_DFS);
    if(level==PM_QOS_DEFAULT_VALUE){
        if(READ_ONCE(ic->om_coc_move_ndfs)&&!ic->ic_ocac.ocac_running&&!dfs&&
           eu_ready&&READ_ONCE(ic->om_coc_last_switch)==9U&&
           READ_ONCE(ic->om_coc_pm_trigger)==13U)move=true;
    }else if(dfs&&eu_ready){
        move=READ_ONCE(ic->om_coc_move_ndfs)!=0U;
    }
    if(!move)return 0;
    chan=ieee80211_find_channel_by_ieee(ic,ieee80211_scs_pick_channel(ic,pick_flags,0));
    if(chan&&chan!=IEEE80211_CHAN_ANYC&&ic->ic_check_channel(ic,chan,0,0))
        return ieee80211_enter_csa(ic,chan,om_coc_finish_csa,9U,10,1,3)==0;
    return 0;
}

static void om_coc_update_pm(struct ieee80211com *ic)
{
    struct ieee80211_channel *chan=READ_ONCE(ic->ic_bsschan);
    int level;
    int switched;
    /* The OEM worker accesses BSS flags before an invalid-pointer check.
     * Avoid changing QoS, pick state or callback ownership when not ready. */
    if(!chan||chan==IEEE80211_CHAN_ANYC)return;
    if(chan->ic_flags&IEEE80211_CHAN_DFS_CAC_IN_PROGRESS)return;
    level=ieee80211_is_idle_state(ic)?BOARD_PM_LEVEL_IDLE:PM_QOS_DEFAULT_VALUE;
    if(ic->ic_sta_assoc>0&&ic->ic_dfs_is_eu_region()&&
       level!=PM_QOS_DEFAULT_VALUE&&(chan->ic_flags&IEEE80211_CHAN_DFS)){
        switched=om_coc_channel_switch(ic,level,0x12);
        if(switched)WRITE_ONCE(ic->om_coc_last_switch,9U);
    }else{
        pm_qos_update_requirement(PM_QOS_POWER_SAVE,BOARD_PM_GOVERNOR_WLAN,level);
        switched=om_coc_channel_switch(ic,level,0x14);
        if(switched)WRITE_ONCE(ic->om_coc_last_switch,0U);
    }
}

'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();pp=json.loads((a.parent/'result.json').read_text());assert pp['total_original_entries_added']==23;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');changes={};patch=[]
 def change(rel,new):
  file=a.output/rel;old=file.read_text();file.write_text(new,newline='\n');changes[rel]=sha(file);patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 h='headers/net80211/ieee80211_var.h';old=(a.output/h).read_text();anchor='\tint om_legacy_rate_fixed;\n';assert old.count(anchor)==1;new=old.replace(anchor,anchor+'\t/* OEM491 owns independent host PM policy/transaction state. */\n\tu32 om_coc_move_ndfs;\n\tu32 om_coc_last_switch;\n\tu32 om_coc_pm_trigger;\n',1);proto='void ieee80211_pm_queue_work(struct ieee80211com *ic);';assert new.count(proto)==1;new=new.replace(proto,proto+'\nvoid om_ieee80211_pm_queue_node_join(struct ieee80211com *ic);',1);change(h,new)
 rel='source/wlan/ieee80211.c';old=(a.output/rel).read_text();start=old.index('static void\nieee80211_update_pm(');end=old.index('\nstatic void\nieee80211_pm_period_change(',start);new=old[:start]+HELPERS+'''static void
ieee80211_update_pm(struct work_struct *work)
{
    struct ieee80211com *ic=container_of(work,struct ieee80211com,pm_work.work);
    om_coc_update_pm(ic);
}
'''+old[end:];start=new.index('void\nieee80211_pm_queue_work(');end=new.index('EXPORT_SYMBOL(ieee80211_pm_queue_work);',start)+len('EXPORT_SYMBOL(ieee80211_pm_queue_work);');queue=new[start:end];queue=queue.replace('void\nieee80211_pm_queue_work(struct ieee80211com *ic)','static void\nom_coc_pm_queue(struct ieee80211com *ic,u32 trigger)',1);queue=queue.replace('\tint idle = ieee80211_is_idle_state(ic);','\tint idle;\n\tWRITE_ONCE(ic->om_coc_pm_trigger,trigger);\n\tidle = ieee80211_is_idle_state(ic);',1);queue=queue.replace('EXPORT_SYMBOL(ieee80211_pm_queue_work);','''void ieee80211_pm_queue_work(struct ieee80211com *ic)
{
    om_coc_pm_queue(ic,0U);
}
EXPORT_SYMBOL(ieee80211_pm_queue_work);

void om_ieee80211_pm_queue_node_join(struct ieee80211com *ic)
{
    om_coc_pm_queue(ic,13U);
}
EXPORT_SYMBOL(om_ieee80211_pm_queue_node_join);''');new=new[:start]+queue+new[end:];change(rel,new)
 rel='source/wlan/ieee80211_node.c';old=(a.output/rel).read_text();start=old.index('ieee80211_node_join(struct ieee80211_node *ni, int resp)');end=old.index('/*\n * Handle a station leaving',start);fragment=old[start:end];assert fragment.count('ieee80211_pm_queue_work(ic);')==1;fragment=fragment.replace('ieee80211_pm_queue_work(ic);','om_ieee80211_pm_queue_node_join(ic);',1);change(rel,old[:start]+fragment+old[end:])
 rel='source/wlan/ieee80211_wireless.c';old=(a.output/rel).read_text();new=old.replace('#define OM_OEM_PARAM_FIX_LEGACY_RATE 490','#define OM_OEM_PARAM_COC_MOVE_NDFS 491\n#define OM_OEM_PARAM_FIX_LEGACY_RATE 490',1);start=new.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param)',start));new=new[:brace+1]+'''\n\tcase OM_OEM_PARAM_COC_MOVE_NDFS:
\t\tWRITE_ONCE(ic->om_coc_move_ndfs,(u32)value);
\t\treturn 0;
'''+new[brace+1:];start=new.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');switch=new.index('switch (param[0] & 0xffff)',start);assert switch<new.index('\nstatic ',start);brace=new.index('{',switch);new=new[:brace+1]+'''\n\tcase OM_OEM_PARAM_COC_MOVE_NDFS:
\t\tparam[0]=(int)READ_ONCE(ic->om_coc_move_ndfs);
\t\treturn 0;
'''+new[brace+1:];start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);new=new[:end]+'''\n\t{ OM_OEM_PARAM_COC_MOVE_NDFS,
\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,0,"coc_mv_to_ndfs" },
\t{ OM_OEM_PARAM_COC_MOVE_NDFS,0,
\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,"g_coc_mv_to_ndfs" },'''+new[end:];change(rel,new)
 (a.output/'coc491-recovery.patch').write_text(''.join(patch),newline='\n');result=dict(status='SOURCE_ONLY_COC491_FULL_PM_CSA_CONSUMER_25_RECORDS_PENDING_GATES',hardware_accessed=False,firmware_eligible=False,total_original_entries_added=25,remaining_original_table_gaps=19,parent_manifest_sha256=sha(a.parent/'result.json'),changed_sources=changes,host_fields='three u32 at ICtail: policy exactu32, lastCoCCSA9/0, PMtrigger nodejoin13 versusallother0',consumer_entries=['OEM0x83da0 fullconsumer390B','OEM0x83f28 worker256B','OEM0x84028 CSAcallback184B'],safety_deviation='Invalid/ANYCBSS snapshot refuses PMtransaction rather thanOEMuncheckedpointer; localIRQalwaysrestored',trigger_projection='Only equality13 consumed; genericqueue mapsallothertriggerreasons0; nodejoinqueue publishes13. No aliaschannel-switchreason.',gates=['Actualconsumer/worker/callback/queuefixtures','ARCfulloldfieldABI/newQDRV+12layout','All58source/headerusers rebuildx2','SameheaderSOURCE23control globaldelta','PM/CSAownership/lifetime unchangedcontract andqueuedcallbackvalidation'],limits='Sharedstate READ/WRITE_ONCE doesnotmaketuplecoherent; PM/CSA voidcallback asynchronouscompletion unknown. Nohardware/RF/regulatory/traffic/persistence/release')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
