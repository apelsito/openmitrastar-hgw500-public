/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "f344_transaction.h"
struct fixture {struct f344_state state,before;unsigned calls;int fail_at,rollback_fail,lie,drift;};
static unsigned checks;
#define C(x) do{checks++;assert(x);}while(0)
static void mask(uint8_t*m){memset(m,0,32);m[36/8]|=1U<<(36%8);m[40/8]|=1U<<(40%8);m[44/8]|=1U<<(44%8);m[48/8]|=1U<<(48%8);}
static void settled(struct f344_state*s,enum f344_mode mode)
{
 s->topology.csa_known=s->topology.csa_reuse_supported=true;s->mode=mode;s->topology.valid=s->topology.core_started=true;s->topology.primary_present=s->topology.primary_up=s->topology.open_gate=true;
 s->topology.primary_mode=mode==F344_MODE_AP?F344_MODE_AP:F344_MODE_STA;
 s->topology.repeater=mode==F344_MODE_REPEATER;s->topology.secondary_present=s->topology.secondary_up=mode==F344_MODE_REPEATER;s->topology.secondary_mode=mode==F344_MODE_REPEATER?F344_MODE_AP:F344_MODE_NONE;
 s->primary_bridged=true;s->secondary_bridged=mode==F344_MODE_REPEATER;s->ap_enabled=mode!=F344_MODE_STA;s->upstream_completed=mode!=F344_MODE_AP;s->three_address_bridge=true;
}
static void setup(struct fixture*f,enum f344_mode mode)
{
 memset(f,0,sizeof(*f));f->fail_at=-1;f->state.valid=F344_SNAPSHOT_VALID;f->state.snapshot_cookie=100;f->state.bandwidth=f->state.configured_bandwidth=80;f->state.frequency_mhz=5180;
 mask(f->state.channel_mask);memset(f->state.management_digest,0x55,32);memset(f->state.profile_digest,1,32);f->state.primary_mac[0]=2;f->state.primary_mac[5]=1;f->state.secondary_mac[0]=2;f->state.secondary_mac[5]=2;settled(&f->state,mode);f->before=f->state;
}
static int snapshot(void*c,struct f344_state*s){struct fixture*f=c;*s=f->state;return 0;}
static int inspect(void*c,struct f344_state*s){struct fixture*f=c;*s=f->state;return 0;}
static int execute(void*c,enum f344_action a,const struct f344_target*t,const struct f344_state*original,bool rollback)
{
 struct fixture*f=c;struct f344_state*s=&f->state;(void)original;f->calls++;
 if((!rollback&&(int)a==f->fail_at)||(rollback&&f->rollback_fail))return -99;
 if(!rollback&&f->lie&&a==F344_SET_CHANNEL_POLICY)return 0;
 switch(a){
 case F344_GUARD_MANAGEMENT:s->topology.channel_hold=true;s->topology.csa_drained=false;break;
 case F344_STOP_SECURITY:s->ap_enabled=s->upstream_completed=false;break;
 case F344_DOWN_VAPS:s->topology.primary_up=s->topology.secondary_up=false;break;
 case F344_CLOSE_OPEN_GATE:s->topology.open_gate=false;break;
 case F344_DRAIN_CSA:C(!s->topology.primary_up&&!s->topology.secondary_up&&!s->topology.open_gate&&s->topology.channel_hold);s->topology.csa_pending=false;s->topology.csa_drained=true;break;
 case F344_DETACH_WIFI:s->primary_bridged=s->secondary_bridged=false;break;
 case F344_REPEATER_CLEAR:s->topology.repeater=false;break;
 case F344_DELETE_VAPS:
  C(!s->topology.primary_up&&!s->topology.secondary_up&&!s->topology.open_gate);
  s->topology.primary_present=s->topology.secondary_present=false;s->mode=F344_MODE_NONE;break;
 case F344_CREATE_PRIMARY:C(!s->topology.primary_present);s->topology.primary_present=true;s->topology.primary_mode=t->mode==F344_MODE_AP?F344_MODE_AP:F344_MODE_STA;s->mode=s->topology.primary_mode;break;
 case F344_SET_CHANNEL_POLICY:memcpy(s->channel_mask,t->channel_mask,32);s->bandwidth=s->configured_bandwidth=t->bandwidth;s->frequency_mhz=t->mode==F344_MODE_AP?t->ap_frequency_mhz:5180;break;
 case F344_REPEATER_ENABLE:C(s->topology.primary_mode==F344_MODE_STA);s->topology.repeater=true;s->mode=F344_MODE_REPEATER;break;
 case F344_CREATE_SECONDARY:C(s->topology.primary_present&&s->topology.primary_mode==F344_MODE_STA&&s->topology.repeater);s->topology.secondary_present=true;s->topology.secondary_mode=F344_MODE_AP;break;
 case F344_SET_BRIDGE_POLICY:s->three_address_bridge=rollback||t->mode==F344_MODE_AP?original->three_address_bridge:true;break;
 case F344_ATTACH_WIFI:s->primary_bridged=true;s->secondary_bridged=s->topology.secondary_present;break;
 case F344_CONFIGURE_SECURITY:memcpy(s->profile_digest,t->profile_digest,32);break;
 case F344_OPEN_GATE:C(s->topology.csa_drained);s->topology.channel_hold=false;s->topology.open_gate=true;break;
 case F344_START_SECURITY:s->topology.primary_up=true;s->topology.secondary_up=s->topology.secondary_present;break;
 }
 if(!rollback&&f->drift&&a==F344_DETACH_WIFI)s->management_digest[0]^=1;
 return 0;
}
static int wait_target(void*c,const struct f344_target*t,struct f344_state*out)
{struct fixture*f=c;f->state.ap_enabled=t->mode!=F344_MODE_STA;f->state.upstream_completed=t->mode!=F344_MODE_AP;*out=f->state;return 0;}
int main(void)
{
 struct fixture f;struct f344_ops ops={&f,snapshot,inspect,execute,wait_target};struct f344_target target;struct f344_result result;unsigned a,b,n;uint8_t get[32],set[32];
 memset(&target,0,sizeof(target));target.profile_cookie=200;target.bandwidth=80;target.ap_frequency_mhz=5180;mask(target.channel_mask);memset(target.profile_digest,2,32);
 for(a=F344_MODE_AP;a<=F344_MODE_REPEATER;a++)for(b=F344_MODE_AP;b<=F344_MODE_REPEATER;b++){
  setup(&f,a);target.mode=b;C(!f344_apply(&ops,&target,&result));C(result.outcome==F344_APPLIED_READBACK&&!result.traffic_verified&&f344_target_observed(&target,&f.state));C(!memcmp(f.before.management_digest,f.state.management_digest,32));
 }
 for(n=0;n<=F344_START_SECURITY;n++){
  setup(&f,F344_MODE_AP);target.mode=F344_MODE_REPEATER;f.fail_at=n;
  C(f344_apply(&ops,&target,&result)!=0);C(result.outcome==F344_ROLLED_BACK_READBACK&&result.rollback_actions>0&&!result.traffic_verified);C(f.state.mode==F344_MODE_AP&&!memcmp(f.before.profile_digest,f.state.profile_digest,32));
 }
 setup(&f,F344_MODE_AP);target.mode=F344_MODE_STA;f.fail_at=F344_CREATE_PRIMARY;f.rollback_fail=1;C(f344_apply(&ops,&target,&result)!=0&&result.outcome==F344_ROLLBACK_FAILED);
 setup(&f,F344_MODE_AP);target.mode=F344_MODE_AP;memcpy(target.profile_digest,f.state.profile_digest,32);C(!f344_apply(&ops,&target,&result)&&result.outcome==F344_UNCHANGED&&f.calls==0);memset(target.profile_digest,2,32);
 setup(&f,F344_MODE_AP);f.state.topology.csa_reuse_supported=false;C(f344_apply(&ops,&target,&result)==-95&&!f.calls&&result.outcome==F344_REJECTED);
 setup(&f,F344_MODE_AP);f.state.valid=0;C(f344_apply(&ops,&target,&result)!=0&&result.outcome==F344_REJECTED&&!f.calls);
 setup(&f,F344_MODE_AP);f.state.topology.extender=true;C(f344_apply(&ops,&target,&result)!=0&&!f.calls);
 setup(&f,F344_MODE_AP);f.drift=1;C(f344_apply(&ops,&target,&result)!=0&&result.outcome==F344_ROLLBACK_FAILED);
 setup(&f,F344_MODE_AP);f.state.frequency_mhz=100000;C(!f344_target_observed(&target,&f.state));
 for(n=1;n<256;n++){memset(get,0,32);get[n/8]|=1U<<(n%8);C(!f344_channel_encode(get,1,set));C(set[(n-1)/8]==(uint8_t)(1U<<((n-1)%8)));}
 memset(get,0,32);get[0]=1;C(f344_channel_encode(get,1,set)!=0);mask(get);C(f344_mask_non_dfs(get));get[52/8]|=1U<<(52%8);C(!f344_mask_non_dfs(get));
 printf("F344_TRANSACTION_PASS checks=%u transitions=9 failure_injections=%u hardware=0 traffic_verified=0\n",checks,(unsigned)F344_START_SECURITY+1);return 0;
}
