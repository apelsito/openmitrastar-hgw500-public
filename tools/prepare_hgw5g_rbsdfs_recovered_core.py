"""Exact recovered OEM466/468 local state and bounded callback consumer core.

Source-only OEM behavior retains its temporary TX-enable request. Linux adapter
requires an exact-frame grant/revoke provider; unavailable means refusal. This
does not change the active port's DFS/regulatory or provide a runtime TX grant.
"""
import argparse,hashlib,json
from pathlib import Path

HEADER=r'''/* OEM466/468 source reconstruction; source-only, never hardware-qualified.
 * Local fields are semantic state, not copied OEM offsets or STAstrict aliases.
 * The OEM producer requests TX enable during CAC; its callback is mandatory.
 * Linux exact-frame grant boundary is separate and fail-closed when unavailable.
 */
#ifndef OPENMITRASTAR_RBSDFS_RECOVERED_H
#define OPENMITRASTAR_RBSDFS_RECOVERED_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 omrbs_u32;typedef u8 omrbs_u8;
#else
#include <stdint.h>
typedef uint32_t omrbs_u32;typedef uint8_t omrbs_u8;
#endif
struct om_rbsdfs_state { omrbs_u8 measurement_in_cac,allow_rbs_report,allow_mbs_csa;
    omrbs_u32 end_tx_ms; };
struct om_rbsdfs_oem_hooks {
    void *context;
    void (*enable_tx)(void *);
    void (*disable_tx)(void *);
    void (*arm_timer)(void *,omrbs_u32 channel,omrbs_u32 expires);
    void *(*find_channel)(void *,omrbs_u32 channel);
    int (*equal_current)(void *,void *channel);
    unsigned (*channel_status)(void *);
};
void om_rbsdfs_init(struct om_rbsdfs_state *state);
int om_rbsdfs_set466(struct om_rbsdfs_state *state,omrbs_u32 value);
int om_rbsdfs_get466(const struct om_rbsdfs_state *state,omrbs_u32 *value);
int om_rbsdfs_set468(struct om_rbsdfs_state *state,omrbs_u32 value);
int om_rbsdfs_get468(const struct om_rbsdfs_state *state,omrbs_u32 *value);
int om_rbsdfs_oem_radar_window(struct om_rbsdfs_state *,unsigned role,
    int during_cac,omrbs_u32 channel,omrbs_u32 now,omrbs_u32 hz,
    const struct om_rbsdfs_oem_hooks *);
int om_rbsdfs_oem_mbs_window(struct om_rbsdfs_state *,int wds_is_rbs,
    int vap_hostap_run,int during_cac,const struct om_rbsdfs_oem_hooks *);
int om_rbsdfs_oem_send_permitted(struct om_rbsdfs_state *,unsigned role,
    const struct om_rbsdfs_oem_hooks *);
int om_rbsdfs_oem_expire(omrbs_u32 channel,const struct om_rbsdfs_oem_hooks *);

/* Provider-bound exact-frame adapter; no default MMIO/hostlink TX implementation.
 * Validation must prove a single measurement frame / owner / allocation remains
 * live and authorized. Grant and revoke may retain uncertainty; never replay it.
 */
struct om_rbsdfs_frame_hooks {
    void *context;
    int (*validate_measurement)(void *,const void *frame,unsigned role,omrbs_u32 channel);
    int (*grant_frame)(void *,const void *frame);
    int (*send_frame)(void *,const void *frame);
    int (*revoke_frame)(void *,const void *frame);
};
struct om_rbsdfs_frame_state {
    omrbs_u32 generation,channel,deadline;
    const void *frame;
    unsigned active,quarantined;
};
enum om_rbsdfs_frame_result { OMRBS_REFUSED=0,OMRBS_COMPLETE=1,OMRBS_PUBLISHED_UNKNOWN=2 };
enum om_rbsdfs_frame_result om_rbsdfs_exact_frame_window(struct om_rbsdfs_frame_state *,
    const void *frame,unsigned role,omrbs_u32 channel,omrbs_u32 deadline,
    const struct om_rbsdfs_frame_hooks *);
#endif
'''

