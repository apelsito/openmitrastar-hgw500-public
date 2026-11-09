from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'work/kernel-port/f344';Q=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
def edit(p,changes):
 s=p.read_text()
 for a,b in changes:
  if a not in s:raise ValueError(str(p)+': missing '+a[:70])
  s=s.replace(a,b)
 p.write_bytes(s.encode())
def main():
 edit(S/'f344_mode_gate.h', [('bool csa_known,csa_pending,channel_hold;','bool csa_known,csa_pending,channel_hold,csa_drained;\n unsigned csa_generation,csa_readers;')])
 edit(Q/'qdrv_control.c', [
 ('view->channel_hold=READ_ONCE(openmitrastar_mode_channel_hold);','''spin_lock_irqsave(&f344_policy_lock,flags);
  view->channel_hold=f344_policy.hold;view->csa_drained=f344_policy.drained;
  view->csa_generation=f344_policy.generation;view->csa_readers=f344_policy.readers;
  spin_unlock_irqrestore(&f344_policy_lock,flags);'''),
 ('view->csa_pending=!!(sp->csa_lhost','view->csa_pending=!!view->csa_readers||!!(sp->csa_lhost'),
 ('scnprintf(buf,512,','scnprintf(buf,1024,'),
 ('channel_hold=%u\\n",openmitrastar_mode_workflow','channel_hold=%u\\ncsa_drained=%u\\ncsa_generation=%u\\ncsa_readers=%u\\n",openmitrastar_mode_workflow'),
 ('v.csa_known,v.csa_pending,v.channel_hold);','v.csa_known,v.csa_pending,v.channel_hold,v.csa_drained,v.csa_generation,v.csa_readers);')])
 # A completion interrupt after software retirement is not a new request.
 edit(Q/'qdrv_wlan.c', [('\tif (muc_status & QTN_CSA_STATUS_MUC_PRE &&','\tif (!(lhost_status & QTN_CSA_STATUS_LHOST_ACTIVE)) return;\n\n\tif (muc_status & QTN_CSA_STATUS_MUC_PRE &&')])
 edit(S/'f344_transaction.h',[('  F344_CLOSE_OPEN_GATE,','  F344_CLOSE_OPEN_GATE,\n  F344_DRAIN_CSA,')])
 edit(S/'f344_transaction.c',[('F344_CLOSE_OPEN_GATE,  F344_DETACH_WIFI,','F344_CLOSE_OPEN_GATE, F344_DRAIN_CSA, F344_DETACH_WIFI,')])
 p=S/'f344_backend.c';s=p.read_text();a=s.index('    for (;;) {',s.index('  case F344_DOWN_VAPS:'));b=s.index('  case F344_CLOSE_OPEN_GATE:',a)
 s=s[:a]+'    return 0;\n'+s[b:]
 a=s.index('  case F344_DETACH_WIFI:')
 s=s[:a]+'''  case F344_DRAIN_CSA:
    for (;;) {
      struct f344_state state = {0};
      struct timespec pause = {0, 10000000};
      uint64_t now = f344_now_ms();
      int rc;
      if (!now || now >= n->phase_deadline || now >= n->global_deadline)
        return -1;
      rc = qdrv_command("mode 0 drain-csa\\n");
      if (f344_layout_observe(&state) || !state.topology.csa_known ||
          !state.topology.channel_hold || state.topology.open_gate ||
          state.topology.primary_up || state.topology.secondary_up)
        return -1;
      if (!rc && state.topology.csa_drained && !state.topology.csa_pending)
        return 0;
      if (!state.topology.csa_pending) return -1;
      nanosleep(&pause, 0);
    }
'''+s[a:];p.write_bytes(s.encode())
 edit(S/'f344_probe.c', [
 ('"channel_hold"};','"channel_hold", "csa_drained", "csa_generation", "csa_readers"};'),
 ('unsigned values[19]','unsigned values[22]'),
 ('value > 255','value > UINT32_MAX'),('i < 19','i < 22'),
 ('seen != 0x7ffff','seen != 0x3fffff'),
 ('i != 15 && values[i] > 1','i != 15 && i != 20 && i != 21 && values[i] > 1'),
 ('s->topology.channel_hold = values[18];','s->topology.channel_hold = values[18];\n  s->topology.csa_drained = values[19];\n  s->topology.csa_generation = values[20];\n  s->topology.csa_readers = values[21];')])
 edit(S/'test_mode_gate.c',[('s.valid=s.core_started=s.primary_mac_matches=true;','s.valid=s.core_started=s.primary_mac_matches=s.csa_known=true;')])
 edit(S/'test_transaction.c',[
 ('s->mode=mode;s->topology.valid','s->topology.csa_known=true;s->mode=mode;s->topology.valid'),
 ('f->state.bandwidth=80;','f->state.bandwidth=f->state.configured_bandwidth=80;'),
 ('case F344_GUARD_MANAGEMENT:break;','case F344_GUARD_MANAGEMENT:s->topology.channel_hold=true;s->topology.csa_drained=false;break;'),
 ('case F344_DETACH_WIFI:', 'case F344_DRAIN_CSA:C(!s->topology.primary_up&&!s->topology.secondary_up&&!s->topology.open_gate&&s->topology.channel_hold);s->topology.csa_pending=false;s->topology.csa_drained=true;break;\n case F344_DETACH_WIFI:'),
 ('s->bandwidth=t->bandwidth;','s->bandwidth=s->configured_bandwidth=t->bandwidth;'),
 ('case F344_OPEN_GATE:s->topology.open_gate=true;','case F344_OPEN_GATE:C(s->topology.csa_drained);s->topology.channel_hold=false;s->topology.open_gate=true;')])
 for n in ('f344_mode_gate.h','f344_mode_gate.c'):(Q/n).write_bytes((S/n).read_bytes())
if __name__=='__main__':main()
