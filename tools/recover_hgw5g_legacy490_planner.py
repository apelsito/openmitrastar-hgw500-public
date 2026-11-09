"""Recover OEM490 rate/mode plan as sourcefixture, no naked flag alias.

Pureplanner represents observedcontrolflow and restoretransaction. ActualPHY/
mode callbacks and per-radio savedstate mustbe bound inport before moduleAPI.
No candidate23 record is published untilthosebindingsandABIusersqualified.
"""
import argparse
import hashlib
import json
from pathlib import Path

PLANNER='''#include <stdint.h>
#include <stddef.h>
struct legacy490_state {int saved_mode;int fixed;};
struct legacy490_plan {uint32_t wire;int next_mode;int write_mode;int update_profile;int profile_is_5g;int profile_vht;int channel_callback;};
static int legacy490_plan(struct legacy490_state *state,int value,unsigned current_mode,int phy_mode,int rf_chip,int ic_opmode,int vap_opmode,struct legacy490_plan *plan)
{
    int target=-1;
    uint32_t wire;
    if(value<0){
        if(!state->fixed)return -22;
        target=state->saved_mode;
        state->fixed=0;state->saved_mode=0;
        if((unsigned)(target-1)<6U)target=-1;
        wire=255U;
    }else{
        if(value>12)return -22;
        wire=0x7f000000U|(uint32_t)value|((uint32_t)value<<8)|((uint32_t)value<<16);
        if((uint16_t)(current_mode-1U)<6U)target=-1;
        else if(phy_mode==1||phy_mode==7||phy_mode==10||(unsigned)(phy_mode-11)<4U)target=1;
        else target=3;
        if(!state->fixed){state->saved_mode=current_mode;state->fixed=1;}
    }
    plan->wire=wire;plan->next_mode=target;plan->write_mode=target!=-1;
    plan->update_profile=target!=-1&&rf_chip==2&&ic_opmode==1;
    plan->profile_is_5g=phy_mode==1||phy_mode==7||phy_mode==10||(unsigned)(phy_mode-11)<4U;
    plan->profile_vht=target>10;
    plan->channel_callback=target!=-1&&vap_opmode==6;
    return 0;
}
'''

FIXTURE='''#include <assert.h>
int main(void){struct legacy490_state state;struct legacy490_plan plan;unsigned mode,phy,v;int result;
for(mode=0;mode<15;mode++)for(phy=0;phy<15;phy++)for(v=0;v<13;v++){
state.saved_mode=0;state.fixed=0;result=legacy490_plan(&state,v,mode,phy,2,1,6,&plan);assert(result==0);assert(state.saved_mode==(int)mode&&state.fixed==1);assert(plan.wire==(0x7f000000U|v|(v<<8)|(v<<16)));int next=plan.next_mode;
result=legacy490_plan(&state,-1,mode,next,2,1,6,&plan);assert(result==0&&state.fixed==0&&state.saved_mode==0&&plan.wire==255);assert(plan.next_mode==((mode>=1&&mode<=6)?-1:(int)mode));}
state.saved_mode=7;state.fixed=1;assert(legacy490_plan(&state,13,7,11,2,1,6,&plan)==-22&&state.saved_mode==7&&state.fixed==1);state.fixed=0;assert(legacy490_plan(&state,-1,7,11,2,1,6,&plan)==-22&&state.fixed==0);
state.saved_mode=11;state.fixed=1;assert(legacy490_plan(&state,-2,7,11,2,1,6,&plan)==0&&plan.next_mode==11&&plan.wire==255);return0;}
'''.replace('return0;','return 0;')

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);(a.output/'legacy490_plan.c').write_text(PLANNER);(a.output/'fixture.c').write_text(PLANNER+FIXTURE)
 r=dict(status='RECOVERED_490_PLANNER_SOURCE_ONLY_NO23_RECORD',hardware_accessed=False,firmware_eligible=False,planner_sha256=hashlib.sha256(PLANNER.encode()).hexdigest(),wire='Allnegativevaluesrestorefixedstateifactive;255;0..12encode0x7fVVVVVV',first_blocker='Noexistingper-radio savedmode/fixedstateinretainedhostABI; exactic_set_channel/profilecallbacksneededbeforedriverdispatchbinding',next_bindings=['state.sharedperradio notperVAP','ic_curmode/phy_mode/des_mode + setmodecallbackmapping','CHIPID_DUAL2+STA1 profile5g/2gVHTfield update','CSAconfigreason4 thenreassoc(vap0,1) andHOSTAPchannelcallback'],limits='Pureplanfixtureonly,noPHY/callbackinvocationorNAC23moduleclaim')
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))

if __name__=='__main__':main()
