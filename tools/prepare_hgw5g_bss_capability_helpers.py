"""Recover offline-only OEM RRM/BSSTM byte helpers with bounded TLV handling.

Standalone source prototype only: no beacon callers, state fields, capabilities,
module, radio or firmware are changed. Demonstrates two consumers needed by
private operations492/493; their complete features remain unimplemented.
"""
import argparse
import hashlib
import json
from pathlib import Path


HELPERS='''#include <stddef.h>
#include <stdint.h>

/* Exact OEM RRM EnabledCapabilitiesIE70/length5 format. The first capability
 * byte's bit1 advertises NeighborReport support; all other bytes are zero. */
static int om_rrm_enabled_ie(uint8_t *dst,size_t capacity,int neighbor_report)
{
    size_t i;
    if(capacity<7)return -1;
    for(i=0;i<7;i++)dst[i]=0;
    dst[0]=70;dst[1]=5;dst[2]=neighbor_report?2:0;
    return 7;
}

/* Recover OEM update_bss_tm ExtCapIE127 payloadbyte2 bit3. A short or malformed
 * element is refused without an out-of-bounds store; OEM lacked that check.
 * Return1 when changed,0 noExtCap, -1 malformed/short. This is a source
 * prototype, not a port wire API or complete802.11v BSStransition feature. */
static int om_update_bss_tm_bit(uint8_t *ies,size_t len,int enabled)
{
    size_t cursor=0;
    while(cursor<len){
        size_t element_len;
        if(len-cursor<2)return -1;
        element_len=ies[cursor+1];
        if(element_len>len-cursor-2)return -1;
        if(ies[cursor]==127){
            if(element_len<3)return -1;
            if(enabled)ies[cursor+4]|=8;
            else ies[cursor+4]&=(uint8_t)~8U;
            return 1;
        }
        cursor+=element_len+2;
    }
    return 0;
}
'''


FIXTURE='''#include <assert.h>
#include <string.h>
int main(void){uint8_t bytes[258],before[258],dst[8];unsigned id,len,bit,i;int result;
for(bit=0;bit<2;bit++){memset(dst,0xA5,sizeof(dst));assert(om_rrm_enabled_ie(dst,6,bit)==-1);for(i=0;i<8;i++)assert(dst[i]==0xA5);assert(om_rrm_enabled_ie(dst,7,bit)==7);assert(dst[0]==70&&dst[1]==5&&dst[2]==(bit?2:0)&&dst[7]==0xA5);}
for(id=0;id<256;id++)for(len=0;len<256;len++)for(bit=0;bit<2;bit++){
memset(bytes,0xA5,sizeof(bytes));bytes[0]=id;bytes[1]=len;memcpy(before,bytes,sizeof(bytes));result=om_update_bss_tm_bit(bytes,len+2,bit);
if(id==127&&len>=3){assert(result==1);assert(bytes[4]==(bit?(before[4]|8):(before[4]&~8)));before[4]=bytes[4];assert(!memcmp(bytes,before,sizeof(bytes)));}
else if(id==127){assert(result==-1);assert(!memcmp(bytes,before,sizeof(bytes)));}
else {assert(result==0);assert(!memcmp(bytes,before,sizeof(bytes)));}
}
for(len=0;len<258;len++){memset(bytes,0xA5,sizeof(bytes));bytes[0]=127;bytes[1]=255;memcpy(before,bytes,sizeof(bytes));result=om_update_bss_tm_bit(bytes,len,1);if(len<257){assert(result==-1||result==0);assert(!memcmp(bytes,before,sizeof(bytes)));}}
return0;}
'''.replace('return0;','return 0;')


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 h=a.output/'bss_capability_helpers.c';h.write_text(HELPERS);f=a.output/'fixture.c';f.write_text(HELPERS+'\n'+FIXTURE)
 r=dict(status='STANDALONE_SOURCE_HELPERS_NOT_DRIVER_FEATURE',hardware_accessed=False,firmware_eligible=False,helpers_sha256=hashlib.sha256(h.read_bytes()).hexdigest(),operations_related=[492,493],scope='Consumerbytehelpers only; nooperationsacceptedintablecount',limits=['NoIEcallerwiring/statefield/moduleintegration.','Doesnotenable802.11k/v capabilities or actualradio.','MalformedshortTLVs refusalisexplicitsafetydeltafromOEM.'])
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))


if __name__=='__main__':main()
