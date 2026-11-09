/* SPDX-License-Identifier: GPL-2.0-only */
#include "f344_mode_gate.h"
int f344_vap_admit(const struct f344_topology*s,enum f344_vap_operation op)
{
 if(!s||!s->valid||!s->core_started||!s->csa_known)return F344_GATE_UNKNOWN;
 if(s->csa_pending)return F344_GATE_ORDER;
 if(!s->csa_reuse_supported)return F344_GATE_POLICY;
 if(s->other_vaps||s->extender)return F344_GATE_POLICY;
 if(s->open_gate||s->primary_up||s->secondary_up)return F344_GATE_ORDER;
 if((s->primary_present||s->secondary_present)&&(!s->channel_hold||!s->csa_drained))return F344_GATE_ORDER;
 switch(op){
 case F344_CREATE_AP0:case F344_CREATE_STA0:
  if(s->primary_present||s->secondary_present||s->repeater)return F344_GATE_ORDER;
  return s->primary_mac_matches?F344_GATE_OK:F344_GATE_POLICY;
 case F344_CREATE_AP1:
  return s->primary_present&&s->primary_mode==F344_MODE_STA&&!s->secondary_present&&s->repeater?F344_GATE_OK:F344_GATE_ORDER;
 case F344_DELETE_ALL:
  if(s->primary_present&&s->primary_mode!=F344_MODE_AP&&s->primary_mode!=F344_MODE_STA)return F344_GATE_POLICY;
  /* Clearing the repeater flag while its primary STA still exists is an
   * intentional intermediate state before native stop0all. */
  if(s->secondary_present&&(!s->primary_present||s->primary_mode!=F344_MODE_STA||s->secondary_mode!=F344_MODE_AP))return F344_GATE_POLICY;
  return F344_GATE_OK;
 case F344_BRIDGE_CONFIG:
  return s->primary_present&&(s->primary_mode==F344_MODE_STA||s->primary_mode==F344_MODE_AP)?F344_GATE_OK:F344_GATE_ORDER;
 default:return F344_GATE_POLICY;
 }
}
int f344_selector_mode(unsigned selector,bool static_ip,bool lease_known,bool lease_present,enum f344_mode configured,enum f344_mode*result)
{
 if(!result)return F344_GATE_UNKNOWN;
 if(selector==0){*result=F344_MODE_AP;return 0;}
 if(selector==1){*result=F344_MODE_STA;return 0;}
 if(selector==2){
  if(static_ip){*result=F344_MODE_STA;return 0;}
  if(!lease_known)return F344_GATE_UNKNOWN;
  *result=lease_present?F344_MODE_AP:F344_MODE_STA;return 0;
 }
 if(configured!=F344_MODE_AP&&configured!=F344_MODE_STA&&configured!=F344_MODE_REPEATER)return F344_GATE_UNKNOWN;
 *result=configured;return 0;
}
