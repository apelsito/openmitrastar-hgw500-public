"""VersionedLinuxRBSbridge preservingfaithfulOEMcore/defaultabsentframeprovider."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
from collections import Counter
from catalog_hgw_firmware_comments import scan_comments
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
API=r'''
/* Required frame provider is immutable and pinned for the entire IC lifetime.
 * All callbacks run under IRQ spinlock, cannot sleep, and may authorize ONLY
 * the validated single frame/owner. They must never enable general radio TX.
 * No provider installation is implemented: initializer always leaves NULL.
 * open_window/close_window bind a frame allowance, not IOCTL_DEV_XMITCTL.
 * send_frame=1 consumes skb and its held node reference; unknown retains both.
 */
struct om_rbsdfs_kernel_provider {
    struct om_rbsdfs_frame_hooks frame;
    int (*open_window)(void *,unsigned role,u32 channel,u32 deadline);
    int (*close_window)(void *,u32 channel);
};
struct om_rbsdfs_kernel_state {
    struct om_rbsdfs_state core;
    struct om_rbsdfs_frame_state frame;
    struct timer_list timer;
    spinlock_t lock;
    const struct om_rbsdfs_kernel_provider *provider;
    struct ieee80211_node *retained_node;
    u32 channel,deadline;
    u8 initialized,stopping,window_active,quarantined;
};
void om_ieee80211_rbsdfs_init(struct ieee80211com *ic);
int om_ieee80211_rbsdfs_stop(struct ieee80211com *ic);
int om_ieee80211_rbsdfs_resume(struct ieee80211com *ic);
int om_ieee80211_rbsdfs_policy(struct ieee80211com *ic,unsigned op,u32 *value,int write);
int om_ieee80211_rbsdfs_radar(struct ieee80211com *ic,int during_cac,u32 channel);
int om_ieee80211_rbsdfs_mbs(struct ieee80211vap *vap,int during_cac,u32 channel);
/* 0=ordinary unchanged enqueue, 1=provider consumed frame+node,
 * 2=provider publication unknown retained by state, negative=drop both. */
int om_ieee80211_rbsdfs_send(struct ieee80211com *ic,struct ieee80211_node *ni,
    struct sk_buff *skb,int is_mgmt);
'''
BRIDGE=r'''/* Linux bridge: exact OEM core is included separately without modifications.
 * The adapter adds lifetime/serialization/refusal; it never provides raw TX.
 * Qualification stays blocked until a real immutable exact-frame provider and
 * its asynchronous ownership/completion/revoke contract are recovered.
 */
struct om_rbsdfs_kernel_call {
    struct ieee80211com *ic;
    unsigned role;
    u32 channel,deadline;
    int result;
};
static int om_rbsdfs_kernel_ready(struct om_rbsdfs_kernel_state *s)
{
    const struct om_rbsdfs_kernel_provider *p=s->provider;
    return p&&p->open_window&&p->close_window&&p->frame.validate_measurement&&
        p->frame.grant_frame&&p->frame.send_frame&&p->frame.revoke_frame;
}
static void om_rbsdfs_kernel_open(void *arg)
{
    struct om_rbsdfs_kernel_call *c=arg;
    struct om_rbsdfs_kernel_state *s=&c->ic->om_rbsdfs;
    c->result=s->provider->open_window(s->provider->frame.context,c->role,c->channel,c->deadline);
    if(c->result==1){s->window_active=1;s->channel=c->channel;s->deadline=c->deadline;}
    else if(c->result!=0)s->quarantined=1;
}
static void om_rbsdfs_kernel_arm(void *arg,u32 channel,u32 deadline)
{
    struct om_rbsdfs_kernel_call *c=arg;
    struct om_rbsdfs_kernel_state *s=&c->ic->om_rbsdfs;
    if(c->result==1){s->channel=channel;s->deadline=deadline;mod_timer(&s->timer,(unsigned long)deadline);}
}
static void *om_rbsdfs_kernel_find(void *arg,u32 channel)
{
    struct om_rbsdfs_kernel_call *c=arg;
    return ieee80211_find_channel_by_ieee(c->ic,channel);
}
static int om_rbsdfs_kernel_equal(void *arg,void *channel)
{
    struct om_rbsdfs_kernel_call *c=arg;
    struct ieee80211com *ic=c->ic;
    return ic->ic_curchan&&ic->ic_curchan!=IEEE80211_CHAN_ANYC&&
        ic->ic_chan_compare_equality&&ic->ic_chan_compare_equality(ic,ic->ic_curchan,channel);
}
static void om_rbsdfs_kernel_close(void *arg)
{
    struct om_rbsdfs_kernel_call *c=arg;
    struct om_rbsdfs_kernel_state *s=&c->ic->om_rbsdfs;
    c->result=s->provider->close_window(s->provider->frame.context,c->channel);
    if(c->result==1)s->window_active=0;else s->quarantined=1;
}
static unsigned om_rbsdfs_kernel_status(void *arg)
{
    struct om_rbsdfs_kernel_call *c=arg;
    struct ieee80211com *ic=c->ic;
    if(!ic->ic_curchan||ic->ic_curchan==IEEE80211_CHAN_ANYC||
       !ic->ic_get_chan_availability_status_by_chan_num)return 8;
    return ic->ic_get_chan_availability_status_by_chan_num(ic,ic->ic_curchan);
}
static struct om_rbsdfs_oem_hooks om_rbsdfs_kernel_hooks(struct om_rbsdfs_kernel_call *c)
{
    struct om_rbsdfs_oem_hooks h={c,om_rbsdfs_kernel_open,om_rbsdfs_kernel_close,
        om_rbsdfs_kernel_arm,om_rbsdfs_kernel_find,om_rbsdfs_kernel_equal,om_rbsdfs_kernel_status};
    return h;
}
static void om_rbsdfs_kernel_timer(struct timer_list *timer)
{
    struct om_rbsdfs_kernel_state *s=from_timer(s,timer,timer);
    struct ieee80211com *ic=container_of(s,struct ieee80211com,om_rbsdfs);
    struct om_rbsdfs_kernel_call c={ic,0,0,0,0};
    struct om_rbsdfs_oem_hooks h=om_rbsdfs_kernel_hooks(&c);
    unsigned long flags;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized||s->stopping||!s->window_active||!om_rbsdfs_kernel_ready(s))goto out;
    if(time_before(jiffies,(unsigned long)s->deadline)){mod_timer(&s->timer,(unsigned long)s->deadline);goto out;}
    c.channel=s->channel;
    /* Faithful expiry finds stored channel and disables only if current equal.
     * close_window never changes radio TX/CAC/radar; stale-channel bookkeeping
     * is then revoked by this narrower adapter even when OEM returned zero. */
    if(om_rbsdfs_oem_expire(s->channel,&h)==0)om_rbsdfs_kernel_close(&c);
    if(c.result!=1)s->quarantined=1;
out:spin_unlock_irqrestore(&s->lock,flags);
}
void om_ieee80211_rbsdfs_init(struct ieee80211com *ic)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;
    memset(s,0,sizeof(*s));spin_lock_init(&s->lock);om_rbsdfs_init(&s->core);
    timer_setup(&s->timer,om_rbsdfs_kernel_timer,0);
    s->provider=NULL;s->initialized=1;
}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_init);
int om_ieee80211_rbsdfs_stop(struct ieee80211com *ic)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;
    unsigned long flags;int result=0;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized){spin_unlock_irqrestore(&s->lock,flags);return 0;}
    s->stopping=1;
    spin_unlock_irqrestore(&s->lock,flags);
    /* Join timer after producer stop, never while holding callback lock. */
    del_timer_sync(&s->timer);
    spin_lock_irqsave(&s->lock,flags);
    if(s->quarantined||s->frame.quarantined||s->frame.active)result=-EBUSY;
    else if(s->window_active){
        if(!om_rbsdfs_kernel_ready(s)||s->provider->close_window(s->provider->frame.context,s->channel)!=1){s->quarantined=1;result=-EBUSY;}
        else s->window_active=0;
    }
    if(!result){s->core.allow_rbs_report=0;s->core.allow_mbs_csa=0;}
    spin_unlock_irqrestore(&s->lock,flags);return result;
}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_stop);
int om_ieee80211_rbsdfs_resume(struct ieee80211com *ic)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;unsigned long flags;int result=0;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized)result=-EAGAIN;
    else if(s->quarantined||s->frame.quarantined||s->frame.active||s->window_active)result=-EBUSY;
    else{s->stopping=0;s->core.allow_rbs_report=0;s->core.allow_mbs_csa=0;}
    spin_unlock_irqrestore(&s->lock,flags);return result;
}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_resume);
int om_ieee80211_rbsdfs_policy(struct ieee80211com *ic,unsigned op,u32 *v,int write)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;unsigned long flags;int result;
    if(!v)return -EINVAL;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized)result=-EAGAIN;
    else if(s->stopping||s->quarantined)result=-EBUSY;
    else if(op==466)result=write?om_rbsdfs_set466(&s->core,*v):om_rbsdfs_get466(&s->core,v);
    else if(op==468)result=write?om_rbsdfs_set468(&s->core,*v):om_rbsdfs_get468(&s->core,v);
    else result=-EINVAL;
    spin_unlock_irqrestore(&s->lock,flags);return result;
}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_policy);
static int om_rbsdfs_kernel_producer(struct ieee80211com *ic,unsigned role,int wds_is_rbs,
    int vap_hostap_run,int during_cac,u32 channel)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;
    struct om_rbsdfs_kernel_call c={ic,role,channel,0,0};
    struct om_rbsdfs_oem_hooks h=om_rbsdfs_kernel_hooks(&c);
    struct om_rbsdfs_state prior;unsigned long flags;int result;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized||s->stopping||s->quarantined||s->frame.active){result=-EBUSY;goto out;}
    if(!during_cac||!s->core.measurement_in_cac||(role==2&&ic->ic_extender_role!=2)||
        (role==1&&(wds_is_rbs||!vap_hostap_run))){result=0;goto out;}
    /* Required callback absent is an explicit missing-provider refusal BEFORE
     * the faithful core assigns allowance or requests temporary TX enable. */
    if(!om_rbsdfs_kernel_ready(s)){result=-EOPNOTSUPP;goto out;}
    if(s->window_active){result=-EBUSY;goto out;}
    prior=s->core;c.deadline=(u32)jiffies+s->core.end_tx_ms*HZ/1000U;
    result=role==2?om_rbsdfs_oem_radar_window(&s->core,ic->ic_extender_role,1,channel,(u32)jiffies,HZ,&h):
        om_rbsdfs_oem_mbs_window(&s->core,wds_is_rbs,vap_hostap_run,1,&h);
    if(result!=1||c.result!=1){s->core=prior;result=c.result==0?-EOPNOTSUPP:-EBUSY;}
    else if(role==1){
        /* OEM MBS branch has no expiry timer. Adapter additionally bounds its
         * frame-only allowance to end_tx_ms; never presents this as OEMequal. */
        mod_timer(&s->timer,(unsigned long)c.deadline);
    }
out:spin_unlock_irqrestore(&s->lock,flags);return result;
}
int om_ieee80211_rbsdfs_radar(struct ieee80211com *ic,int cac,u32 channel)
{return om_rbsdfs_kernel_producer(ic,2,0,0,cac,channel);}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_radar);
int om_ieee80211_rbsdfs_mbs(struct ieee80211vap *vap,int cac,u32 channel)
{return om_rbsdfs_kernel_producer(vap->iv_ic,1,ieee80211_scs_is_wds_rbs_node(vap->iv_ic),
    vap->iv_opmode==IEEE80211_M_HOSTAP&&vap->iv_state==IEEE80211_S_RUN,cac,channel);}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_mbs);
int om_ieee80211_rbsdfs_send(struct ieee80211com *ic,struct ieee80211_node *ni,
    struct sk_buff *skb,int is_mgmt)
{
    struct om_rbsdfs_kernel_state *s=&ic->om_rbsdfs;
    struct om_rbsdfs_kernel_call c={ic,ic->ic_extender_role,0,0,0};
    struct om_rbsdfs_oem_hooks h=om_rbsdfs_kernel_hooks(&c);
    struct om_rbsdfs_state prior;unsigned long flags;int result;unsigned allowance;
    spin_lock_irqsave(&s->lock,flags);
    if(!s->initialized||s->stopping||s->quarantined||s->frame.active){result=-EBUSY;goto out;}
    if(!s->core.measurement_in_cac||(c.role!=1&&c.role!=2)){result=0;goto out;}
    prior=s->core;allowance=c.role==2?s->core.allow_rbs_report:s->core.allow_mbs_csa;
    result=om_rbsdfs_oem_send_permitted(&s->core,c.role,&h);
    if(result!=1){result=-EACCES;goto out;}
    if(!allowance){
        /* Retain ordinary available-channel queue. During CAC require the
         * missing exact-frame provider even if status scalar says available. */
        result=ic->ic_curchan&&ic->ic_curchan!=IEEE80211_CHAN_ANYC&&
            !(ic->ic_curchan->ic_flags&IEEE80211_CHAN_DFS_CAC_IN_PROGRESS)?0:-EACCES;
        goto out;
    }
    if(!is_mgmt||!skb||!ni||!s->window_active||!om_rbsdfs_kernel_ready(s)||
       time_after_eq(jiffies,(unsigned long)s->deadline)){
        s->core=prior;result=-EOPNOTSUPP;goto out;
    }
    /* skb pointer identity is retained by core on uncertain publication. Node
     * lifetime is held alongside it; caller must not release either in case2. */
    result=om_rbsdfs_exact_frame_window(&s->frame,skb,c.role,s->channel,s->deadline,&s->provider->frame);
    if(result==OMRBS_PUBLISHED_UNKNOWN){s->retained_node=ni;s->quarantined=1;result=2;}
    else if(result==OMRBS_COMPLETE)result=1;
    else{result=-EOPNOTSUPP;}
out:spin_unlock_irqrestore(&s->lock,flags);return result;
}
EXPORT_SYMBOL(om_ieee80211_rbsdfs_send);
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 for d in('source','headers'):shutil.copytree(a.parent/d,a.output/d)
 changes={};patch=[]
 def change(rel,text):
  path=a.output/rel;old=path.read_bytes();raw=text.encode();comments=lambda b:Counter(b[r['offset']:r['end_offset']]for r in scan_comments(b));assert not comments(old)-comments(raw),'oldcomments '+rel;path.write_bytes(raw);changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.decode().splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 for name,d in [('openmitrastar_rbsdfs_recovered.h','headers/net80211'),('openmitrastar_rbsdfs_recovered.c','source/wlan')]:path=a.output/d/name;path.write_bytes((a.core/name).read_bytes());changes[path.relative_to(a.output).as_posix()]=sha(path)
 path=a.output/'source/wlan/openmitrastar_rbsdfs_kernel.inc';path.write_text(BRIDGE,newline='\n');changes[path.relative_to(a.output).as_posix()]=sha(path)
 rel='headers/net80211/ieee80211_var.h';s=(a.output/rel).read_text();needle='#include "net80211/ieee80211_linux.h"';assert s.count(needle)==1;s=s.replace(needle,needle+'\n#include "net80211/openmitrastar_rbsdfs_recovered.h"\n',1);pos=s.index('struct ieee80211com {');s=s[:pos]+API+'\n'+s[pos:];needle='\tu32 om_neighbor_report_flags;\n';assert s.count(needle)==1;s=s.replace(needle,needle+'\t/* OEM466/468 host state append; whole enclosing ABI rebuild required. */\n\tstruct om_rbsdfs_kernel_state om_rbsdfs;\n',1);change(rel,s)
 rel='source/wlan/ieee80211.c';s=(a.output/rel).read_text();needle='const char *ieee80211_phymode_name[]';assert s.count(needle)==1;s=s.replace(needle,'#include "openmitrastar_rbsdfs_recovered.c"\n#include "openmitrastar_rbsdfs_kernel.inc"\n\n'+needle,1);needle='\tspin_lock_init(&ic->om_coc_queue_lock);';assert s.count(needle)==1;s=s.replace(needle,'\tom_ieee80211_rbsdfs_init(ic);\n'+needle,1);needle='\tom_ieee80211_coc_quiesce(ic);';assert s.count(needle)==1;s=s.replace(needle,'\t/* Default providerNULL means stop cannot publish or retain frames. */\n\tWARN_ON_ONCE(om_ieee80211_rbsdfs_stop(ic));\n'+needle,1);change(rel,s)
 rel='source/wlan/ieee80211_wireless.c';s=(a.output/rel).read_text();s=s.replace('#define OM_OEM_PARAM_WEATHER_CAC_ENABLE 478','#define OM_OEM_PARAM_RBS_DFS_MSR_CAC 466\n#define OM_OEM_PARAM_RBS_DFS_END_TX 468\n#define OM_OEM_PARAM_WEATHER_CAC_ENABLE 478',1);start=s.index('ieee80211_ioctl_setparam(struct net_device *dev');b=s.index('{',s.index('switch (param)',start));s=s[:b+1]+'\n\tcase OM_OEM_PARAM_RBS_DFS_MSR_CAC:\n\tcase OM_OEM_PARAM_RBS_DFS_END_TX:\n\t\treturn om_ieee80211_rbsdfs_policy(ic,param,(u32 *)&value,1);\n'+s[b+1:];start=s.index('ieee80211_ioctl_getparam(struct net_device *dev');b=s.index('{',s.index('switch (param[0] & 0xffff)',start));s=s[:b+1]+'\n\tcase OM_OEM_PARAM_RBS_DFS_MSR_CAC:\n\tcase OM_OEM_PARAM_RBS_DFS_END_TX:\n\t\treturn om_ieee80211_rbsdfs_policy(ic,param[0]&0xffff,(u32 *)&param[0],0);\n'+s[b+1:];pos=s.index('\n};',s.index('static const struct iw_priv_args ieee80211_priv_args[]'));s=s[:pos]+'\n\t{466,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"rbs_dfs_msr_cac"},\n\t{466,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"g_rbsdfs_msrcac"},\n\t{468,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"rbs_dfs_end_tx"},\n\t{468,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"g_rbsdfs_endtx"},'+s[pos:];change(rel,s)
 rel='source/qdrv/qdrv_wlan.c';s=(a.output/rel).read_text();needle='\tstruct qdrv_vap *qv;\n\n\tif (ic->sta_dfs_info.sta_dfs_strict_mode) {';assert s.count(needle)==1;s=s.replace(needle,'\tstruct qdrv_vap *qv;\n\tint om_rbs_result;\n\n\tif (ic->sta_dfs_info.sta_dfs_strict_mode) {',1);needle='\tdev_queue_xmit(skb);\n\n\tieee80211_free_node(ni);';assert s.count(needle)==1;s=s.replace(needle,'\t/* Missing exact-frame provider never enables radio-wide TX. */\n\tom_rbs_result=om_ieee80211_rbsdfs_send(ic,ni,skb,is_mgmt);\n\tif(om_rbs_result>0)return 0; /* provider consumed or retained frame+node */\n\tif(om_rbs_result<0){dev_kfree_skb_any(skb);ieee80211_free_node(ni);return 0;}\n'+needle,1);needle='\tom_ieee80211_coc_quiesce(ic);';assert s.count(needle)==1;s=s.replace(needle,'\tif(om_ieee80211_rbsdfs_stop(ic))return -EBUSY;\n'+needle,1);change(rel,s)
 rel='source/qdrv/qdrv_radar.c';s=(a.output/rel).read_text();needle='\t\t\tieee80211_dfs_send_csa(vap, new_chan->ic_ieee);';assert s.count(needle)==1;s=s.replace(needle,'\t\t\t/* RBS466 MBS allowance request is frame-provider bound. */\n\t\t\t(void)om_ieee80211_rbsdfs_mbs(vap,is_cac_started(),new_chan->ic_ieee);\n'+needle,1);needle='\t/* take a dfs action */\n\tdfs_action(local_new_ieee, radar_detected_during_cac);';assert s.count(needle)==1;s=s.replace(needle,'\t/* Faithful recovered RBS producer captured pre-stop-CAC state. */\n\t(void)om_ieee80211_rbsdfs_radar(ic,radar_detected_during_cac,chan->ic_ieee);\n'+needle,1);change(rel,s)
 (a.output/'rbsdfs-kernel.patch').write_text(''.join(patch));pins={str(a.parent/'result.json'):sha(a.parent/'result.json'),str(a.core/'result.json'):sha(a.core/'result.json'),str(Path(__file__)):sha(__file__)};r=dict(status='SOURCE_ONLY_RBS466468_KERNEL_TYPED_REQUIRED_FRAME_PROVIDER_PENDING',hardware_accessed=False,firmware_eligible=False,qualified_ops_added=0,source_private_ops_added=4,parent=str(a.parent),core=str(a.core),faithful_core_exact=True,provider_bound=False,provider_installation_absent=True,changed_sources=changes,input_pins=pins,missing=['Exact-frame MuC authorization/revoke provider; currentIOCTL_DEV_XMITCTL26 is global bool','Realframe/node/provider lifetime and asynccompletionproof','Kernel wholeABI/fullsource modules/globaldelta qualification','MBSproducer capturedpreCAC context through actualcaller chain; pendingOEMwholefunctionequivalence','OriginalQHOPreport skip3OUIbytes retained; parser/provider validation unavailable','Arbitraryifdetach/forcedunload recovery of unknownprovider publication unqualified'],limits=['OEMcorepreservedexact with mandatoryenable/disable hooks; defaultNULL kernelbridge refusesbeforecoremutation','No radio-wideTXenable connected; noSTAalias/CACcompletion/radarclear','MBSadapterboundsoneframeallowance byendtx unlikeOEMnotimer; stalechanexpiry revokesbookkeeping unlikeOEMcurrent-onlydisable','Tablepresenceandtypedops are source-only; fourcompleteops remainmissing','NoHW/RF/client/traffic/persistence/rollback/release']);(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k!='changed_sources'}))
if __name__=='__main__':main()
