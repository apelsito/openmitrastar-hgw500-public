"""Constrain unverified MuC descriptor reuse explicitly before transitions."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'work/kernel-port/f344';Q=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
def edit(p,changes):
 s=p.read_text()
 for a,b in changes:
  if a not in s:raise ValueError(str(p)+' missing '+a[:50])
  s=s.replace(a,b)
 p.write_bytes(s.encode())
def main():
 edit(S/'f344_mode_gate.h',[('bool csa_known,csa_pending,channel_hold,csa_drained;','bool csa_known,csa_pending,channel_hold,csa_drained,csa_reuse_supported;')])
 edit(S/'f344_mode_gate.c',[
 ('if(s->csa_pending)return F344_ORDER;', 'if(s->csa_pending)return F344_ORDER;')
 ] if 'F344_ORDER;' in (S/'f344_mode_gate.c').read_text() else [
 ('if(s->csa_pending)return F344_GATE_ORDER;','if(s->csa_pending)return F344_GATE_ORDER;\n if(!s->csa_reuse_supported)return F344_GATE_POLICY;'),
 ('return s->primary_present&&s->primary_mode==F344_MODE_STA?F344_GATE_OK:F344_GATE_ORDER;','return s->primary_present&&(s->primary_mode==F344_MODE_STA||s->primary_mode==F344_MODE_AP)?F344_GATE_OK:F344_GATE_ORDER;')])
 edit(Q/'qdrv_control.c',[
 ('view->csa_known=true;view->csa_pending=', 'view->csa_known=true;view->csa_reuse_supported=!qw->ic.ic_f344_hardware_generation;view->csa_pending='),
 ('view.channel_hold&&!view.primary_up','view.csa_reuse_supported&&view.channel_hold&&!view.primary_up'),
 ('csa_readers=%u\\n",openmitrastar_mode_workflow','csa_readers=%u\\ncsa_reuse_supported=%u\\n",openmitrastar_mode_workflow'),
 ('v.csa_generation,v.csa_readers);','v.csa_generation,v.csa_readers,v.csa_reuse_supported);'),
 ('if(!sp||!sp->csa_lhost)return -ENODEV;','''if(!sp||!sp->csa_lhost)return -ENODEV;
 /* qtn_csa_info has no transaction token. COMPLETE is observable but the
  * fresh-vs-residual IRQ handshake after descriptor reuse is not yet proven.
  * Do not replace a VAP after this boot has published a deferred CSA. */
 if(READ_ONCE(ic->ic_f344_hardware_generation))return -EOPNOTSUPP;''')])
 edit(S/'f344_probe.c',[
 ('"csa_generation", "csa_readers"};','"csa_generation", "csa_readers", "csa_reuse_supported"};'),
 ('values[22]','values[23]'),('i < 22','i < 23'),('seen != 0x3fffff','seen != 0x7fffff'),
 ('s->topology.csa_readers = values[21];','s->topology.csa_readers = values[21];\n  s->topology.csa_reuse_supported = values[22];')])
 edit(S/'f344_transaction.c',[
 ('  if ((before.mode != F344_MODE_AP &&','''  if (!before.topology.csa_reuse_supported) {
    r->error = -95; /* EOPNOTSUPP: unresolved MuC descriptor retirement/reuse. */
    return r->error;
  }
  if ((before.mode != F344_MODE_AP &&'''),
 ('  if (rollback && original->mode == F344_MODE_REPEATER &&','  if (rollback && original->three_address_bridge != observed->three_address_bridge)\n    return -5;\n  if (rollback && original->mode == F344_MODE_REPEATER &&')])
 edit(S/'f344_backend.c',[
 ('return t->mode == F344_MODE_AP ? 0 : qdrv_command("bridge 0 enable\\n");','''return qdrv_command((rollback || t->mode == F344_MODE_AP) &&
                                !original->three_address_bridge
                            ? "bridge 0 disable\\n" : "bridge 0 enable\\n");''')])
 edit(S/'test_mode_gate.c',[('s.channel_hold=s.csa_drained=true;','s.channel_hold=s.csa_drained=s.csa_reuse_supported=true;')])
 edit(S/'test_transaction.c',[
 ('s->topology.csa_known=true;','s->topology.csa_known=s->topology.csa_reuse_supported=true;'),
 ('case F344_SET_BRIDGE_POLICY:s->three_address_bridge=true;','case F344_SET_BRIDGE_POLICY:s->three_address_bridge=rollback||t->mode==F344_MODE_AP?original->three_address_bridge:true;'),
 (' setup(&f,F344_MODE_AP);f.state.valid=0;', ' setup(&f,F344_MODE_AP);f.state.topology.csa_reuse_supported=false;C(f344_apply(&ops,&target,&result)==-95&&!f.calls&&result.outcome==F344_REJECTED);\n setup(&f,F344_MODE_AP);f.state.valid=0;')])
 for n in ('f344_mode_gate.h','f344_mode_gate.c'):(Q/n).write_bytes((S/n).read_bytes())
 # Keep a proof of COMPLETE separately, and assert the stronger final guard.
 p=ROOT/'tools/test_f344_csa.py';s=p.read_text()
 s=s.replace('firmware.lhost_status=0; wlan.ic.ic_f344_hardware_generation=1;\n C(qdrv_command_mode(&dev,3,a)==-EAGAIN); /* POST is not COMPLETE */\n firmware.muc_status=QTN_CSA_STATUS_MUC_COMPLETE; /* explicit fake OEM completion */','''firmware.lhost_status=0; wlan.ic.ic_f344_hardware_generation=1;
 C(qdrv_command_mode(&dev,3,a)==-EOPNOTSUPP); /* final scope forbids reuse */
 firmware.muc_status=QTN_CSA_STATUS_MUC_COMPLETE;
 C(qdrv_command_mode(&dev,3,a)==-EOPNOTSUPP); /* COMPLETE is not a new epoch token */
 wlan.ic.ic_f344_hardware_generation=0; /* separate fresh-boot fixture */''')
 s=s.replace('C(joins==5&&f344_policy.drained);','C(joins==4&&f344_policy.drained);');p.write_bytes(s.encode())
if __name__=='__main__':main()
