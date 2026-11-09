/* SPDX-License-Identifier: GPL-2.0-only */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "f344_mode_gate.h"
int main(void)
{
 struct f344_topology s;enum f344_mode mode=F344_MODE_NONE;unsigned cases=0;
#define C(x) do{cases++;assert(x);}while(0)
 memset(&s,0,sizeof(s));C(f344_vap_admit(&s,F344_CREATE_STA0)==F344_GATE_UNKNOWN);
 s.valid=s.core_started=s.primary_mac_matches=s.csa_known=s.channel_hold=s.csa_drained=s.csa_reuse_supported=true;
 C(!f344_vap_admit(&s,F344_CREATE_AP0));C(!f344_vap_admit(&s,F344_CREATE_STA0));
 s.primary_mac_matches=false;C(f344_vap_admit(&s,F344_CREATE_STA0)==F344_GATE_POLICY);s.primary_mac_matches=true;
 s.primary_present=true;s.primary_mode=F344_MODE_STA;C(f344_vap_admit(&s,F344_CREATE_AP1)==F344_GATE_ORDER);
 s.repeater=true;C(!f344_vap_admit(&s,F344_CREATE_AP1));
 s.primary_up=true;C(f344_vap_admit(&s,F344_CREATE_AP1)==F344_GATE_ORDER);s.primary_up=false;
 s.extender=true;C(f344_vap_admit(&s,F344_CREATE_AP1)==F344_GATE_POLICY);s.extender=false;
 s.secondary_present=true;s.secondary_mode=F344_MODE_AP;C(!f344_vap_admit(&s,F344_DELETE_ALL));
 s.other_vaps=1;C(f344_vap_admit(&s,F344_DELETE_ALL)==F344_GATE_POLICY);s.other_vaps=0;
 s.open_gate=true;C(f344_vap_admit(&s,F344_DELETE_ALL)==F344_GATE_ORDER);s.open_gate=false;
 s.secondary_mode=F344_MODE_STA;C(f344_vap_admit(&s,F344_DELETE_ALL)==F344_GATE_POLICY);
 C(!f344_selector_mode(0,false,false,false,F344_MODE_NONE,&mode)&&mode==F344_MODE_AP);
 C(!f344_selector_mode(1,false,false,false,F344_MODE_NONE,&mode)&&mode==F344_MODE_STA);
 C(f344_selector_mode(2,false,false,false,F344_MODE_NONE,&mode)==F344_GATE_UNKNOWN);
 C(!f344_selector_mode(2,false,true,true,F344_MODE_NONE,&mode)&&mode==F344_MODE_AP);
 C(!f344_selector_mode(2,false,true,false,F344_MODE_NONE,&mode)&&mode==F344_MODE_STA);
 C(!f344_selector_mode(2,true,false,false,F344_MODE_NONE,&mode)&&mode==F344_MODE_STA);
 C(!f344_selector_mode(99,false,false,false,F344_MODE_REPEATER,&mode)&&mode==F344_MODE_REPEATER);
 C(f344_selector_mode(99,false,false,false,F344_MODE_NONE,&mode)==F344_GATE_UNKNOWN);
 printf("F344_MODE_GATE_PASS cases=%u hardware=0\n",cases);return 0;
}
