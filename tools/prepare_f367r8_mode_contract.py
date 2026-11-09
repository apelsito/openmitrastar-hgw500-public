"""Correct the OEM setter token and bound observation of its asynchronous CSA."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay/usr/sbin/om-f367-control'
DEST=ROOT/'versions/lyoko-foundation-6.11.7-f367r8-mode-contract'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if DEST.exists():raise ValueError('immutable R8 source already exists')
 assert sha(SOURCE)=='fc3cb92b665ccd8a4b4d2f23bda7ff44652466db3d9a6abe5ecee3842c4cbd22'
 s=SOURCE.read_text()
 old=''' "$iwpriv" wifi0 mode 11ac20 >/dev/null 2>&1 || fail mode20
 "$iwpriv" wifi0 radar_bw 20 >/dev/null 2>&1 || fail filter20
 "$iwconfig" wifi0 channel 52 >/dev/null 2>&1 || fail channel52
 "$iwpriv" wifi0 get_region | grep -q 'get_region:21317' || fail region-readback
 "$iwpriv" wifi0 get_mode | grep -qi '11ac20' || fail mode-readback
 f367_load_snapshot || fail context-readback
 [ "${channel-}" = 52 ] && [ "${filter_bw-}" = 20 ] && [ "${phymode-}" = 11 ] && [ "${region_es-}" = 1 ] && [ "${doth-}" = 1 ] && [ "${tpc-}" = 1 ] || fail context-not52-20
'''
 new=''' # OEM write vocabulary is "11ac"; its readback vocabulary is "11ac20".
 printf 'OMF367_MODE_REQUEST request=11ac bandwidth=20\\n'
 mode_rc=0
 "$iwpriv" wifi0 mode 11ac >/dev/null 2>&1 || mode_rc=$?
 printf 'OMF367_MODE_RESULT request=11ac exit_code=%s\\n' "$mode_rc"
 [ "$mode_rc" = 0 ] || fail mode20
 filter_rc=0
 "$iwpriv" wifi0 radar_bw 20 >/dev/null 2>&1 || filter_rc=$?
 printf 'OMF367_FILTER_RESULT request=20 exit_code=%s\\n' "$filter_rc"
 [ "$filter_rc" = 0 ] || fail filter20
 f367_load_snapshot || fail context-clock
 case "${monotonic_ms-}" in ''|*[!0-9]*) fail context-clock;; esac
 context_started_ms=$monotonic_ms
 context_deadline_ms=$((context_started_ms+5000))
 channel_rc=0
 "$iwconfig" wifi0 channel 52 >/dev/null 2>&1 || channel_rc=$?
 printf 'OMF367_CHANNEL_RESULT request=52 exit_code=%s\\n' "$channel_rc"
 [ "$channel_rc" = 0 ] || fail channel52
 "$iwpriv" wifi0 get_region | grep -q 'get_region:21317' || fail region-readback
 "$iwpriv" wifi0 get_mode | grep -qi '11ac20' || fail mode-readback
 # The AP RUN ioctl queues CSA. Observe completion; never repeat a write or
 # renew a watchdog/CAC/NOP deadline while waiting for the cached context.
 context_attempts=0
 while :; do
  f367_load_snapshot || fail context-readback
  case "${monotonic_ms-}" in ''|*[!0-9]*) fail context-clock;; esac
  [ "$monotonic_ms" -ge "$context_started_ms" ] || fail context-clock-regressed
  context_elapsed_ms=$((monotonic_ms-context_started_ms))
  if [ "$monotonic_ms" -gt "$context_deadline_ms" ]; then
   printf 'OMF367_CONTEXT_READBACK result=timeout elapsed_ms=%s channel=%s filter_bw=%s phymode=%s\\n' "$context_elapsed_ms" "${channel:-0}" "${filter_bw:-0}" "${phymode:-0}"
   fail context-readback-timeout
  fi
  if [ "${control_fault-}" != 0 ] || [ "${tx_fault_latched-}" != 0 ]; then
   printf 'OMF367_CONTEXT_READBACK result=fault elapsed_ms=%s control_fault=%s tx_fault_latched=%s\\n' "$context_elapsed_ms" "${control_fault:-1}" "${tx_fault_latched:-1}"
   fail kernel-fault
  fi
  if [ "${channel-}" = 52 ] && [ "${filter_bw-}" = 20 ] && [ "${phymode-}" = 11 ] && [ "${region_es-}" = 1 ] && [ "${doth-}" = 1 ] && [ "${tpc-}" = 1 ]; then
   printf 'OMF367_CONTEXT_READBACK result=pass elapsed_ms=%s channel=52 filter_bw=20 phymode=11 region_es=1 doth=1 tpc=1\\n' "$context_elapsed_ms"
   break
  fi
  if [ "$monotonic_ms" -ge "$context_deadline_ms" ] || [ "$context_attempts" -ge 5 ]; then
   printf 'OMF367_CONTEXT_READBACK result=timeout elapsed_ms=%s channel=%s filter_bw=%s phymode=%s\\n' "$context_elapsed_ms" "${channel:-0}" "${filter_bw:-0}" "${phymode:-0}"
   fail context-readback-timeout
  fi
  context_attempts=$((context_attempts+1))
  sleep 1
 done
'''
 assert s.count(old)==1;s=s.replace(old,new)
 target=DEST/'overlay/usr/sbin/om-f367-control';target.parent.mkdir(parents=True);target.write_bytes(s.encode())
 report=dict(schema='openmitrastar.f367r8-mode-source/v1',status='PREPARED_FOR_AFFECTED_TESTS',source=item(SOURCE),artifact=item(target),setter='11ac',getter='11ac20',channel_readback_deadline_ms=5000,write_attempts_per_command=1,timers_changed=False,hardware_actions=False)
 (DEST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
def item(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
if __name__=='__main__':main()
