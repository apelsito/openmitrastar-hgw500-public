"""F366 transformations of the actual F365 ladder and qualified F341 helpers."""
from pathlib import Path
import hashlib,re
ROOT=Path(__file__).resolve().parents[1]
VERSION='lyoko-foundation-6.10.2-f366-native-dfs-diagnostic'
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('F366 anchor ambiguous '+repr(a[:100]))
 return s.replace(a,b,1)
def native_start(source:bytes,base_qdrv_sha:str,new_qdrv_sha:str)->bytes:
 s=source.decode('ascii')
 s=once(s,'# Exact direct-EMAC/symbol-provider dependency order proven live on 2026-08-20.',
  '# Live ARM/phase acknowledgement is mandatory before any native radio load.\n/usr/sbin/om-f366-stage verify module-load || refuse f366-watchdog-not-protecting-module-load\n# Exact direct-EMAC/symbol-provider dependency order proven live on 2026-08-20.')
 s=once(s,'for dirty in qdrv wlan temp_sensor switch_emac switch_tqe hbm fwt_ctrl; do',
            'for dirty in qdrv qtn_radar_f366 wlan temp_sensor switch_emac switch_tqe hbm fwt_ctrl; do')
 s=once(s,'expected_qdrv_sha='+base_qdrv_sha+'\n','expected_qdrv_sha='+new_qdrv_sha+'\n')
 # Retain the calibrated normal F365 profile and exact unchanged peer hashes.
 anchor='[ "$(sha256sum "$module_dir/qdrv.ko" 2>/dev/null | awk \'{ print $1 }\')" = "$expected_qdrv_sha" ] || refuse qdrv-contract'
 s=once(s,anchor,anchor+'\nexpected_radar_sha=$(value RADAR_F366_SHA256 "$contract")\n[ "$(sha256sum "$module_dir/qtn_radar_f366.ko" 2>/dev/null | awk \'{ print $1 }\')" = "$expected_radar_sha" ] || refuse f366-provider-contract')
 provider='''load_module wlan.ko
load_module qtn_radar_f366.ko hardware_enable=1 diagnostic_capture=1 authoritative_enable=0
grep -qx 'hardware_dirty=0' /proc/openmitrastar_radar_f366/status || refuse f366-dirty-before-qdrv
grep -qx 'callbacks=0' /proc/openmitrastar_radar_f366/status || refuse f366-callback-before-qdrv
/usr/sbin/om-radar-engine-f366 --serve >/run/openmitrastar/f366/engine.log 2>&1 &
printf '%s\n' "$!" >/run/openmitrastar/f366/engine.pid
f366_wait=0
while [ "$f366_wait" -lt 5 ]; do
 grep -qx 'ipc_state=1' /proc/openmitrastar_radar_f366/status && break
 f366_wait=$((f366_wait+1)); sleep 1
done
grep -qx 'ipc_state=1' /proc/openmitrastar_radar_f366/status || refuse f366-service-not-attached
'''
 s=once(s,'load_module wlan.ko\n',provider)
 s=once(s,'control_set start core-start','/usr/sbin/om-f366-stage complete module-load || refuse f366-wdt-module-complete\n/usr/sbin/om-f366-stage begin core-start 30000 || refuse f366-wdt-core-begin\ncontrol_set start core-start')
 s=once(s,'control_set_vap_create "$mac"','/usr/sbin/om-f366-stage complete core-start || refuse f366-wdt-core-complete\n/usr/sbin/om-f366-stage begin vap-create 30000 || refuse f366-wdt-vap-begin\ncontrol_set_vap_create "$mac"')
 s=once(s,'load_module wlan_scan_ap.ko','/usr/sbin/om-f366-stage complete vap-create || refuse f366-wdt-vap-complete\n/usr/sbin/om-f366-stage begin radio-nondfs 45000 || refuse f366-wdt-radio-begin\nload_module wlan_scan_ap.ko')
 match=re.search(r'\(\n\tsleep \d+\n\t\[ -e "\$state/commit" \]',s)
 if not match:raise ValueError('F365 rollback timer missing')
 end=s.index("log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'",match.start())+len("log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'")
 s=s[:match.start()]+'# F366 recovery belongs exclusively to the armed watchdog owner.'+s[end:]
 marker='log "OMRADIO5_READY '
 if s.count(marker)!=1:raise ValueError('ready marker ambiguous')
 checks="grep -qx 'callbacks=0' /proc/openmitrastar_radar_f366/status || refuse f366-callback-after-start\ngrep -qx 'channel=36' /proc/openmitrastar_radar_f366/status || refuse f366-channel-after-start\n/usr/sbin/om-f366-stage complete radio-nondfs || refuse f366-wdt-radio-complete\n"
 s=s.replace(marker,checks+marker,1)
 if 'authoritative_enable=0' not in s or 'channel=36' not in s or 'OMRADIO5_ROLLBACK_ARMED' in s:raise ValueError('F366 diagnostic boundary missing')
 return s.encode('ascii')
def overlay():
 donor=ROOT/'versions/lyoko-foundation-6.10.1-f341-native-diagnostic/overlay'
 result={p.relative_to(donor).as_posix().replace('f341','f366'):p.read_bytes().replace(b'F341',b'F366').replace(b'f341',b'f366').replace(b'USER_DEFERRED',b'UNRUN') for p in donor.rglob('*') if p.is_file()}
 key='usr/sbin/om-f366-status'
 # Module/proc identity is F366; unchanged GPL telemetry retains its F341 ABI.
 result[key]=result[key].replace(b"schema=openmitrastar.f366-provider/v1",b"schema=openmitrastar.f341-provider/v1")
 key='usr/sbin/om-f366-diagnostic';s=result[key].decode()
 s=once(s,'case "${1:-status}" in','''failure_snapshot()
{
 code=$1
 printf 'OMF366_ERROR reason=%s hardware_quiesced=0 reboot_required=1\n' "$code"
 if [ -r "$provider/status" ]; then
  snapshot=$("$status" 2>/dev/null || true)
  [ -z "$snapshot" ] || printf 'OMF366_FAILURE_STATUS json=%s\n' "$snapshot"
 fi
 "$stage" cease || true
}
case "${1:-status}" in''')
 s=once(s,'if ! "$start" --f366-native-diagnostic; then\n "$stage" cease || true',
  'if ! "$start" --f366-native-diagnostic; then\n failure_snapshot native-start-failed')
 s=s.replace('"$stage" cease || true; exit ', 'failure_snapshot observation-failed; exit ')
 s=once(s,' "$status" >"$state/status-$i.json" || { failure_snapshot observation-failed; exit 50; }',
  ' "$status" >"$state/status-$i.json" || { failure_snapshot status-read-failed; exit 50; }\n printf \'OMF366_STATUS index=%s json=%s\\n\' "$i" "$(cat "$state/status-$i.json")"')
 s=once(s,'"$stage" begin pipeline-observe 30000 || exit 49','"$stage" begin pipeline-observe 30000 || { failure_snapshot observe-phase-failed; exit 49; }')
 s=once(s,'"$stage" complete pipeline-observe || exit 54','"$stage" complete pipeline-observe || { failure_snapshot observe-complete-failed; exit 54; }')
 result[key]=s.encode()
 return result
