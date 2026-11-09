"""Versioned VOPT481 Linux adapter with caller-owned482 and existing producers.

Offline candidate only. Optional VSP get/set callbacks retain their actual opaque
provider contract; no background-scan alias or noop. Full module gates separate.
"""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
from prepare_hgw5g_vopt482_linux_helper import HEADER as STATE482,HELPER as HELPER482

ADAPTER=r'''
/* OEM481 Linux worker adapter. Timer onlyqueues; callbacks run underRTNL.
 * Exact coreR2 is separately preserved; this variant stops on retained482. */
static u32 om_vopt_global_backoff;
struct om_vopt_work_context { struct ieee80211com *ic;struct ieee80211vap *vap; };
static int om_vopt_kernel_parameter(void *context,unsigned command,int value)
{
    struct om_vopt_work_context *ctx=context;
    if(command==482)return om_qdrv_vopt482(ctx->vap,&ctx->ic->om_vopt482,value);
    ieee80211_param_to_qdrv(ctx->vap,command,value,NULL,0);return 0;
}
static int om_vopt_kernel_scs(void *context,u32 value)
{
    struct om_vopt_work_context *ctx=context;
    return ieee80211_param_scs_set(ctx->vap->iv_dev,ctx->vap,value);
}
static int om_vopt_kernel_ocac(void *context,u32 value)
{
    struct om_vopt_work_context *ctx=context;
    return ieee80211_param_ocac_set(ctx->vap->iv_dev,ctx->vap,value);
}
static int om_vopt_kernel_vsp_get(void *context,unsigned index,u32 *value)
{
    struct om_vopt_work_context *ctx=context;
    return ctx->ic->om_vopt_vsp_get(ctx->ic,index,value);
}
static int om_vopt_kernel_vsp_set(void *context,unsigned index,unsigned value)
{
    struct om_vopt_work_context *ctx=context;
    return ctx->ic->om_vopt_vsp_set(ctx->ic,index,value);
}
static void om_vopt_kernel_reassociate(void *context,unsigned first,unsigned second)
{
    struct om_vopt_work_context *ctx=context;
    ieee80211_wireless_reassoc(ctx->vap,first,second);
}
static void om_vopt_kernel_peer(void *arg,struct ieee80211_node *ni)
{
    struct om_vopt_peer peer;
    u32 *counts=arg;
    peer.self_bss=ni==ni->ni_vap->iv_bss;
    peer.self_address=!memcmp(ni->ni_macaddr,ni->ni_vap->iv_myaddr,IEEE80211_ADDR_LEN);
    peer.flags=READ_ONCE(ni->ni_qtn_flags);
    om_vopt_count_peer(&peer,&counts[0],&counts[1]);
}
static void om_vopt_kernel_work(struct work_struct *work)
{
    struct ieee80211com *ic=container_of(work,struct ieee80211com,om_vopt_work);
    struct ieee80211vap *vap;
    struct om_vopt_work_context context;
    struct om_vopt_environment environment;
    struct om_vopt_provider provider;
    unsigned long flags;
    u32 counts[2]={0,0};
    int rc=0;
    /* Never block on RTNL: a VAPdelete caller may hold it during syncjoin. */
    if(!rtnl_trylock())goto no_rtnl;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    if(ic->om_vopt_stopping||ic->om_vopt482.quarantined){
        spin_unlock_irqrestore(&ic->om_vopt_lock,flags);rtnl_unlock();goto no_rtnl;
    }
    ic->om_vopt_running=true;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
    vap=TAILQ_FIRST(&ic->ic_vaps);
    if(!vap||vap->iv_opmode!=IEEE80211_M_HOSTAP||!vap->iv_bss||
       !ic->ic_setparam||!ic->ic_iterate_nodes){rc=-EAGAIN;goto done;}
    context.ic=ic;context.vap=vap;
    memset(&provider,0,sizeof(provider));provider.context=&context;
    provider.parameter=om_vopt_kernel_parameter;provider.scs=om_vopt_kernel_scs;
    provider.ocac=om_vopt_kernel_ocac;provider.reassociate=om_vopt_kernel_reassociate;
    if(ic->om_vopt_vsp_get&&ic->om_vopt_vsp_set){
        provider.background_get=om_vopt_kernel_vsp_get;
        provider.background_set=om_vopt_kernel_vsp_set;
    }
    environment.flags=ic->ic_flags;environment.flags_ext=ic->ic_flags_ext;
    environment.ocac_channel=ic->ic_ocac.ocac_cfg.ocac_chan_ieee;
    environment.mode_value=ic->ic_curchan&&ic->ic_curchan!=IEEE80211_CHAN_ANYC?
        (int)(signed char)ic->ic_curchan->ic_maxpower_normal:0;
    ic->ic_iterate_nodes(&ic->ic_sta,om_vopt_kernel_peer,counts,0);
    rc=om_vopt_tick(&ic->om_vopt,&om_vopt_global_backoff,counts[0],counts[1],
        &environment,&provider);
    ic->ic_pppc_select_enable=ic->om_vopt.live_pppc;
    ic->ic_airfair=ic->om_vopt.live_airfair;
done:
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    ic->om_vopt_last_error=rc;ic->om_vopt_running=false;
    if(rc==-EINPROGRESS)ic->om_vopt_stopping=true;
    ic->om_vopt_pending=false;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);rtnl_unlock();return;
no_rtnl:
    spin_lock_irqsave(&ic->om_vopt_lock,flags);ic->om_vopt_pending=false;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
}
void om_ieee80211_vopt_initialize(struct ieee80211com *ic)
{
    spin_lock_init(&ic->om_vopt_lock);INIT_WORK(&ic->om_vopt_work,om_vopt_kernel_work);
    om_vopt_initialize(&ic->om_vopt,ic->ic_pppc_select_enable,ic->ic_airfair);
    memset(&ic->om_vopt482,0,sizeof(ic->om_vopt482));
    ic->om_vopt_stopping=false;ic->om_vopt_pending=false;ic->om_vopt_running=false;
    ic->om_vopt_destroying=false;
    ic->om_vopt_last_error=0;
}
EXPORT_SYMBOL(om_ieee80211_vopt_initialize);
void om_ieee80211_vopt_queue(struct ieee80211com *ic)
{
    unsigned long flags;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    if(!ic->om_vopt_stopping&&!ic->om_vopt_pending&&!ic->om_vopt482.quarantined){
        ic->om_vopt_pending=true;
        if(!schedule_work(&ic->om_vopt_work))ic->om_vopt_pending=false;
    }
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
}
EXPORT_SYMBOL(om_ieee80211_vopt_queue);
int om_ieee80211_vopt_quiesce(struct ieee80211com *ic)
{
    unsigned long flags;
    if(current_work()==&ic->om_vopt_work)return -EBUSY;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);ic->om_vopt_stopping=true;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
    del_timer_sync(&ic->ic_inact);cancel_work_sync(&ic->om_vopt_work);
    return om_qdrv_vopt482_pending(&ic->om_vopt482)?-EINPROGRESS:0;
}
EXPORT_SYMBOL(om_ieee80211_vopt_quiesce);
int om_ieee80211_vopt_detach_begin(struct ieee80211com *ic)
{
    unsigned long flags;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);ic->om_vopt_destroying=true;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
    return om_ieee80211_vopt_quiesce(ic);
}
EXPORT_SYMBOL(om_ieee80211_vopt_detach_begin);
void om_ieee80211_vopt_resume(struct ieee80211com *ic)
{
    unsigned long flags;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    if(!ic->om_vopt_destroying&&!om_qdrv_vopt482_pending(&ic->om_vopt482)&&
       !TAILQ_EMPTY(&ic->ic_vaps)){
        ic->om_vopt_stopping=false;
        mod_timer(&ic->ic_inact,jiffies+IEEE80211_INACT_WAIT*HZ);
    }
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
}
EXPORT_SYMBOL(om_ieee80211_vopt_resume);
static int om_vopt_kernel_policy(struct ieee80211vap *vap,int *value,int write)
{
    struct ieee80211com *ic=vap->iv_ic;unsigned long flags;int rc;
    if(!value)return -EINVAL;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    if(ic->om_vopt_stopping||ic->om_vopt_running){rc=-EBUSY;goto out;}
    rc=write?om_vopt_set(&ic->om_vopt,vap->iv_opmode,(u32)*value):
        om_vopt_get(&ic->om_vopt,vap->iv_opmode,value);
out:spin_unlock_irqrestore(&ic->om_vopt_lock,flags);return rc;
}
static int om_vopt_kernel_write_ready(struct ieee80211com *ic,unsigned command)
{
    unsigned long flags;int result=0;
    if(command!=481&&command!=78&&command!=195&&command!=147&&command!=158&&
       command!=288&&command!=232&&command!=375)return 0;
    /* VOPT worker mutates its core outside the spinlock while RTNL-owned.
     * Admit user writes only under the same process/lifetime serialization. */
    if(!rtnl_is_locked()||in_interrupt()||irqs_disabled())return -EBUSY;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    if(ic->om_vopt_running||ic->om_vopt_destroying||ic->om_vopt482.quarantined)result=-EBUSY;
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);return result;
}
static void om_vopt_kernel_backup(struct ieee80211com *ic,unsigned command,u32 value)
{
    unsigned long flags;
    spin_lock_irqsave(&ic->om_vopt_lock,flags);
    switch(command){
    case 78:ic->om_vopt.saved_txbf=(u8)value;break;
    case 195:ic->om_vopt.saved_probe=(u8)value;break;
    case 147:ic->om_vopt.saved_scs=value&65535U;break;
    case 158:ic->om_vopt.saved_pppc=(u8)value;ic->om_vopt.live_pppc=(u8)value;break;
    case 288:ic->om_vopt.saved_airfair=(u8)value;ic->om_vopt.live_airfair=(u8)value;break;
    case 232:case 375:ic->om_vopt.saved_ocac=ic->ic_ocac.ocac_cfg.ocac_enable;break;
    }
    spin_unlock_irqrestore(&ic->om_vopt_lock,flags);
}
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--helper482',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert sha(a.core/'openmitrastar_vopt481_recovered.c')=='6feb5e8af6980f109ec1295f8a254497903ddff09cbdd7c3d2231a0483ffaaaa';a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');changed={};patch=[]
 def write(rel,text):
  f=a.output/rel;old=f.read_text()if f.exists()else'';f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text,newline='\n');changed[rel]=sha(f);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 write('headers/net80211/openmitrastar_vopt482_state.h',STATE482)
 write('headers/net80211/openmitrastar_vopt481_recovered.h',(a.core/'openmitrastar_vopt481_recovered.h').read_text())
 write('source/wlan/openmitrastar_vopt481_recovered.h',(a.core/'openmitrastar_vopt481_recovered.h').read_text())
 core=(a.core/'openmitrastar_vopt481_recovered.c').read_text();write('source/wlan/openmitrastar_vopt481_recovered.c',core);adapt=core.replace('    om_vopt_u32 value;','    om_vopt_u32 value;int om482_rc;',1);adapt=adapt.replace('        provider->parameter(provider->context,482,om_vopt_byte_value((unsigned)environment->mode_value&255U));','        om482_rc=provider->parameter(provider->context,482,om_vopt_byte_value((unsigned)environment->mode_value&255U));\n        if(om482_rc==-115)return om482_rc;',1).replace('        provider->parameter(provider->context,482,0);','        om482_rc=provider->parameter(provider->context,482,0);\n        if(om482_rc==-115)return om482_rc;',1);write('source/wlan/openmitrastar_vopt481_kernel_core.inc',adapt);write('source/wlan/openmitrastar_vopt481_kernel.inc',ADAPTER)
 rel='headers/net80211/ieee80211_var.h';t=(a.output/rel).read_text();t=t.replace('#include <compat.h>','#include <compat.h>\n#include <net80211/openmitrastar_vopt481_recovered.h>\n#include <net80211/openmitrastar_vopt482_state.h>',1);anchor='\tu32 om_neighbor_report_flags;\n';assert anchor in t;t=t.replace(anchor,anchor+'\t/* OEM481 host-private worker and retained482 transaction. */\n\tstruct om_vopt_state om_vopt;\n\tstruct om_vopt482_state om_vopt482;\n\tstruct work_struct om_vopt_work;\n\tspinlock_t om_vopt_lock;\n\tbool om_vopt_stopping,om_vopt_pending,om_vopt_running,om_vopt_destroying;\n\tint om_vopt_last_error;\n\tint (*om_vopt_vsp_get)(struct ieee80211com *,unsigned,u32 *);\n\tint (*om_vopt_vsp_set)(struct ieee80211com *,unsigned,unsigned);\n',1);t+='\nvoid om_ieee80211_vopt_initialize(struct ieee80211com *);\nvoid om_ieee80211_vopt_queue(struct ieee80211com *);\nint om_ieee80211_vopt_quiesce(struct ieee80211com *);\nint om_ieee80211_vopt_detach_begin(struct ieee80211com *);\nvoid om_ieee80211_vopt_resume(struct ieee80211com *);\n';write(rel,t)
 rel='source/wlan/ieee80211_wireless.c';t=(a.output/rel).read_text();anchor='static int ieee80211_ioctl_setparam(';idx=t.find(anchor)
 if idx<0:
  anchor='ieee80211_ioctl_setparam(';idx=t.find(anchor);idx=t.rfind('\nstatic',0,idx)
 assert idx>0;t=t[:idx]+'\n#include "openmitrastar_vopt481_kernel_core.inc"\n#include "openmitrastar_vopt481_kernel.inc"\n'+t[idx:];anchor='\tswitch (param) {\n';ix=t.index(anchor,t.index('ieee80211_ioctl_setparam('));t=t[:ix]+'\tif(om_vopt_kernel_write_ready(ic,(unsigned)param))return -EBUSY;\n'+t[ix:];ix=t.index(anchor,t.index('ieee80211_ioctl_setparam('));t=t[:ix]+t[ix:].replace(anchor,anchor+'\tcase 481:return om_vopt_kernel_policy(vap,&value,1);\n',1);getpos=t.index('ieee80211_ioctl_getparam(');ix=t.index('switch (param[0] & 0xffff)',getpos);brace=t.index('{',ix);t=t[:brace+1]+'\n\tcase 481:return om_vopt_kernel_policy(vap,&param[0],0);'+t[brace+1:]
 # Existing normalWEXT grouped forwarding has no saved state: add exact78/195 stores before forwarding.
 needle='\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);\n\t\tbreak;\n\tcase IEEE80211_PARAM_OFF_CHAN_SUSPEND:';assert needle in t;t=t.replace(needle,'\t\tif(param==78||param==195)om_vopt_kernel_backup(ic,param,(u32)value);\n'+needle,1)
 needle='\t\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);\n\t\t} else {\n\t\t\tretv = EINVAL;\n\t\t}\n\t\tbreak;\n#endif /* QSCS_ENABLED */';assert needle in t;t=t.replace(needle,'\t\t\tom_vopt_kernel_backup(ic,147,(u32)value);\n'+needle,1)
 t=t.replace('\t\t\tic->ic_pppc_select_enable = value;','\t\t\tom_vopt_kernel_backup(ic,158,(u32)value);\n\t\t\tic->ic_pppc_select_enable = value;',1).replace('\t\t\tic->ic_airfair = value;','\t\t\tom_vopt_kernel_backup(ic,288,(u32)value);\n\t\t\tic->ic_airfair = value;',1)
 needle='\t\tif (ieee80211_param_ocac_set(dev, vap, value) == 0) {\n\t\t\tieee80211_param_to_qdrv';assert needle in t;t=t.replace(needle,'\t\tif (ieee80211_param_ocac_set(dev, vap, value) == 0) {\n\t\t\tom_vopt_kernel_backup(ic,param,(u32)value);\n\t\t\tieee80211_param_to_qdrv',1)
 table='static const struct iw_priv_args ieee80211_priv_args[] = {'
 if table not in t:table='static const struct iw_priv_args ieee80211_priv_args[] =\n{'
 if table not in t:table='static const struct iw_priv_args ieee80211_priv_args[] =\n { '
 assert table in t;t=t.replace(table,table+'\n\t{481,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"set_vopt"},\n\t{481,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"get_vopt"},',1);write(rel,t)
 rel='source/wlan/ieee80211.c';t=(a.output/rel).read_text();t=t.replace('\tieee80211_node_attach(ic);','\tom_ieee80211_vopt_initialize(ic);\n\tieee80211_node_attach(ic);',1);anchor='\tstruct ieee80211vap *vap;\n';idx=t.index('ieee80211_ifdetach(');start=t.index(anchor,idx);t=t[:start]+t[start:].replace(anchor,anchor+'\n\tif(om_ieee80211_vopt_detach_begin(ic))return;\n',1);write(rel,t)
 rel='source/wlan/ieee80211_node.c';t=(a.output/rel).read_text();needle='\tieee80211_timeout_ap(ic);\n\n\tmod_timer';assert needle in t;t=t.replace(needle,'\tieee80211_timeout_ap(ic);\n\tom_ieee80211_vopt_queue(ic);\n\n\tmod_timer',1);t=t.replace('\tdel_timer(&ic->ic_inact);','\tdel_timer_sync(&ic->ic_inact);',1);write(rel,t)
 rel='source/qdrv/qdrv_hostlink.c';t=(a.helper482/rel).read_text();t=t.replace('    if(!try_module_get(THIS_MODULE))','    if(qdrv_f355_claim("vopt482")){local_irq_restore(flags);return -EAGAIN;}\n    if(!try_module_get(THIS_MODULE))',1);write(rel,t)
 rel='source/qdrv/qdrv_vap.c';t=(a.output/rel).read_text();needle='\tstruct qdrv_vap *qv = netdev_priv(vdev);\n';idx=t.index('int qdrv_vap_exit(');start=t.index(needle,idx);t=t[:start]+t[start:].replace(needle,needle+'\n\tif(om_ieee80211_vopt_quiesce(qv->iv.iv_ic))return -EBUSY;\n',1);idx=t.index('int qdrv_vap_exit_muc_done(');start=t.index(needle,idx);t=t[:start]+t[start:].replace(needle,needle+'\tstruct ieee80211com *om_vopt_ic=qv->iv.iv_ic;\n\n\tif(om_qdrv_vopt482_pending(&om_vopt_ic->om_vopt482))return -EBUSY;\n',1);needle='\tieee80211_vap_detach_late(&qv->iv);\n\trtnl_unlock();';assert needle in t;t=t.replace(needle,'\tieee80211_vap_detach_late(&qv->iv);\n\tom_ieee80211_vopt_resume(om_vopt_ic);\n\trtnl_unlock();',1);idx=t.index('int qdrv_vap_init(');end=t.index('/* Any resource allocated',idx);prefix=t[:end];pos=prefix.rfind('\treturn 0;');assert pos>idx;t=t[:pos]+'\trtnl_lock();\n\tom_ieee80211_vopt_resume(ic);\n\trtnl_unlock();\n'+t[pos:];write(rel,t)
 (a.output/'vopt34-linux.patch').write_text(''.join(patch),newline='\n');files={str(f.relative_to(a.output)):sha(f)for tree in('source','headers')for f in(a.output/tree).rglob('*')if f.is_file()};result=dict(status='SOURCE_ONLY_VOPT34_LINUX_ADAPTER_PENDING_OFFLINE_GATES',hardware_accessed=False,firmware_eligible=False,qualified_records_added=0,parent=str(a.parent.resolve()),core_exact_r2_sha256=sha(a.core/'openmitrastar_vopt481_recovered.c'),changed_sources=changed,files=files,patch_sha256=sha(a.output/'vopt34-linux.patch'),limits=['No fullmodule/headerABI/callerfixtureyet.','OptionalVSPproviderunavailable selectedCONFIG_QVSP scope; NULLskips exactOEMoptionalcall, no bgscanalias.','Retained482 blocksVOPTfollowup414/reassoc andteardown; F355reboot-onlyretention.','Existingcoreerrors ignoredexcept-EINPROGRESS adaptation.','NoRF/client/traffic/regulatory/hardwarechanges.']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='files'},indent=2))
if __name__=='__main__':main()
