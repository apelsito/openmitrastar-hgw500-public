"""Integrate recovered461 source with the existing kernel scanner, offline only.

State is scanner-owned, not an OEM raw-offset field. All affected modules need
rebuild, source fixtures and a lifecycle review before any operation claim.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

API=r'''
/* Recovered OEM461 scanner state and callbacks; no raw OEM IC offsets. */
int om_chanset_kernel_allowed(struct ieee80211vap *vap);
int om_chanset_kernel_start(struct ieee80211vap *vap, int flags,
    unsigned duration, unsigned nssid, const struct ieee80211_scan_ssid *ssids);
int om_chanset_kernel_policy(struct ieee80211com *ic, int *value, int write);
unsigned om_chanset_kernel_scan_type(struct ieee80211com *ic);
struct ieee80211_channel *om_chanset_kernel_pick(struct ieee80211com *ic);
int om_chanset_kernel_finished(struct ieee80211com *ic);
void om_chanset_kernel_cancel(struct ieee80211com *ic);
'''

ADAPTER=r'''
/* Actual scanner-owned adapter for OEM channel-set selection. The existing
 * validated channel tables supply regulatory/DFS state; templates grant no TX.
 * Shared scan counters are sampled scalars, not a coherent cross-MuC snapshot.
 * No allocation or sleeping operation occurs in scan completion/timer context.
 */
int om_chanset_kernel_allowed(struct ieee80211vap *vap)
{
    struct ieee80211com *ic;
    unsigned mode;
    if(!vap||vap->iv_opmode!=IEEE80211_M_HOSTAP)return 0;
    ic=vap->iv_ic;mode=ic->ic_phymode;
    return mode==IEEE80211_MODE_11B||mode==IEEE80211_MODE_11G||
        mode==IEEE80211_MODE_11NG||mode==IEEE80211_MODE_11NG_HT40PM;
}
int om_chanset_kernel_policy(struct ieee80211com *ic,int *value,int write)
{
    struct scan_state *scan;
    unsigned long flags;
    if(!ic||!value||!ic->ic_scan)return -EAGAIN;
    scan=SCAN_PRIVATE(ic->ic_scan);
    spin_lock_irqsave(&scan->om_chanset_lock,flags);
    if(scan->om_chanset_stopping){spin_unlock_irqrestore(&scan->om_chanset_lock,flags);return -EBUSY;}
    if(write)scan->om_chanset_policy=(u8)*value;
    else *value=scan->om_chanset_policy;
    spin_unlock_irqrestore(&scan->om_chanset_lock,flags);
    return 0;
}
int om_chanset_kernel_start(struct ieee80211vap *vap,int flags,
    unsigned duration,unsigned nssid,const struct ieee80211_scan_ssid *ssids)
{
    struct ieee80211com *ic=vap->iv_ic;
    struct scan_state *scan;
    unsigned long irq;
    int result;
    if(!om_chanset_kernel_allowed(vap)||!ic->ic_scan)return -EOPNOTSUPP;
    scan=SCAN_PRIVATE(ic->ic_scan);
    spin_lock_irqsave(&scan->om_chanset_lock,irq);
    if(scan->om_chanset_stopping||(ic->ic_flags&IEEE80211_F_SCAN)){
        spin_unlock_irqrestore(&scan->om_chanset_lock,irq);return -EBUSY;
    }
    if(scan->om_chanset.busy)(void)om_chanset_end(&scan->om_chanset);
    result=om_chanset_prepare(&scan->om_chanset,OM_CHANSET_BAND24,
        ieee80211_get_bw(ic),ic->ic_country_code!=CTRY_DEFAULT,scan->om_chanset_policy);
    if(!result){
        scan->om_chanset_owner=vap;
        scan->om_chanset.initial_flags=(unsigned)flags;
    }
    spin_unlock_irqrestore(&scan->om_chanset_lock,irq);
    if(result)return result;
    /* Reuse the existing timer/SSID/scan policy. Fresh scan avoids stale cache.
     * The same state machine cancels it before releasing the scanner owner. */
    result=ieee80211_start_scan(vap,flags&~IEEE80211_SCAN_USECACHE,duration,nssid,ssids);
    if(!result)om_chanset_kernel_cancel(ic);
    return result;
}
unsigned om_chanset_kernel_scan_type(struct ieee80211com *ic)
{
    struct scan_state *scan;
    if(!ic||!ic->ic_scan)return 0;
    scan=SCAN_PRIVATE(ic->ic_scan);
    if(READ_ONCE(scan->om_chanset_stopping)||!READ_ONCE(scan->om_chanset.active))return 0;
    return READ_ONCE(scan->om_chanset.queue.cells[0]);
}
void om_chanset_kernel_cancel(struct ieee80211com *ic)
{
    struct scan_state *scan;
    unsigned long flags;
    if(!ic||!ic->ic_scan)return;
    scan=SCAN_PRIVATE(ic->ic_scan);
    spin_lock_irqsave(&scan->om_chanset_lock,flags);
    if(scan->om_chanset.busy)(void)om_chanset_end(&scan->om_chanset);
    scan->om_chanset_owner=NULL;
    spin_unlock_irqrestore(&scan->om_chanset_lock,flags);
}
int om_chanset_kernel_finished(struct ieee80211com *ic)
{
    struct scan_state *scan;
    if(!ic||!ic->ic_scan)return 1;
    scan=SCAN_PRIVATE(ic->ic_scan);
    return !READ_ONCE(scan->om_chanset.active)||!READ_ONCE(scan->om_chanset.queue.cells[0]);
}
static int om_cs_kernel_disabled(struct ieee80211com *ic,unsigned channel,unsigned width)
{
    struct ieee80211_channel *chan;
    unsigned sec;
    if(channel>=IEEE80211_CHAN_MAX||isset(ic->ic_chan_disabled,channel))return 1;
    if(width<40)return 0;
    chan=ieee80211_find_channel_by_ieee(ic,channel);
    if(!chan)return 1;
    sec=ieee80211_find_sec_chan(chan);
    return !sec||sec>=IEEE80211_CHAN_MAX||isset(ic->ic_chan_disabled,sec);
}
struct ieee80211_channel *om_chanset_kernel_pick(struct ieee80211com *ic)
{
    struct scan_state *scan;
    struct ieee80211_scan_state *ss;
    struct shared_params *shared;
    struct qtn_scs_info_set *scs;
    struct ap_state *as;
    struct ap_scan_entry *se;
    struct ieee80211vap *vap;
    struct ieee80211_channel *chan,*chosen=NULL;
    struct om_chanset_transaction *transaction;
    struct om_chanset_view view;
    const struct om_chanset_entry *picked;
    struct om_chanset_scan_sample sample;
    unsigned long flags;
    unsigned i,n=0,current;
    int neighborhood,result,index;
    if(!ic||!(ss=ic->ic_scan)||!(vap=ss->ss_vap)||!ss->ss_priv)return NULL;
    scan=SCAN_PRIVATE(ss);transaction=&scan->om_chanset;
    spin_lock_irqsave(&scan->om_chanset_lock,flags);
    if(scan->om_chanset_stopping||!transaction->active||scan->om_chanset_owner!=vap)goto out;
    shared=qtn_mproc_sync_shared_params_get();
    scs=shared?READ_ONCE(shared->scs_info_lhost):NULL;
    if(scs){
        for(i=0;i<IEEE80211_CHAN_MAX;i++){
            const struct qtn_scs_scan_info *raw=&scs->scan_info[i];
            sample.bandwidth=READ_ONCE(raw->bw_sel);sample.attempts=READ_ONCE(raw->cca_try);
            sample.cca_idle=READ_ONCE(raw->cca_idle);sample.cca_busy=READ_ONCE(raw->cca_busy);
            sample.cca_tx=READ_ONCE(raw->cca_tx);sample.cca_interference=READ_ONCE(raw->cca_intf);
            sample.cca_primary=READ_ONCE(raw->cca_pri);sample.cca_secondary=READ_ONCE(raw->cca_sec);
            sample.cca_secondary40=READ_ONCE(raw->cca_sec40);sample.beacons=READ_ONCE(raw->bcn_rcvd);
            sample.crc_errors=READ_ONCE(raw->crc_err);sample.long_preamble_errors=READ_ONCE(raw->lpre_err);
            sample.short_preamble_errors=READ_ONCE(raw->spre_err);
            chan=ieee80211_find_channel_by_ieee(ic,i);
            if(chan)(void)om_chanset_scan_sample(transaction,i,
                sample.bandwidth==20?0:(chan->ic_flags&IEEE80211_CHAN_HT40U)?1:
                (chan->ic_flags&IEEE80211_CHAN_HT40D)?3:0,&sample);
        }
    }
    (void)om_chanset_scan_advance(transaction);
    if(transaction->queue.cells[0])goto out;
    /* Lock the shared scan cache while copying only bounded channel metrics.
     * No SSID/MAC/client data is recorded in source evidence or this snapshot. */
    as=ss->ss_priv;spin_lock(&as->asl_lock);
    for(i=0;i<IEEE80211_CHAN_MAX;i++)TAILQ_FOREACH(se,&as->as_scan_list[i].asl_head,ase_list){
        uint8_t primary,secondary;
        unsigned width;
        if(n==255)break;
        if(!se->base.se_chan)continue;
        width=ieee80211_get_max_ap_bw(&se->base);
        if(width!=20&&width!=40)continue;
        ieee80211_find_ht_pri_sec_chan(vap,&se->base,&primary,&secondary);
        if(!primary)primary=se->base.se_chan->ic_ieee;
        scan->om_observations[n].channel=primary;scan->om_observations[n].bandwidth=width;
        scan->om_observations[n].secondary_offset=secondary>primary?1:secondary<primary?3:0;
        scan->om_observations[n].rssi_dbm=se->base.se_rssi;n++;
    }
    spin_unlock(&as->asl_lock);
    neighborhood=ieee80211_get_type_of_neighborhood(ic);
    for(i=0;i<transaction->count;i++){
        struct om_chanset_entry *entry=&transaction->entries[i];
        struct om_chanset_channel_state *state=&scan->om_channels[i];
        const uint8_t *active=entry->bandwidth==40?ic->ic_chan_active_40:ic->ic_chan_active_20;
        chan=ieee80211_find_channel_by_ieee(ic,entry->primary);
        state->allowed=chan&&isset(active,entry->primary)&&
            !isset(ic->ic_chan_pri_inactive,entry->primary)&&
            !om_cs_kernel_disabled(ic,entry->primary,entry->bandwidth)&&
            !(chan->ic_flags&(IEEE80211_CHAN_RADAR|IEEE80211_CHAN_DFS));
        state->inactive=0;state->dfs=chan?!!(chan->ic_flags&IEEE80211_CHAN_DFS):0;
        index=entry->bandwidth==40?PWR_IDX_40M:PWR_IDX_20M;
        state->power_range_cost=chan?(u32)((int)chan->ic_maxregpower-
            (int)chan->ic_maxpower_table[PWR_IDX_BF_OFF][PWR_IDX_1SS][index]):0;
        if(chan&&state->allowed&&!ic->ic_check_channel(ic,chan,0,0))state->allowed=0;
        if(entry->bandwidth==40)for(unsigned j=0;j<n;j++){
            struct ieee80211_channel candidate;
            uint8_t primary=scan->om_observations[j].channel;
            unsigned off=scan->om_observations[j].secondary_offset;
            if(!chan)break;candidate=*chan;ieee80211_update_sec_chan_offset(&candidate,entry->secondary_offset);
            /* Existing coexistence validator reads current channel. Preserve
             * its current-channel contract; do not forge ic_curchan for a call. */
            if(ic->ic_curchan==chan&&!ieee80211_20_40_operation_permitted(vap,primary,
                off==1?primary+4:off==3?primary-4:0))state->inactive=1;
        }
    }
    result=om_chanset_rank(transaction,scan->om_channels,transaction->count,
                           scan->om_observations,n,neighborhood);
    if(result)goto out;
    view.entries=transaction->entries;view.count=transaction->count;view.capacity=98;
    current=ieee80211_get_bw(ic);
    if(om_chanset_select(&view,OM_CHANSET_BAND24,ic->ic_max_system_bw,
        transaction->queue.current_bandwidth,scan->om_chanset_policy,
        transaction->params.max_bandwidth_benefit,&picked)==1){
        chosen=ieee80211_find_channel_by_ieee(ic,picked->primary);
        if(chosen&&ieee80211_dual_sec_chan_supported(vap,picked->primary))
            ieee80211_update_sec_chan_offset(chosen,picked->secondary_offset);
        if(chosen&&current!=picked->bandwidth)om_ieee80211_change_bw(vap,picked->bandwidth,0);
        (void)om_chanset_end(transaction);scan->om_chanset_owner=NULL;
    }else if(transaction->queue.current_bandwidth>20){
        (void)om_chanset_add_scan_type(&transaction->queue,OM_CHANSET_BAND24,
                                      transaction->queue.current_bandwidth/2);
    }
out:
    spin_unlock_irqrestore(&scan->om_chanset_lock,flags);
    return chosen;
}
EXPORT_SYMBOL(om_chanset_kernel_allowed);
EXPORT_SYMBOL(om_chanset_kernel_start);
EXPORT_SYMBOL(om_chanset_kernel_policy);
EXPORT_SYMBOL(om_chanset_kernel_scan_type);
EXPORT_SYMBOL(om_chanset_kernel_pick);
EXPORT_SYMBOL(om_chanset_kernel_finished);
EXPORT_SYMBOL(om_chanset_kernel_cancel);
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--helpers',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    assert json.loads((a.parent/'result.json').read_text())['total_original_entries_added']==25
    a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
    changed={};patch=[]
    def write(rel,text):
        f=a.output/rel;old=f.read_text()if f.exists()else'';f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text,encoding='utf-8',newline='\n');changed[rel]=sha(f);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
    for name in ('openmitrastar_chanset_recovered.h','openmitrastar_chanset_recovered.c','openmitrastar_chanset_tables.h'):
        text=(a.helpers/name).read_text()
        if name.endswith('.h')and 'struct om_chanset_transaction {'in text:text=text.replace('unsigned count, generation, busy, active;','unsigned count, generation, busy, active;\n    unsigned initial_flags;',1)
        write('source/wlan/'+name,text)
    # Keep helper compilation in the already compiled scan translation unit.
    adapter=ADAPTER.replace('scan->om_chanset.initial_flags','scan->om_chanset.initial_flags')
    write('source/wlan/openmitrastar_chanset_kernel.inc',adapter)
    for name in ('ieee80211_scan.h','ieee80211_var.h'):
        rel='headers/net80211/'+name;f=a.output/rel
        text=f.read_text()if f.exists()else(ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211'/name).read_text()
        if name=='ieee80211_scan.h':text=text.replace('#endif /* _NET80211_IEEE80211_SCAN_H_ */',API+'\n#endif /* _NET80211_IEEE80211_SCAN_H_ */')
        else:text=text.replace('void ieee80211_pm_queue_work(struct ieee80211com *ic);','void om_ieee80211_change_bw(struct ieee80211vap *,int,int);\nvoid ieee80211_pm_queue_work(struct ieee80211com *ic);',1)
        write(rel,text)
    rel='source/wlan/ieee80211_scan.c';text=(a.output/rel).read_text();text=text.replace('#include "net80211/ieee80211_scan.h"','#include "net80211/ieee80211_scan.h"\n#include "openmitrastar_chanset_recovered.h"',1)
    text=text.replace('\tstruct timer_list ss_probe_timer;\t/* start sending probe requests timer */','\tstruct timer_list ss_probe_timer;\t/* start sending probe requests timer */\n\tspinlock_t om_chanset_lock;\n\tbool om_chanset_stopping;\n\tu8 om_chanset_policy;\n\tstruct ieee80211vap *om_chanset_owner;\n\tstruct om_chanset_transaction om_chanset;\n\tstruct om_chanset_observation om_observations[255];\n\tstruct om_chanset_channel_state om_channels[98];',1)
    text=text.replace('\t\tic->ic_scan = &ss->base;','\t\tspin_lock_init(&ss->om_chanset_lock);\n\t\tic->ic_scan = &ss->base;',1)
    text=text.replace('\t\tdel_timer(&SCAN_PRIVATE(ss)->ss_scan_timer);\n\t\tdel_timer(&SCAN_PRIVATE(ss)->ss_probe_timer);','\t\tWRITE_ONCE(SCAN_PRIVATE(ss)->om_chanset_stopping,true);\n\t\tdel_timer_sync(&SCAN_PRIVATE(ss)->ss_scan_timer);\n\t\tdel_timer_sync(&SCAN_PRIVATE(ss)->ss_probe_timer);',1)
    text=text.replace('\t\tif (ss->ss_ops != NULL) {\n\t\t\tss->ss_ops->scan_detach(ss);','\t\tom_chanset_kernel_cancel(ic);\n\t\tif (ss->ss_ops != NULL) {\n\t\t\tss->ss_ops->scan_detach(ss);',1)
    # Bind scan cancellation to transaction cancellation before callbacks.
    marker='\t\tSCAN_PRIVATE(ss)->ss_iflags |= ISCAN_CANCEL;';text=text.replace(marker,marker+'\n\t\tom_chanset_kernel_cancel(ic);',1)
    # Stop rearming after scanner teardown begins.
    marker='\tstruct ieee80211vap *vap = ss->ss_vap;\n\tstruct ieee80211com *ic = vap->iv_ic;'
    start=text.index('scan_next(struct timer_list *timer)');body=text[start:];body=body.replace('\t/* Make passive channels special */','\tif (READ_ONCE(scan->om_chanset_stopping))return;\n\t/* Make passive channels special */',1);text=text[:start]+body
    # Preserve OEM BW20/40 scan direction without changing normal scan behavior.
    old='''\t\t\t\tif (!ic->ic_11n_40_only_mode)
\t\t\t\t      ic->ic_flags_ext |= IEEE80211_FEXT_SCAN_20;

\t\t\t\tchange_channel(ic, chan);'''
    new='''\t\t\t\tunsigned om_type=om_chanset_kernel_scan_type(ic);
\t\t\t\tif(om_type>=2&&om_type<=4){
\t\t\t\t    ic->ic_flags_ext &= ~IEEE80211_FEXT_SCAN_20;
\t\t\t\t    ic->ic_flags_ext |= IEEE80211_FEXT_SCAN_40;
\t\t\t\t    if(om_type==3||om_type==4)ieee80211_update_sec_chan_offset(chan,om_type==3?1:3);
\t\t\t\t}else if (!ic->ic_11n_40_only_mode)
\t\t\t\t      ic->ic_flags_ext |= IEEE80211_FEXT_SCAN_20;

\t\t\t\tchange_channel(ic, chan);
\t\t\t\tif(om_type)ic->ic_flags_ext &= ~IEEE80211_FEXT_SCAN_40;'''
    assert old in text;text=text.replace(old,new,1)
    text+='\n#include "openmitrastar_chanset_recovered.c"\n#include "openmitrastar_chanset_kernel.inc"\n';write(rel,text)
    rel='source/wlan/ieee80211_wireless.c';text=(a.output/rel).read_text();text=text.replace('#define OM_OEM_PARAM_COC_MOVE_NDFS 491','#define OM_OEM_PARAM_BW_AUTOSEL 461\n#define OM_OEM_PARAM_COC_MOVE_NDFS 491',1)
    start=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param)',start));text=text[:brace+1]+'\n\tcase OM_OEM_PARAM_BW_AUTOSEL:\n\t\treturn om_chanset_kernel_policy(ic,&value,1);\n'+text[brace+1:]
    start=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param[0] & 0xffff)',start));text=text[:brace+1]+'\n\tcase OM_OEM_PARAM_BW_AUTOSEL:\n\t\treturn om_chanset_kernel_policy(ic,&param[0],0);\n'+text[brace+1:]
    start=text.index('static const struct iw_priv_args ieee80211_priv_args[]');end=text.index('\n};',start);text=text[:end]+'\n\t{OM_OEM_PARAM_BW_AUTOSEL,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"set_bw_autosel"},\n\t{OM_OEM_PARAM_BW_AUTOSEL,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"get_bw_autosel"},'+text[end:]
    text+='\n'+(ROOT/'outputs/rea/coex449-changebw-helper-20261022T191000Z-r1/om_coex449_change_bw.c').read_text()+'\nEXPORT_SYMBOL(om_ieee80211_change_bw);\n';write(rel,text)
    rel='source/wlan/ieee80211_proto.c';text=(a.output/rel).read_text();old='''\t\t\t(void) ieee80211_check_scan(vap, scan_flags,
\t\t\t\t\tIEEE80211_SCAN_FOREVER,
\t\t\t\t\tvap->iv_des_nssid, vap->iv_des_ssid,
\t\t\t\t\tNULL);''';new='''\t\t\tif(om_chanset_kernel_allowed(vap))
\t\t\t    (void)om_chanset_kernel_start(vap,scan_flags,IEEE80211_SCAN_FOREVER,
\t\t\t        vap->iv_des_nssid,vap->iv_des_ssid);
\t\t\telse
'''+old;assert old in text;text=text.replace(old,new,1);write(rel,text)
    rel='source/wlan/ieee80211_scan_ap.c';text=(a.output/rel).read_text();text=text.replace('\tspin_lock(&as->asl_lock);\n\tif (bh_disabled) {\n\t\tlocal_bh_disable();\n\t}','\tif (bh_disabled) {\n\t\tlocal_bh_disable();\n\t}\n\tspin_lock(&as->asl_lock);',1);text=text.replace('\tif (bh_disabled) {\n\t\tlocal_bh_enable();\n\t}\n\tspin_unlock(&as->asl_lock);','\tspin_unlock(&as->asl_lock);\n\tif (bh_disabled) {\n\t\tlocal_bh_enable();\n\t}',1)
    # Scanner action tasklet must be joined before its cache is released.
    text=text.replace('\t\tap_flush_asl_table(ss);\n\t\tFREE(as, M_SCANCACHE);','\t\tIEEE80211_CANCEL_TQUEUE(&as->as_actiontq);\n\t\tap_flush_asl_table(ss);\n\t\tFREE(as, M_SCANCACHE);',1)
    anchor='\t/*\n\t * Convert CCA interference to CCI factor';assert anchor in text;text=text.replace(anchor,'\tif(om_chanset_kernel_allowed(ss->ss_vap))return om_chanset_kernel_pick(ic);\n\n'+anchor,1)
    text=text.replace('\t\t\treturn 0;\t\t\t/* restart scan */','\t\t\treturn om_chanset_kernel_allowed(vap)?!om_chanset_kernel_finished(ic):0; /* recovered scan queue */',1);write(rel,text)
    (a.output/'chanset461-kernel.patch').write_text(''.join(patch),encoding='utf-8',newline='\n')
    result=dict(status='SOURCE_ONLY_CHANSET461_KERNEL_SCAN_ADAPTER_27_RECORDS_PENDING_GATES',hardware_accessed=False,firmware_eligible=False,
                total_original_entries_added=27,remaining_original_table_gaps=17,base_records=25,changed_sources=changed,
                parent_sha256=sha(a.parent/'result.json'),helper_sha256=sha(a.helpers/'result.json'),
                limits=['Scanner-owned state, actualWEXT/proto/scan/apcallbacks wired; fullmodule/headerclosure/fixtures not run.',
                        'Mode gating matchesOEMHT24; 5GHz scanner keeps its original algorithm.',
                        'Sampledshared13-wordstats notcoherenttuple; caller/stopping/lifetime review mandatory.',
                        'Source prototype has known candidate inactive/secondary/regulatory integration obligations; no completefeaturecount.',
                        'NoRF,client,traffic,persistentboot/rollback/release orhardwareaccess.'])
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])


if __name__=='__main__':main()
