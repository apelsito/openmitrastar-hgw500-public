"""Exact482 payload and provider-owned CALCMD/normal-SETPARAM transaction.

OEM calldata/order preserved. Unsafe original free-after-unknown is replaced by
an explicit source-only retention boundary, never a guessed hostlink ACK.
"""
import argparse,hashlib,json
from pathlib import Path

HEADER=r'''/* Exact OEM482 CALCMD payload/ordering; bounded provider contract required.
 * No raw OEM offsets, no runtime binding, no calibrated-power/RF acceptance.
 */
#ifndef OPENMITRASTAR_VOPT482_TRANSPORT_H
#define OPENMITRASTAR_VOPT482_TRANSPORT_H
typedef unsigned char om482_u8;
typedef unsigned int om482_u32;
enum om482_publication { OM482_UNPUBLISHED=0, OM482_TERMINAL=1, OM482_UNKNOWN=2 };
struct om482_outcome { enum om482_publication publication; om482_u32 rc; };
struct om482_provider {
    void *context;
    void *(*allocate)(void *,unsigned bytes,om482_u32 *dma,unsigned flags);
    void (*release)(void *,unsigned bytes,void *payload,om482_u32 dma);
    struct om482_outcome (*calcmd_owned)(void *,unsigned length,om482_u32 dma);
    struct om482_outcome (*parameter_owned)(void *,unsigned command,om482_u32 value);
};
struct om482_transaction {
    om482_u32 generation,value,dma,calcmd_rc,parameter_rc;
    void *payload;
    unsigned active,quarantined,stage;
};
enum om482_result { OM482_REFUSED=0, OM482_ACKNOWLEDGED=1, OM482_PUBLISHED_UNKNOWN=2,
    OM482_COMPLETED_ERROR=3 };
void om482_payload(om482_u32 value,om482_u8 output[6]);
enum om482_result om482_execute(struct om482_transaction *,om482_u32 value,
                               const struct om482_provider *);
#endif
'''

SOURCE=r'''#include "openmitrastar_vopt482_transport.h"
typedef char om482_u32_four[(sizeof(om482_u32)==4)?1:-1];
void om482_payload(om482_u32 value,om482_u8 output[6])
{
    om482_u8 low=(om482_u8)value;
    output[0]=19;output[1]=0;output[2]=6;output[3]=0;output[4]=1;
    output[5]=low?(om482_u8)((unsigned)low*4U):44;
}
static int om482_terminal_ok(struct om482_outcome result)
{
    return result.publication==OM482_TERMINAL&&(result.rc&1U)&&!(result.rc&2U);
}
enum om482_result om482_execute(struct om482_transaction *s,om482_u32 value,
                               const struct om482_provider *p)
{
    struct om482_outcome cal={OM482_UNPUBLISHED,0},normal;
    int cal_ok=0;
    if(!s||!p||!p->allocate||!p->release||!p->calcmd_owned||!p->parameter_owned||
       s->active||s->quarantined||s->generation==0xffffffffU)return OM482_REFUSED;
    /* Owning adapter must serialize this record and pin provider/radio/frame
     * lifetime before admission. This core does not manufacture those pins. */
    s->generation++;s->value=value;s->dma=0;s->payload=0;
    s->calcmd_rc=s->parameter_rc=0;s->active=1;s->stage=1;
    s->payload=p->allocate(p->context,128,&s->dma,32);
    if(s->payload){
        om482_payload(value,(om482_u8 *)s->payload);
        s->stage=2;cal=p->calcmd_owned(p->context,6,s->dma);s->calcmd_rc=cal.rc;
        if(cal.publication!=OM482_UNPUBLISHED&&cal.publication!=OM482_TERMINAL){
            s->quarantined=1;return OM482_PUBLISHED_UNKNOWN;
        }
        /* Terminal requires provider-observed descriptorDONE/ERR; raw1 from a
         * dropped/dead-MAC return is not acknowledged. Unpublished is also safe
         * to release, independent of the caller's numerical rc. */
        cal_ok=om482_terminal_ok(cal);
        p->release(p->context,128,s->payload,s->dma);s->payload=0;s->dma=0;
    }
    /* Original SETPARAM482 performs CALCMD first then its normalSETPARAM path,
     * even after calcmd allocation/error. Keep original complete32-bitvalue.
     * UnknownCALCMD is different: do not publish another unarbitrated bankop. */
    s->stage=3;normal=p->parameter_owned(p->context,482,value);s->parameter_rc=normal.rc;
    if(normal.publication!=OM482_UNPUBLISHED&&normal.publication!=OM482_TERMINAL){
        s->quarantined=1;return OM482_PUBLISHED_UNKNOWN;
    }
    s->active=0;s->stage=0;
    if(cal_ok&&om482_terminal_ok(normal))return OM482_ACKNOWLEDGED;
    return OM482_COMPLETED_ERROR;
}
'''

