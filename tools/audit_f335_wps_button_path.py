"""Offline source and exact-F321 artifact evidence for the existing WPS path.

Does not synthesize a button event, open sysfs, launch WPS, or access the HGW.
String presence is not represented as proof of executed machine-code behavior.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound'


def main():
    sources = {
        'qdrv': ROOT/'work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c',
        'madwifi': ROOT/'work/sources/Quantenna-GPL/buildroot/package/zhostapd/hostapd-git/src/drivers/driver_madwifi.c',
        'wps': ROOT/'work/sources/Quantenna-GPL/buildroot/package/zhostapd/hostapd-git/src/ap/wps_hostapd.c',
        'config': ROOT/'work/mission-state/w3-offline/hostapd-qtn-madwifi-v4.config',
        'artifact': ROOT/'outputs/kernel-port/qtn-hostapd-madwifi-v6-isolated-raw-20260830/hostapd',
        'inventory': PRIVATE/'rootfs-inventory.json',
    }
    raw = {k: p.read_bytes() for k, p in sources.items()}
    record = json.loads(raw['inventory'])['after']['usr/sbin/hostapd-qtn']
    checks = {
        'qdrv_release_event': b'qdrv_eventf(dev, "WPS-BUTTON.indication");' in raw['qdrv'],
        'qdrv_long_press_distinct': b'WPS_BUTTON_DBGDUMP_EVENT' in raw['qdrv'],
        'madwifi_direct_wps_dispatch': b'os_strncmp(custom, "WPS-BUTTON.indication", 21) == 0) {\n\t\thostapd_wps_button_pushed(hapd, NULL);' in raw['madwifi'].replace(b'\r\n', b'\n'),
        'wps_entrypoint_exists': b'int hostapd_wps_button_pushed(' in raw['wps'],
        'compiled_profile_wps': b'CONFIG_WPS=y' in raw['config'],
        'compiled_profile_madwifi': b'CONFIG_DRIVER_MADWIFI=y' in raw['config'],
        'exact_f321_hostapd_hash': hashlib.sha256(raw['artifact']).hexdigest() == record['sha256'],
        'exact_f321_hostapd_size': len(raw['artifact']) == record['bytes'],
        'exact_f321_event_string_present': b'WPS-BUTTON.indication\0' in raw['artifact'],
    }
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/preflight'/('f335-wps-button-path-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    result = {
        'schema': 'openmitrastar.f335-wps-button-path/v1',
        'status': 'PASS_OFFLINE_EXISTING_EVENT_PATH' if all(checks.values()) else 'FAIL_OFFLINE_EVENT_PATH',
        'checks': checks, 'hardware_actions': False,
        'source_call_path': 'GPIO4 release -> qdrv WEXT event -> madwifi custom event -> hostapd_wps_button_pushed',
        'implementation_decision': 'Reuse the existing WEXT path; do not add a second sysfs consumer that starts PBC for the same event.',
        'physical_button_dispatch_proven': False,
        'enrollment_proven': False,
        'binary_source_equivalence_fully_proven': False,
        'limitations': 'The exact F321 binary hash and event string are verified; source call-path inspection does not prove a physical button event or enrollment.',
        'sources': {str(p): {'bytes': len(raw[k]), 'sha256': hashlib.sha256(raw[k]).hexdigest()} for k, p in sources.items()},
    }
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'result': str(out/'result.json'), 'status': result['status'], 'checks': checks}, indent=2))
    return int(not all(checks.values()))


if __name__ == '__main__':
    raise SystemExit(main())
