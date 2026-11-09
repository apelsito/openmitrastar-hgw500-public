"""Create new shell-only F367r2 revision without editing the sealed F367."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'versions/lyoko-foundation-6.11.0-f367-ap-dfs/overlay'
DST=ROOT/'versions/lyoko-foundation-6.11.1-f367r2-protected-preamble/overlay'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('revision anchor '+a[:90])
 return s.replace(a,b,1)
def main():
 if DST.exists():raise ValueError('immutable revision exists')
 shutil.copytree(SRC,DST)
 p=DST/'usr/sbin/om-radio5-start';s=p.read_text();s=once(s,'"$stage" begin module-load 30000','"$stage" begin preamble 30000');p.write_bytes(s.encode())
 p=DST/'usr/sbin/om-f367-stage';s=p.read_text()
 s=once(s,'request(){ "$wdt" --request "$token" "$sequence" "$@" >"$state/last-ack.json"; }','''number(){ awk -F'"'"$1"'":' 'NF==2{split($2,a,",");print a[1]}' "$2"; }
owner_refusal(){
 operation=$1; client_rc=$2
 "$wdt" --status "$token" >"$state/owner-at-refusal.json" 2>/dev/null || true
 owner_state=$(sed -n 's/.*"state":"\\([a-z-]*\\)".*/\\1/p' "$state/owner-at-refusal.json")
 case "$owner_state" in idle|waiting-phase|phase-active|ceased-fd-held) ;; *) owner_state=unavailable;; esac
 health=$(number health_deadline_monotonic_ms "$state/owner-at-refusal.json"); deadline=$(number phase_deadline_monotonic_ms "$state/owner-at-refusal.json")
 case "$health" in ''|*[!0-9]*) health=unavailable;; esac
 case "$deadline" in ''|*[!0-9]*) deadline=unavailable;; esac
 printf 'OMF367_WDT_REJECT operation=%s client_rc=%s local_phase=%s local_sequence=%s owner_state=%s health_deadline_ms=%s phase_deadline_ms=%s\\n' "$operation" "$client_rc" "$phase" "$sequence" "$owner_state" "$health" "$deadline" >&2
}
request(){
 if "$wdt" --request "$token" "$sequence" "$@" >"$state/last-ack.json"; then return 0; else rc=$?; fi
 owner_refusal "$1" "$rc"; return "$rc"
}''')
 s=once(s,'in module-load:30000|','in preamble:30000|module-load:30000|')
 s=once(s,'verify) [ "${2:-}" = "$phase" ] || exit 25; request HEALTH ok || exit 24;;','''verify) [ "${2:-}" = "$phase" ] || { owner_refusal phase-mismatch 25; exit 25; }; request HEALTH ok || exit 24;;
require-keeper)
 [ "${2:-}" = "$phase" ] || { owner_refusal phase-mismatch 25; exit 25; }
 request HEALTH ok || exit 24
 proof="$state/keeper-health.json"
 [ -r "$proof" ] || { owner_refusal keeper-missing 28; exit 28; }
 keeper_phase=$(sed -n 's/.*"phase":"\\([a-z0-9_-]*\\)".*/\\1/p' "$proof")
 keeper_sequence=$(number phase_sequence "$proof"); keeper_deadline=$(number health_deadline_monotonic_ms "$proof")
 current_pet=$(number last_pet_monotonic_ms "$state/last-ack.json")
 case "$keeper_sequence:$keeper_deadline:$current_pet" in *[!0-9:]*|:*|*:) owner_refusal keeper-malformed 28; exit 28;; esac
 [ "$keeper_phase" = "$phase" ] && [ "$keeper_sequence" = "$sequence" ] &&
  grep -Fq '\"nonce\":\"'"$token"'\"' "$proof" &&
  [ "$((keeper_deadline-current_pet))" -ge 2500 ] || { owner_refusal keeper-stale-or-different-phase 28; exit 28; }
 printf 'OMF367_KEEPER_VERIFIED phase=%s sequence=%s freshness_ms_at_least=2500\\n' "$phase" "$sequence";;''')
 s=once(s,' request HEALTH ok || exit 24\n case "$phase" in',' request HEALTH ok || exit 24\n cp "$state/last-ack.json" "$state/.keeper-health.json"; mv "$state/.keeper-health.json" "$state/keeper-health.json"\n case "$phase" in')
 s=once(s,'in maintain|begin|purpose|complete)', 'in maintain|begin|purpose|complete|verify|require-keeper)')
 p.write_bytes(s.encode())
 p=DST/'usr/sbin/om-f367-keeper';s=p.read_text()
 s=once(s,'fail(){\n printf \'OMF367_HEALTH_FAIL reason=%s\\n\' "$1"','''emit(){ printf '%s\\n' "$*"; printf '%s\\n' "$*" >"${OM_F367_CONSOLE:-/dev/console}" 2>/dev/null || true; }
trap 'exit_rc=$?; if [ "$exit_rc" -ne 0 ] && [ ! -e "$state/stopping" ]; then emit "OMF367_KEEPER_EXIT exit_code=$exit_rc"; fi' EXIT
fail(){
 emit "OMF367_HEALTH_FAIL reason=$1"''')
 p.write_bytes(s.encode())
 p=DST/'usr/sbin/om-f367-control';s=p.read_text()
 s=once(s,' "$start" --f367-native-diagnostic || fail native-bootstrap',''' if "$start" --f367-native-diagnostic; then :; else
  native_rc=$?
  refusal=$(cat "${OM_RADIO5_STATE:-/run/openmitrastar/radio5g}/last-refusal" 2>/dev/null || true)
  case "$refusal" in ''|*[!A-Za-z0-9_.:-]*) refusal=unavailable;; esac
  printf 'OMF367_NATIVE_EXIT exit_code=%s refusal=%s\\n' "$native_rc" "$refusal"
  fail native-bootstrap
 fi''')
 p.write_bytes(s.encode())
 report={'schema':'openmitrastar.f367r2-runtime-source/v1','status':'PREPARED_FOR_FOCUSED_PREAMBLE_IPC_TEST','baseline':str(SRC),'revision':str(DST),'files':{p.relative_to(DST).as_posix():sha(p) for p in DST.rglob('*') if p.is_file()},'kernel_qdrv_provider_engine_supervisor_changed':False,'phase_budgets_ms':{'preamble':30000,'module-load':30000},'health_lease_ms':5000,'total_budget_ms':5400000,'cac_nop_changed':False,'hardware_actions':False}
 (DST.parent/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'revision':str(DST),'changed':[n for n,h in report['files'].items() if sha(SRC/n)!=h]}))
if __name__=='__main__':main()
