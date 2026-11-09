"""Prepare the F335 WPS overlay from exact F321; no device or firmware actions."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'versions/f335-wps-control'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound'
BASE='openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
FILES=('usr/sbin/om-radio-start','usr/sbin/om-radio5-start','usr/libexec/openmitrastar/om-api-v1','usr/sbin/om-rtlctl')
def digest(data):return hashlib.sha256(data).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def load_baseline():
    image=PRIVATE/(BASE+'.rootfs.squashfs')
    require(digest(image.read_bytes())=='75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e','F321 rootfs drift')
    inventory=json.loads((PRIVATE/'rootfs-inventory.json').read_text())['after']
    for name in FILES:
        path=DEST/'baseline'/name
        if path.exists():require(digest(path.read_bytes())==inventory[name]['sha256'],'existing baseline drift');continue
        p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','unsquashfs','-cat',linux(image),name],capture_output=True,check=True)
        require(digest(p.stdout)==inventory[name]['sha256'],'rootfs extraction mismatch '+name)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(p.stdout)
    return {name:digest((DEST/'baseline'/name).read_bytes()) for name in FILES}

def patch_radio2(source):
    text=source.decode();anchor='chmod 0600 "$state/hostapd.conf"\nunset PSK'
    require(text.count(anchor)==1,'radio2 config anchor drift')
    text=text.replace(anchor,'chmod 0600 "$state/hostapd.conf"\n/usr/sbin/om-wpsctl 2g config >>"$state/hostapd.conf" || refuse wps-config\nunset PSK',1)
    anchor='"$hostapd" -f "$state/hostapd.log" "$state/hostapd.conf"'
    require(text.count(anchor)==1,'radio2 foreground launch drift')
    return text.replace(anchor,'"$hostapd" -q -f "$state/hostapd.log" "$state/hostapd.conf"',1).encode()

def patch_radio5(source):
    text=source.decode();anchor='chmod 0600 "$conf"'
    require(text.count(anchor)==2,'radio5 dry/real config anchors drift')
    text=text.replace(anchor,anchor+'\n/usr/sbin/om-wpsctl 5g config >>"$conf" || refuse wps-config')
    anchor='/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &'
    require(text.count(anchor)==1,'radio5 foreground launch drift')
    # RX ctrl_iface logs PIN at DEBUG; NEW_AP_SETTINGS carries credentials at
    # INFO when processing is disabled. WARNING-level keeps both out of files.
    return text.replace(anchor,'/usr/sbin/hostapd-qtn -q -f "$state/hostapd.log" "$conf" &',1).encode()

WPS_FUNCTION=r'''
run_wps_control()
{
 wps_band=$1; wps_action=$2
 wps_helper=${OM_WPSCTL:-/usr/sbin/om-wpsctl}
 [ -x "$wps_helper" ] || { error_json '503 Service Unavailable' wps-unavailable; exit 0; }
 if [ "$wps_action" = status ]; then
  require_read
  wps_result=$("$wps_helper" "$wps_band" status 2>/dev/null); wps_rc=$?
 else
  [ "$method" = POST ] || { error_json '405 Method Not Allowed' method; exit 0; }
  require_mutation
  wps_length=${CONTENT_LENGTH:-0}
  case "$wps_length" in ''|*[!0-9]*) error_json '400 Bad Request' invalid-body; exit 0 ;; esac
  if [ "$wps_action" = pin ] || [ "$wps_action" = ap-pin ]; then
   case "${CONTENT_TYPE:-}" in application/x-www-form-urlencoded*) ;; *) error_json '415 Unsupported Media Type' content-type; exit 0 ;; esac
   case "$wps_length" in 8|12) ;; *) error_json '400 Bad Request' invalid-pin; exit 0 ;; esac
   wps_body=$(dd bs=1 count="$wps_length" 2>/dev/null)
   [ "${#wps_body}" = "$wps_length" ] || { error_json '400 Bad Request' invalid-body; exit 0; }
   case "$wps_body" in pin=*) wps_pin=${wps_body#pin=} ;; *) error_json '400 Bad Request' invalid-pin; exit 0 ;; esac
   case "$wps_pin" in ''|*[!0-9]*) unset wps_body wps_pin; error_json '400 Bad Request' invalid-pin; exit 0 ;; esac
   wps_result=$(printf '%s' "$wps_pin" | "$wps_helper" "$wps_band" "$wps_action" 2>/dev/null); wps_rc=$?
   unset wps_body wps_pin
  else
   [ "$wps_length" = 0 ] || { error_json '400 Bad Request' invalid-body; exit 0; }
   wps_result=$("$wps_helper" "$wps_band" "$wps_action" 2>/dev/null); wps_rc=$?
  fi
 fi
 case "$wps_rc" in
  0) ;;
  2) error_json '400 Bad Request' wps-input-or-feature; exit 0 ;;
  3) error_json '409 Conflict' wps-busy-or-unavailable; exit 0 ;;
  *) error_json '503 Service Unavailable' wps-control-failed; exit 0 ;;
 esac
 printf '%s\n' "$wps_result" | grep -Fq '"schema":"lyoko.radio.wps/v1"' || { error_json '502 Bad Gateway' wps-contract; exit 0; }
 headers; printf '%s\n' "$wps_result"
}
'''
WPS_CASE=r'''radios/2g/wps|radios/5g/wps)
 wps_band=${endpoint#radios/}; wps_band=${wps_band%/wps}
 run_wps_control "$wps_band" status
 ;;
radios/2g/wps/pbc|radios/5g/wps/pbc|radios/2g/wps/cancel|radios/5g/wps/cancel|radios/2g/wps/pin|radios/5g/wps/pin|radios/2g/wps/ap-pin|radios/5g/wps/ap-pin|radios/2g/wps/ap-pin-disable|radios/5g/wps/ap-pin-disable)
 wps_path=${endpoint#radios/}; wps_band=${wps_path%%/*}; wps_action=${endpoint##*/}
 run_wps_control "$wps_band" "$wps_action"
 ;;
'''
def patch_api(source):
    text=source.decode();anchor="session_valid || { error_json '403 Forbidden' auth; exit 0; }\n\ncase \"$endpoint\" in\n"
    require(text.count(anchor)==1,'authenticated dispatch anchor drift')
    return text.replace(anchor,WPS_FUNCTION+'\n'+anchor+WPS_CASE,1).encode()

def build_overlay():
    baseline=load_baseline();overlay=DEST/'overlay'
    for name,patch in [('usr/sbin/om-radio-start',patch_radio2),('usr/sbin/om-radio5-start',patch_radio5),('usr/libexec/openmitrastar/om-api-v1',patch_api)]:
        target=overlay/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(patch((DEST/'baseline'/name).read_bytes()))
    flag=overlay/'etc/openmitrastar/features/wps-v1';flag.parent.mkdir(parents=True,exist_ok=True);flag.write_bytes(b'OPENMITRASTAR_WPS=1\n')
    manifest={'schema':'openmitrastar.f335-wps-overlay-preparation/v1','baseline':baseline,
              'physical_actions':False,'firmware_created':False,'pbc_automatically_started':False,
              'credentials':'preserved; received WPS AP credentials are not applied',
              'catalogue_refresh_required':['usr/sbin/om-radio5-start'],
              'integration':'Apply these additive transforms to the selected composed candidate; do not replace newer F332/F334 runtime changes with baseline copies',
              'files':{str(p.relative_to(overlay)):digest(p.read_bytes()) for p in overlay.rglob('*') if p.is_file()}}
    (DEST/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest
if __name__=='__main__':print(json.dumps(build_overlay(),indent=2))
