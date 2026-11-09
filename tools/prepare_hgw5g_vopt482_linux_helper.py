"""Caller-owned Linux482 consumer; new candidate only and no hardware use."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
HEADER=r'''/* Caller-owned482 state. Initialize once with zeroed storage; never reset a
 * retained/quarantined transaction or free its IC/radio/provider owner. */
#ifndef OPENMITRASTAR_VOPT482_STATE_H
#define OPENMITRASTAR_VOPT482_STATE_H
struct ieee80211vap;
struct om_vopt482_state {
    void *payload,*pending_ioctl,*owner;
    unsigned dma,bytes,generation,stage,processing,quarantined,module_held;
};
int om_qdrv_vopt482(struct ieee80211vap *,struct om_vopt482_state *,int value);
int om_qdrv_vopt482_pending(const struct om_vopt482_state *);
#endif
'''
HELPER=r'''
/* OEM482 source recovery: CALCMD first, then normalSETPARAM482. Payload6,
 * allocation128 and lowbyte powerencoding faithful. Source-only adaptation
 * retains unknown publishedDMA/descriptor and forbids retry/ownerteardown. */
int om_qdrv_vopt482_pending(const struct om_vopt482_state *s)
{
    return s&&(READ_ONCE(s->processing)||READ_ONCE(s->quarantined));
}
EXPORT_SYMBOL(om_qdrv_vopt482_pending);
static int om482_send_owned(struct qdrv_wlan *qw,struct host_ioctl *ioctl,
    struct om_vopt482_state *s)
{
    bool retained=false,published=false;
    int rc=qdrv_send_ioctl_owned_observed(qw,ioctl,true,&retained,&published);
    if(retained){
        s->pending_ioctl=ioctl;s->quarantined=1;return -EINPROGRESS;
    }
    /* MACdead has legacyrawrc1 but publication=false; never call it ACK. */
    if(!published)return -EIO;
    return rc>=0&&(rc&QTN_HLINK_RC_DONE)&&!(rc&QTN_HLINK_RC_ERR)?0:-EIO;
}
int om_qdrv_vopt482(struct ieee80211vap *vap,struct om_vopt482_state *s,int value)
{
    struct qdrv_vap *qv;
    struct qdrv_wlan *qw;
    struct host_ioctl *ioctl;
    struct qtn_setparams_args *args;
    dma_addr_t dma;
    unsigned long flags;
    unsigned char *command;
    unsigned low=(unsigned)value&255U;
    int cal_rc=-EIO,normal_rc=-EIO;
    if(!vap||!s||in_interrupt()||irqs_disabled())return -EWOULDBLOCK;
    qv=container_of(vap,struct qdrv_vap,iv);qw=qv->parent;
    if(!qw||!qw->mac||qw->unit!=0||READ_ONCE(qw->mac->dead))return -ENODEV;
    local_irq_save(flags);
    if(s->processing||s->quarantined||s->generation==~0U||
       (s->owner&&s->owner!=qw)){
        local_irq_restore(flags);return -EBUSY;
    }
    if(!try_module_get(THIS_MODULE)){local_irq_restore(flags);return -ENODEV;}
    s->module_held=1;s->processing=1;s->generation++;s->owner=qw;
    local_irq_restore(flags);
    /* Required caller serialized RTNL/IC lifetime. Modulepin doesnotpinqw:
     * caller quiesce must refuse releasingIC/QDRV while pending query istrue. */
    s->stage=1;command=qdrv_hostlink_alloc_coherent(NULL,128,&dma,GFP_DMA);
    if(command){
        s->payload=command;s->dma=(unsigned)dma;s->bytes=128;
        command[0]=19;command[1]=0;command[2]=6;command[3]=0;command[4]=1;
        command[5]=low?(unsigned char)(low*4U):44;
        ioctl=qdrv_alloc_ioctl(qw);
        if(ioctl){
            ioctl->ioctl_command=IOCTL_DEV_CALCMD;ioctl->ioctl_arg1=0;
            ioctl->ioctl_arg2=6;ioctl->ioctl_argp=dma;
            cal_rc=om482_send_owned(qw,ioctl,s);
            if(cal_rc==-EINPROGRESS)goto retained;
        }
        qdrv_hostlink_free_coherent(NULL,128,command,dma);
        s->payload=NULL;s->dma=0;s->bytes=0;
    }
    /* Originalnormal command follows even calcmdalloc/error/refusal. */
    s->stage=2;ioctl=vnet_alloc_ioctl(qv);
    if(ioctl){
        args=qdrv_hostlink_alloc_coherent(NULL,sizeof(*args),&dma,GFP_DMA|GFP_ATOMIC);
        if(args){
            s->payload=args;s->dma=(unsigned)dma;s->bytes=sizeof(*args);
            args->ni_param=482;args->ni_value=value;args->ni_len=0;
            ioctl->ioctl_command=IOCTL_DEV_SETPARAMS;ioctl->ioctl_arg1=qv->devid;
            ioctl->ioctl_argp=dma;
            normal_rc=om482_send_owned(qw,ioctl,s);
            if(normal_rc==-EINPROGRESS)goto retained;
            qdrv_hostlink_free_coherent(NULL,sizeof(*args),args,dma);
            s->payload=NULL;s->dma=0;s->bytes=0;
        }else vnet_free_ioctl(ioctl);
    }
    local_irq_save(flags);
    s->processing=0;s->stage=0;s->owner=NULL;s->module_held=0;
    local_irq_restore(flags);
    module_put(THIS_MODULE);
    return !cal_rc&&!normal_rc?0:-EIO;
retained:
    /* Permanently retain callerstate/radio/module/DMA until explicitrecovery.
     * No resets/frees/retry, and no followingnormal482 afterunknownCALCMD. */
    return -EINPROGRESS;
}
EXPORT_SYMBOL(om_qdrv_vopt482);
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');header=a.output/'headers/net80211/openmitrastar_vopt482_state.h';header.write_text(HEADER,newline='\n');f=a.output/'source/qdrv/qdrv_hostlink.c';old=f.read_text();new=old.replace('#include "qdrv_dma_wire.h"','#include "qdrv_dma_wire.h"\n#include <net80211/openmitrastar_vopt482_state.h>',1)
 needle='static int qdrv_send_ioctl_owned(struct qdrv_wlan *qw,\n\tstruct host_ioctl *ioctl, bool retain_published_timeout, bool *retained)';assert needle in new;new=new.replace(needle,'static int qdrv_send_ioctl_owned_observed(struct qdrv_wlan *qw,\n\tstruct host_ioctl *ioctl, bool retain_published_timeout, bool *retained,\n\tbool *published_out)',1);new=new.replace('\tif (retained)\n\t\t*retained = false;','\tif (retained)\n\t\t*retained = false;\n\tif (published_out)\n\t\t*published_out = false;',1);new=new.replace('\tpublished = true;','\tpublished = true;\n\tif (published_out)\n\t\t*published_out = true;',1)
 anchor='static int qdrv_send_ioctl(struct qdrv_wlan *qw, struct host_ioctl *ioctl)';assert anchor in new;wrapper='static int qdrv_send_ioctl_owned(struct qdrv_wlan *qw,\n\tstruct host_ioctl *ioctl, bool retain_published_timeout, bool *retained)\n{\n\treturn qdrv_send_ioctl_owned_observed(qw,ioctl,retain_published_timeout,retained,NULL);\n}\n\n';new=new.replace(anchor,wrapper+anchor,1);new+='\n'+HELPER;f.write_text(new,newline='\n');patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/source/qdrv/qdrv_hostlink.c',tofile='b/source/qdrv/qdrv_hostlink.c'));patch+=''.join(difflib.unified_diff([],HEADER.splitlines(True),fromfile='/dev/null',tofile='b/headers/net80211/openmitrastar_vopt482_state.h'));(a.output/'vopt482-caller-owned.patch').write_text(patch,newline='\n');result=dict(status='SOURCE_ONLY_LINUX482_CALLER_OWNED_PROVIDER_PENDING_LIFETIME_GATES',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent.resolve()),files={'source/qdrv/qdrv_hostlink.c':sha(f),'headers/net80211/openmitrastar_vopt482_state.h':sha(header)},patch_sha256=sha(a.output/'vopt482-caller-owned.patch'),required_caller_gate='IC/radio/VAP/module ownedstate must remainalive while om_qdrv_vopt482_pending!=0; no reset/retry/release.',limits=['UP/unit0/process/serializedcaller scope only; allglobalhostlinkwriters/arbitration retainpriorlimits.','No callerquiesce/lifetimeintegration yet; modulepin alone doesnotpinIC/qw.','retained publishedDMA+descriptor is permanentuntilexplicitrecovery; NO_GOrelease/unload.', 'MTESTreturn0 isnotterminalACK; no livehardwareclaim.']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
