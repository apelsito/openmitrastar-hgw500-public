"""Versioned F344 bootstrap transformation; it never runs the resulting loader."""
import hashlib
from f341_runtime_contract import once
from f334_shadow_contract import DONOR_START

def native_start(source: bytes) -> bytes:
 if hashlib.sha256(source).hexdigest()!=DONOR_START:
  raise ValueError('F344 native ladder donor changed')
 s=source.decode('ascii').replace('qtn_radar_shadow_f315','qtn_radar_f338').replace('RADAR_SHADOW_SHA256','RADAR_F338_SHA256')
 s=once(s,'umask 077','''umask 077
# An uninstalled component bundle is not a radio activation. A future,
# explicitly selected image profile must enable this versioned feature.
f344_feature=$(cat /etc/openmitrastar/features/qtn-f344-managed-modes-v1 2>/dev/null || true)
[ "$f344_feature" = OPENMITRASTAR_F344_MANAGED_MODES=1 ] || exit 78''')
 s=once(s,'qdrv_profile=f315-radar-shadow\nexpected_qdrv_sha=$(value QDRV_SHA256 "$contract")',
  'qdrv_profile=f344-managed-modes\nexpected_qdrv_sha=$(value QDRV_SHA256 "$contract")\nexpected_wlan_sha=$(value WLAN_SHA256 "$contract")\nexpected_board_compat_sha=$(value BOARD_COMPAT_SHA256 "$contract")\nexpected_switch_emac_sha=$(value SWITCH_EMAC_SHA256 "$contract")')
 begin=s.index('load_module qtn_radar_f338.ko');end=s.index('if [ "$beacon_v89_wire_enable" = 1 ]; then',begin)
 s=s[:begin]+'''# F344 modes use the real radar ABI but never open acquisition hardware.
load_module qtn_radar_f338.ko hardware_enable=0 diagnostic_capture=0 authoritative_enable=0
grep -qx 'hardware_enabled=0' /proc/openmitrastar_radar_f338/status || refuse f344-acquisition-enabled
grep -qx 'hardware_dirty=0' /proc/openmitrastar_radar_f338/status || refuse f344-acquisition-dirty
grep -qx 'callbacks=0' /proc/openmitrastar_radar_f338/status || refuse f344-radar-callback
'''+s[end:]
 anchor='openmitrastar_sequential_bringup=1 openmitrastar_single_vap_create=0'
 if s.count(anchor)!=3:raise ValueError('F344 qdrv profile branches changed')
 s=s.replace(anchor,anchor+' openmitrastar_mode_workflow=1')
 s=once(s,'load_module wlan_scan_ap.ko','load_module wlan_scan_ap.ko\nload_module wlan_scan_sta.ko')
 s=once(s,'/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &',
  '/usr/sbin/om-f344-mode --launch-ap "$conf" >"$state/hostapd.log" 2>&1 &')
 s=once(s,'touch "$state/commit"','/usr/sbin/om-f344-mode --confirm-bootstrap || refuse f344-private-bootstrap-unverified\ntouch "$state/commit"')
 begin=s.index('[ -w /sys/module/qtn_radar_f338/parameters/shadow_arm ]');end=s.index('log "OMRADIO5_READY ',begin)
 s=s[:begin]+'''grep -qx 'hardware_enabled=0' /proc/openmitrastar_radar_f338/status || refuse f344-acquisition-enabled-after-start
grep -qx 'callbacks=0' /proc/openmitrastar_radar_f338/status || refuse f344-callback-after-start
'''+s[end:]
 if 'shadow_arm' in s or 'om-radar-engine' in s or 'hardware_enable=1' in s:raise ValueError('F344 acquisition activation survived')
 return s.encode('ascii')

def driver_contract(source: bytes, modules: dict) -> bytes:
 mapping={'QDRV_SHA256':'qdrv','WLAN_SHA256':'wlan','BOARD_COMPAT_SHA256':'board_compat','SWITCH_EMAC_SHA256':'switch_emac','SWITCH_TQE_SHA256':'switch_tqe'}
 seen=set();out=[]
 for line in source.decode('ascii').splitlines():
  key=line.split('=',1)[0]
  if key in mapping:
   if key in seen:raise ValueError('duplicate driver contract key')
   seen.add(key);line=key+'='+modules[mapping[key]]['sha256']
  if key not in ('RADAR_SHADOW_SHA256','RADAR_F341_SHA256','RADAR_F338_SHA256'):out.append(line)
 if seen!=set(mapping):raise ValueError('incomplete driver contract')
 out.append('RADAR_F338_SHA256='+modules['qtn_radar_f338']['sha256'])
 return ('\n'.join(out)+'\n').encode('ascii')
