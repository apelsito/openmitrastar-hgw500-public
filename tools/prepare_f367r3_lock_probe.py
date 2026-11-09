"""Generate a tiny root-owned HGW probe; generation itself accesses no hardware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'versions/lyoko-foundation-6.11.2-f367r3-owned-lock-release/overlay/usr/sbin/om-f367-stage'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 source=STAGE.read_text();begin=source.index('release_lock()\n{');end=source.index('\nfinish_stage()\n{',begin);body=source[begin:end]
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367r3-lock-probe-'+stamp);out.mkdir(parents=True,exist_ok=False)
 script='''#!/bin/ash
set -eu
umask 077
# One new private fixture only. No production ipc-lock, watchdog or radio path.
lock_dir="/run/openmitrastar/f367r3-lock-probe-$$"
lock_owner=$$
mkdir "$lock_dir" || { printf 'LOCK_PROBE_REFUSED already-exists=1\\n'; exit 73; }
lock_owned=1
printf '%s\\n' "$lock_owner" >"$lock_dir/.owner"
'''+body+'''
if ! release_lock; then
 printf 'LOCK_PROBE_FAIL reason=%s fixture=%s\\n' "$lock_error" "$lock_dir"
 exit 74
fi
[ ! -e "$lock_dir" ] && [ ! -L "$lock_dir" ] || { printf 'LOCK_PROBE_FAIL reason=fixture-remains\\n'; exit 74; }
printf 'F367R3_EXACT_LOCK_RELEASE_PASS watchdog=0 radio=0 mtd=0 preexisting_data=0\\n'
'''
 p=out/'probe.sh';p.write_bytes(script.encode())
 result={'schema':'openmitrastar.f367r3-lock-probe-package/v1','status':'READY_FOR_ROOT_ONE_OWNED_EMPTY_DIRECTORY_PROBE','probe':{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size},'stage':{'path':str(STAGE),'sha256':sha(STAGE)},'exact_function_sha256':hashlib.sha256(body.encode()).hexdigest(),'scope':'one freshly created private /run/openmitrastar/f367r3-lock-probe-PID directory; exact cleanup body, no watchdog/radio/MTD','hardware_execution':False}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
