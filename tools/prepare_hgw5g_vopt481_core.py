"""Recover exact OEM481 policy/effective consumers into a new isolated C core.

The callback contract preserves OEM command IDs and execution order. This is
source reconstruction, not a Linux/provider implementation or qualified ioctl.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = r'''/* Derived from pinned OEM ARC481 cases and explicit consumer entries.
 * Original module bytes are unchanged. No kernel ABI offsets are reused. */
#ifndef OM_VOPT481_RECOVERED_H
#define OM_VOPT481_RECOVERED_H
typedef unsigned char om_vopt_u8;
typedef unsigned int om_vopt_u32;
struct om_vopt_state {
    om_vopt_u8 policy, effective, saved_txbf, saved_probe;
    om_vopt_u8 saved_pppc, saved_airfair, live_pppc, live_airfair;
    om_vopt_u8 live_duplicate_mu;
    om_vopt_u32 saved_scs, saved_ocac, saved_bgscan;
};
struct om_vopt_environment {
    om_vopt_u32 flags, flags_ext;
    unsigned ocac_channel;
    int mode_value;
};
struct om_vopt_provider {
    void *context;
    int (*parameter)(void *, unsigned, int);
    int (*scs)(void *, om_vopt_u32);
    int (*ocac)(void *, om_vopt_u32);
    int (*background_get)(void *, unsigned, om_vopt_u32 *);
    int (*background_set)(void *, unsigned, unsigned);
    void (*reassociate)(void *, unsigned, unsigned);
};
struct om_vopt_peer { unsigned self_bss, self_address; om_vopt_u32 flags; };
void om_vopt_initialize(struct om_vopt_state *, unsigned, unsigned);
int om_vopt_set(struct om_vopt_state *, unsigned, om_vopt_u32);
int om_vopt_get(const struct om_vopt_state *, unsigned, int *);
int om_vopt_apply(struct om_vopt_state *, unsigned,
                  const struct om_vopt_environment *, const struct om_vopt_provider *);
void om_vopt_count_peer(const struct om_vopt_peer *, om_vopt_u32 *, om_vopt_u32 *);
int om_vopt_tick(struct om_vopt_state *, om_vopt_u32 *, om_vopt_u32, om_vopt_u32,
                 const struct om_vopt_environment *, const struct om_vopt_provider *);
#endif
'''
SOURCE = r'''/* OEM derived reconstruction. Callback errors are ignored where OEM ignores
 * them; adapter/provider availability remains an independent acceptance gate. */
#include "openmitrastar_vopt481_recovered.h"
typedef char om_vopt_u32_is_four[(sizeof(om_vopt_u32)==4)?1:-1];
void om_vopt_initialize(struct om_vopt_state *state,unsigned pppc,unsigned airfair)
{
    struct om_vopt_state zero={0};
    *state=zero;
    state->saved_probe=1;
    state->saved_pppc=(om_vopt_u8)pppc;
    state->saved_airfair=(om_vopt_u8)airfair;
    state->live_pppc=(om_vopt_u8)pppc;
    state->live_airfair=(om_vopt_u8)airfair;
}
int om_vopt_set(struct om_vopt_state *state,unsigned opmode,om_vopt_u32 value)
{
    /* Signed OEM bounds0..2; uint comparison rejects every negative encoding. */
    if(!state||opmode!=6||value>2)return -95;
    state->policy=(om_vopt_u8)value;return 0;
}
int om_vopt_get(const struct om_vopt_state *state,unsigned opmode,int *output)
{
    if(!state||!output)return -22;
    *output=opmode==6?((state->policy&15U)<<4)|state->effective:0;
    return 0;
}
static int om_vopt_byte_value(unsigned value)
{
    /* OEM ldb.x sign extends its saved byte before param_to_qdrv. */
    return value<128? (int)value:(int)value-256;
}
int om_vopt_apply(struct om_vopt_state *state,unsigned effective,
    const struct om_vopt_environment *environment,const struct om_vopt_provider *provider)
{
    om_vopt_u32 value;
    if(!state||!environment||!provider||!provider->parameter||
       !provider->scs||!provider->ocac||!provider->reassociate)return -95;
    /* Provider availability checked before mutation. Original consumer assumes
     * these callbacks exist. This refusal is a declared source adapter guard. */
    state->effective=(om_vopt_u8)effective;
    if(!state->effective){
        if(state->saved_txbf){
            provider->parameter(provider->context,78,om_vopt_byte_value(state->saved_txbf));
            provider->parameter(provider->context,68,17);
        }
        if(state->saved_pppc){
            provider->parameter(provider->context,158,om_vopt_byte_value(state->saved_pppc));
            state->live_pppc=state->saved_pppc;
        }
        if(state->saved_scs){
            value=state->saved_scs|0x10000U;
            if(!provider->scs(provider->context,value))
                provider->parameter(provider->context,147,(int)value);
        }
        if(state->saved_ocac){
            value=environment->ocac_channel&65535U;value|=0x10000U;
            provider->ocac(provider->context,value);
        }
        if(state->saved_bgscan&&provider->background_set)
            provider->background_set(provider->context,0,1);
        if(state->saved_probe)
            provider->parameter(provider->context,195,om_vopt_byte_value(state->saved_probe));
        if(state->saved_airfair){
            state->live_airfair=state->saved_airfair;
            provider->parameter(provider->context,288,om_vopt_byte_value(state->saved_airfair));
        }
        provider->parameter(provider->context,482,om_vopt_byte_value((unsigned)environment->mode_value&255U));
        state->live_duplicate_mu=0;
        provider->parameter(provider->context,414,0);
    }else{
        provider->parameter(provider->context,68,16);
        provider->parameter(provider->context,78,0);
        if(!(environment->flags&0x40000000U)||!(environment->flags_ext&0x800000U))
            provider->parameter(provider->context,158,0);
        state->live_pppc=0;
        provider->parameter(provider->context,195,0);
        state->live_airfair=0;
        provider->parameter(provider->context,288,0);
        value=0x10000U;
        if(!provider->scs(provider->context,value))
            provider->parameter(provider->context,147,(int)value);
        value=0x20000U;
        provider->ocac(provider->context,value);
        if(provider->background_get&&provider->background_set&&
           !provider->background_get(provider->context,0,&value)){
            state->saved_bgscan=value;
            provider->background_set(provider->context,0,0);
        }
        provider->parameter(provider->context,482,0);
        state->live_duplicate_mu=3;
        provider->parameter(provider->context,414,3);
    }
    provider->reassociate(provider->context,0,0);
    return 0;
}
void om_vopt_count_peer(const struct om_vopt_peer *peer,om_vopt_u32 *total,om_vopt_u32 *qualified)
{
    if(!peer||!total||!qualified||peer->self_bss||peer->self_address)return;
    ++*total;if(peer->flags&0x800U)++*qualified;
}
int om_vopt_tick(struct om_vopt_state *state,om_vopt_u32 *global_backoff,
    om_vopt_u32 total,om_vopt_u32 qualified,const struct om_vopt_environment *environment,
    const struct om_vopt_provider *provider)
{
    int result;
    if(!state||!global_backoff)return -22;
    if(state->policy==state->effective)return 0;
    if(state->policy==0||state->policy==1){
        result=om_vopt_apply(state,state->policy,environment,provider);
        if(!result)*global_backoff=0;return result;
    }
    if(state->policy==2){
        if(*global_backoff){--*global_backoff;return 0;}
        if(total==qualified&&state->effective!=1)
            return om_vopt_apply(state,1,environment,provider);
        if(total!=qualified&&state->effective!=0){
            result=om_vopt_apply(state,0,environment,provider);
            if(!result)*global_backoff=10;return result;
        }
    }
    return 0;
}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    references = [ROOT/'outputs/rea/windows-oem-vopt481-apply-20261022T200100Z-r1/rea.json',
                  ROOT/'outputs/rea/windows-oem-vopt481-policy-20261022T200100Z-r1/rea.json',
                  ROOT/'outputs/rea/windows-oem-vopt481-peer-classifier-20261022T200900Z-r1/rea.json',
                  ROOT/'outputs/rea/oem-wlan-case-map-20261022T132100Z-r1/481-set_vopt-set.objdump.txt',
                  ROOT/'outputs/rea/oem-wlan-case-map-20261022T132100Z-r1/481-get_vopt-get.objdump.txt']
    for reference in references[:3]:
        proof=json.loads(reference.read_text(encoding='utf-8'))
        assert proof['ok'] and proof['data']['subject']['digest']['sha256']=='4a7db7427670a80543918e269a51d82cf9cde75a04b02214121022e31eeb6d3a'
    args.output.mkdir(parents=True)
    for name, text in [('openmitrastar_vopt481_recovered.h',HEADER),('openmitrastar_vopt481_recovered.c',SOURCE)]:
        (args.output/name).write_text(text,encoding='utf-8',newline='\n')
    result={'status':'SOURCE_ONLY_OEM481_POLICY_EFFECTIVE_CONSUMER_CORE',
            'hardware_accessed':False,'firmware_eligible':False,'qualified_records_added':0,
            'pins':{str(path):sha(path)for path in references+[Path(__file__)]},
            'source_files':{path.name:sha(path)for path in args.output.iterdir()if path.is_file()},
            'limits':['No Linux IC/VAP ABI, caller/timer or QDRV provider implementation.',
                      'OEM482 callback remains an exact numeric callback contract, not an existing Linux parameter alias.',
                      'SCS/OCAC/background/beamforming/MuC behavior only established when provider contract is independently verified.',
                      'Guard against absent mandatory provider before mutation is explicit; successful callbacks retain OEM ordering/errors.',
                      'OEM shared global backoff ownership preserved as caller-supplied global state; no invented per-radio equivalence.',
                      'No RF/client/traffic/physical/persistence/release acceptance.']}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