SOURCE=r'''#include "openmitrastar_rbsdfs_recovered.h"
void om_rbsdfs_init(struct om_rbsdfs_state *s)
{ if(s){s->measurement_in_cac=0;s->allow_rbs_report=0;s->allow_mbs_csa=0;s->end_tx_ms=500;} }
int om_rbsdfs_set466(struct om_rbsdfs_state *s,omrbs_u32 v)
{ if(!s)return -22;s->measurement_in_cac=v!=0;return 0; }
int om_rbsdfs_get466(const struct om_rbsdfs_state *s,omrbs_u32 *v)
{ if(!s||!v)return -22;*v=s->measurement_in_cac;return 0; }
int om_rbsdfs_set468(struct om_rbsdfs_state *s,omrbs_u32 v)
{ if(!s||(omrbs_u32)(v-1)>999U)return -22;s->end_tx_ms=v;return 0; }
int om_rbsdfs_get468(const struct om_rbsdfs_state *s,omrbs_u32 *v)
{ if(!s||!v)return -22;*v=s->end_tx_ms;return 0; }
int om_rbsdfs_oem_radar_window(struct om_rbsdfs_state *s,unsigned role,
    int during_cac,omrbs_u32 channel,omrbs_u32 now,omrbs_u32 hz,
    const struct om_rbsdfs_oem_hooks *h)
{
    omrbs_u32 ticks;
    if(!s||!h)return -22;
    if(role!=2||!during_cac||!s->measurement_in_cac)return 0;
    if(!h->enable_tx||!h->arm_timer||!hz||hz>0xffffffffU/1000U||
        (omrbs_u32)(s->end_tx_ms-1)>999U)return -22;
    /* Actual OEM assigns allowance then enables TX then arms its close timer.
     * floor(ms*HZ/1000), unsigned wrapping deadline, HZ200 observed OEM build. */
    s->allow_rbs_report=1;h->enable_tx(h->context);
    ticks=s->end_tx_ms*hz/1000U;
    h->arm_timer(h->context,channel,now+ticks);return 1;
}
int om_rbsdfs_oem_mbs_window(struct om_rbsdfs_state *s,int wds_is_rbs,
    int vap_hostap_run,int during_cac,const struct om_rbsdfs_oem_hooks *h)
{
    if(!s||!h)return -22;
    if(wds_is_rbs||!vap_hostap_run||!during_cac||!s->measurement_in_cac)return 0;
    if(!h->enable_tx)return -22;
    s->allow_mbs_csa=1;h->enable_tx(h->context);return 1;
}
int om_rbsdfs_oem_send_permitted(struct om_rbsdfs_state *s,unsigned role,
    const struct om_rbsdfs_oem_hooks *h)
{
    omrbs_u8 *allow;
    unsigned status;
    if(!s||!h)return -22;
    if(!s->measurement_in_cac||(role!=1&&role!=2))return 1;
    allow=role==2?&s->allow_rbs_report:&s->allow_mbs_csa;
    if(*allow){*allow=0;return 1;}
    if(!h->channel_status)return -22;
    /* OEM calls status twice along the short-circuit branch. */
    status=h->channel_status(h->context);if(status==4)return 0;
    status=h->channel_status(h->context);return status!=8;
}
int om_rbsdfs_oem_expire(omrbs_u32 channel,const struct om_rbsdfs_oem_hooks *h)
{
    void *found;
    if(!h||!h->find_channel||!h->equal_current||!h->disable_tx)return -22;
    found=h->find_channel(h->context,channel);
    if(!found)return -22; /* Adapter input guard, not an OEM null-proof claim. */
    if(h->equal_current(h->context,found)){h->disable_tx(h->context);return 1;}
    return 0;
}
enum om_rbsdfs_frame_result om_rbsdfs_exact_frame_window(struct om_rbsdfs_frame_state *s,
    const void *frame,unsigned role,omrbs_u32 channel,omrbs_u32 deadline,
    const struct om_rbsdfs_frame_hooks *h)
{
    int result;
    if(!s||!frame||!h||!h->validate_measurement||!h->grant_frame||
        !h->send_frame||!h->revoke_frame||s->active||s->quarantined||
        s->generation==0xffffffffU||(role!=1&&role!=2))return OMRBS_REFUSED;
    if(h->validate_measurement(h->context,frame,role,channel)!=1)return OMRBS_REFUSED;
    /* Caller serializes and pins state/frame/provider before this admission.
     * No module integration exists until provider lifetime/pins are proven. */
    s->generation++;s->frame=frame;s->channel=channel;s->deadline=deadline;s->active=1;
    result=h->grant_frame(h->context,frame);
    if(result==0){s->active=0;s->frame=0;return OMRBS_REFUSED;}
    if(result!=1){s->quarantined=1;return OMRBS_PUBLISHED_UNKNOWN;}
    result=h->send_frame(h->context,frame);
    if(result!=0&&result!=1){
        (void)h->revoke_frame(h->context,frame);s->quarantined=1;
        return OMRBS_PUBLISHED_UNKNOWN;
    }
    if(h->revoke_frame(h->context,frame)!=1){s->quarantined=1;return OMRBS_PUBLISHED_UNKNOWN;}
    s->active=0;s->frame=0;
    return result==1?OMRBS_COMPLETE:OMRBS_REFUSED;
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];assert not a.output.exists();a.output.mkdir(parents=True)
 files={'openmitrastar_rbsdfs_recovered.h':HEADER,'openmitrastar_rbsdfs_recovered.c':SOURCE}
 for n,v in files.items():(a.output/n).write_text(v,newline='\n')
 pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),root/'outputs/rea/rbsdfs466-measurement-rea-20261022T231000Z-r1/rea.json',root/'outputs/rea/rbsdfs466468-radar-rea-20261022T231100Z-r1/rea.json',root/'outputs/rea/rbsdfs468-expiry-rea-20261022T231600Z-r2/rea.json',root/'outputs/rea/oem-wlan-case-map-20261022T132100Z-r1/466-rbs_dfs_msr_cac-set.objdump.txt',root/'outputs/rea/oem-wlan-case-map-20261022T132100Z-r1/468-rbs_dfs_end_tx-set.objdump.txt']}
 result={'status':'SOURCE_ONLY_OEM_RBSDFS_CORE_AND_EXACT_FRAME_ADAPTER_PROVIDER_BOUNDARY','hardware_accessed':False,'firmware_eligible':False,'source_replacement':False,'qualified_ops_added':0,'files':{n:hashlib.sha256((a.output/n).read_bytes()).hexdigest()for n in files},'evidence_pins':pins,'ops_contracts':{'466':'U32!=0 stored u8, getteru8, noSTArole/EUvalidation','468':'U32 range1..1000,default500, getteru32'},'limits':['OEMenableTXcallback is represented faithfully; no live hostlink/TXprovider bound.','Exact-frameadapter refuses unavailableprovider; neither Linuxmodulepointerlifetime norphysicalframegrants proven.','OEMreportframe gate was recovered separately from missingfullQHOPpacketconsumers anddata-path metadata.','NoSTAstrictalias,CACcompletion,radarclear,regulatoryorphysicalchange.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='evidence_pins'},indent=2))
if __name__=='__main__':main()