LINUX=r'''/* Integration fragment only: insert beside actual qdrv_send_ioctl_owned.
 * Original qdrv_send_ioctl remains unchanged; new typedCALCMD consumer only.
 * qdrv_alloc_ioctl/macreadiness are actual source functions. Existing owned
 * sender distinguishes postpublicationtimeout with retained=true. This fragment
 * still needs actual owned-sender wait/arbitration/lifetime qualification.
 */
static struct om482_outcome om482_linux_calcmd_owned(void *context,
    unsigned length,om482_u32 dma)
{
    struct qdrv_wlan *qw=context;
    struct host_ioctl *ioctl;
    struct om482_outcome outcome={OM482_UNPUBLISHED,0};
    bool retained=false;
    int rc;
    if(!qw||!qw->mac||READ_ONCE(qw->mac->dead)||length!=6)return outcome;
    ioctl=qdrv_alloc_ioctl(qw);
    if(!ioctl)return outcome;
    ioctl->ioctl_command=IOCTL_DEV_CALCMD;
    ioctl->ioctl_arg1=0;ioctl->ioctl_arg2=length;ioctl->ioctl_argp=dma;
    rc=qdrv_send_ioctl_owned(qw,ioctl,true,&retained);
    outcome.rc=(om482_u32)rc;
    if(retained)outcome.publication=OM482_UNKNOWN;
    else if(rc>=0&&(rc&(QTN_HLINK_RC_DONE|QTN_HLINK_RC_ERR))&&
            !READ_ONCE(qw->mac->dead))outcome.publication=OM482_TERMINAL;
    /* Sender drops deadMAC with rawrc1 and no publication. Postreturndead may
     * be unrelated or concurrent: conservatively avoid ACKclaim but payload is
     * released only because retained=false denotes no pending senderownership.
     * Source-only UP caller scope; samebankotherproducer/lifecycle unqualified. */
    return outcome;
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];a.output.mkdir(parents=True,exist_ok=False);files={'openmitrastar_vopt482_transport.h':HEADER,'openmitrastar_vopt482_transport.c':SOURCE,'linux-calcmd-owned-fragment.c.inc':LINUX}
 for n,t in files.items():(a.output/n).write_text(t,newline='\n')
 pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),root/'outputs/rea/vopt482-calcmd-rea-20261022T203100Z-r1/rea.json',root/'outputs/rea/oem-qdrv-missingops-20261022T142000Z-setparam/rea.json',root/'outputs/rea/consolidated30-source-20261022T221100Z-r2/source/qdrv/qdrv_hostlink.c']};result=dict(status='SOURCE_ONLY_EXACT482_PAYLOAD_OWNED_TRANSPORT_BOUNDARY',hardware_accessed=False,firmware_eligible=False,module_integration=False,qualified_records_added=0,files={n:hashlib.sha256((a.output/n).read_bytes()).hexdigest()for n in files},pins=pins,limits=['No runtimeprovider ormoduleintegration; normalparameterowned callbackrequired.','OEMcalcmd6 bytes/alloc128/GFP32/orderfollowed; explicitunknownquarantine differsfromunsafeoriginalfree.','Rawmacdeadrc1 isnotACK; terminalclassificationrequirespublicationevidence.','Linuxfragment dependsactualowned sender boundedwait/foreignwriter/lifetimequalification; notestablishedhere.']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='pins'},indent=2))
if __name__=='__main__':main()
