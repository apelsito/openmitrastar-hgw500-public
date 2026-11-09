"""Pure F341 runtime transformations, pinned to the existing native ladder."""
from pathlib import PurePosixPath
import hashlib,re
import f334_shadow_contract as old
PRODUCT_VERSION='lyoko-foundation-6.10.1-f341-native-diagnostic'
MODULE_DIR=old.MODULE_DIR
def sha(content):return hashlib.sha256(content).hexdigest()
def once(source,anchor,replacement):
 if source.count(anchor)!=1:raise ValueError('F341 anchor ambiguous '+repr(anchor[:80]))
 return source.replace(anchor,replacement,1)
def native_start(source:bytes)->bytes:
 old.pinned(source,old.DONOR_START,'native F315 ladder donor')
 s=source.decode('ascii')
 s=once(s,'# Exact direct-EMAC/symbol-provider dependency order proven live on 2026-08-20.',
  '# A direct invocation of this private ladder must also prove a live, armed\n# F340 phase before loading any qdrv dependency. HEALTH does not renew deadlines.\n/usr/sbin/om-f341-stage verify module-load || refuse f341-watchdog-not-protecting-module-load\n# Exact direct-EMAC/symbol-provider dependency order proven live on 2026-08-20.')
 s=s.replace('qtn_radar_shadow_f315','qtn_radar_f341').replace('openmitrastar_radar_f315','openmitrastar_radar_f341')
 s=s.replace('RADAR_SHADOW_SHA256','RADAR_F341_SHA256')
 s=once(s,'qdrv_profile=f315-radar-shadow\nexpected_qdrv_sha=$(value QDRV_SHA256 "$contract")',
  'qdrv_profile=f341-native-diagnostic\nexpected_qdrv_sha=$(value QDRV_SHA256 "$contract")\nexpected_wlan_sha=$(value WLAN_SHA256 "$contract")\nexpected_board_compat_sha=$(value BOARD_COMPAT_SHA256 "$contract")\nexpected_switch_emac_sha=$(value SWITCH_EMAC_SHA256 "$contract")')
 begin=s.index('load_module qtn_radar_f341.ko')
 end=s.index('if [ "$beacon_v89_wire_enable" = 1 ]; then',begin)
 provider='''load_module qtn_radar_f341.ko hardware_enable=1 diagnostic_capture=1 authoritative_enable=0
grep -qx 'hardware_dirty=0' /proc/openmitrastar_radar_f341/status || refuse f341-dirty-before-qdrv
grep -qx 'callbacks=0' /proc/openmitrastar_radar_f341/status || refuse f341-callback-before-qdrv
/usr/sbin/om-radar-engine-f341 --serve >/run/openmitrastar/f341/engine.log 2>&1 &
printf '%s\\n' "$!" >/run/openmitrastar/f341/engine.pid
f341_wait=0
while [ "$f341_wait" -lt 5 ]; do
 grep -qx 'ipc_state=1' /proc/openmitrastar_radar_f341/status && break
 f341_wait=$((f341_wait+1)); sleep 1
done
grep -qx 'ipc_state=1' /proc/openmitrastar_radar_f341/status || refuse f341-service-not-attached
'''
 s=s[:begin]+provider+s[end:]
 s=once(s,'control_set start core-start','/usr/sbin/om-f341-stage complete module-load || refuse f341-wdt-module-complete\n/usr/sbin/om-f341-stage begin core-start 30000 || refuse f341-wdt-core-begin\ncontrol_set start core-start')
 s=once(s,'control_set_vap_create "$mac"','/usr/sbin/om-f341-stage complete core-start || refuse f341-wdt-core-complete\n/usr/sbin/om-f341-stage begin vap-create 30000 || refuse f341-wdt-vap-begin\ncontrol_set_vap_create "$mac"')
 s=once(s,'load_module wlan_scan_ap.ko','/usr/sbin/om-f341-stage complete vap-create || refuse f341-wdt-vap-complete\n/usr/sbin/om-f341-stage begin radio-nondfs 45000 || refuse f341-wdt-radio-begin\nload_module wlan_scan_ap.ko')
 begin=s.index('[ -w /sys/module/qtn_radar_f341/parameters/shadow_arm ]')
 end=s.index('log "OMRADIO5_READY ',begin)
 s=s[:begin]+'''grep -qx 'callbacks=0' /proc/openmitrastar_radar_f341/status || refuse f341-callback-after-start
grep -qx 'channel=36' /proc/openmitrastar_radar_f341/status || refuse f341-channel-after-start
/usr/sbin/om-f341-stage complete radio-nondfs || refuse f341-wdt-radio-complete
'''+s[end:]
 # The original normal AP fallback is not a substitute for the hardware
 # watchdog phase budget. In this diagnostic ladder it must not run a
 # competing asynchronous teardown of qdrv while acquisition is dirty.
 begin=s.index('(\n\tsleep 25\n') if '(\n\tsleep 25\n' in s else -1
 if begin<0:
  match=re.search(r'\(\n\tsleep \d+\n\t\[ -e "\$state/commit" \]',s)
  if not match:raise ValueError('original rollback timer anchor missing')
  begin=match.start()
 end=s.index("log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'",begin)+len("log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'")
 s=s[:begin]+'# F341 rollback is the armed hardware watchdog owner, not this old shell timer.'+s[end:]
 if 'shadow_arm' in s or 'sample_limit=18' in s:raise ValueError('old acquisition controls survived F341 transform')
 if 'channel=36' not in s or 'qtn-dfs-control-v1' not in s:raise ValueError('non-DFS enforcement lost')
 return s.encode('ascii')
def driver_contract(source:bytes,module_hashes:dict[str,str])->bytes:
 old.pinned(source,old.SOURCE_DRIVER_CONTRACT,'F321 driver contract')
 mapping={'QDRV_SHA256':'qdrv','WLAN_SHA256':'wlan','BOARD_COMPAT_SHA256':'board_compat','SWITCH_EMAC_SHA256':'switch_emac','SWITCH_TQE_SHA256':'switch_tqe'}
 lines=source.decode('ascii').splitlines();seen=set();out=[]
 for line in lines:
  key=line.split('=',1)[0]
  if key in mapping:
   if key in seen:raise ValueError('duplicate driver binding')
   seen.add(key);line=key+'='+module_hashes[mapping[key]]
  out.append(line)
 if seen!=set(mapping):raise ValueError('missing driver binding')
 out.append('RADAR_F341_SHA256='+module_hashes['qtn_radar_f341'])
 return ('\n'.join(out)+'\n').encode('ascii')
def catalog(source:bytes,changes:dict[str,bytes])->bytes:
 entries=old.parse_artifact_catalog(source)
 for path,data in changes.items():
  if path==old.ARTIFACTS_PATH:raise ValueError('catalog cannot hash itself')
  if str(PurePosixPath(path))!=path or path.startswith('/') or '..' in PurePosixPath(path).parts:raise ValueError('unsafe catalog path')
  entries[path]=sha(data)
 return ''.join(f'{digest}  /{path}\n' for path,digest in sorted(entries.items())).encode('ascii')
