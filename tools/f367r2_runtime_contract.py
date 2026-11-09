"""Protected readonly preamble; existing F367 radio/kernel contracts unchanged."""
from pathlib import Path
import f367_runtime_contract as previous
ROOT=Path(__file__).resolve().parents[1]
VERSION='lyoko-foundation-6.11.1-f367r2-protected-preamble-device'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.1-f367r2-protected-preamble/overlay'
def once(s,old,new):
 if s.count(old)!=1:raise ValueError('preamble anchor not unique '+old[:80])
 return s.replace(old,new,1)
def native_start(source,base_qdrv_sha,new_qdrv_sha):
 s=previous.native_start(source,base_qdrv_sha,new_qdrv_sha).decode()
 s=once(s,'mkdir -p "$state"\nchmod 0700 "$state"',
  '/usr/sbin/om-f367-stage verify preamble || refuse f367-watchdog-not-protecting-preamble\nmkdir -p "$state"\nchmod 0700 "$state"')
 s=once(s,'\t\tdigest=$(sha256sum "$calibration/$file"',
  '\t\t/usr/sbin/om-f367-stage verify preamble || refuse f367-watchdog-calibration-check\n\t\tdigest=$(sha256sum "$calibration/$file"')
 s=once(s,'\t\tactual=$(sha256sum "$path"',
  '\t\t/usr/sbin/om-f367-stage verify preamble || refuse f367-watchdog-artifact-check\n\t\tactual=$(sha256sum "$path"')
 guard='/usr/sbin/om-f367-stage verify module-load || refuse f367-watchdog-not-protecting-module-load'
 s=once(s,guard,'''# No module can load until both the foreground and the actual keeper are protected.
/usr/sbin/om-f367-stage require-keeper preamble || refuse f367-keeper-not-protecting-module-load
/usr/sbin/om-f367-stage complete preamble || refuse f367-watchdog-preamble-complete
/usr/sbin/om-f367-stage begin module-load 30000 || refuse f367-watchdog-module-begin
'''+guard)
 return s.encode()
def overlay():return {p.relative_to(OVERLAY).as_posix():p.read_bytes() for p in OVERLAY.rglob('*') if p.is_file()}
