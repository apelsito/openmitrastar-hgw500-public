"""Pinned, bounded transformations for the F325 shadow-only image."""
from __future__ import annotations

import hashlib
import re


SOURCE_CANDIDATE = "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18"
SOURCE_ROOTFS = "75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e"
SOURCE_API = "849ffe6a503d3be2a3083116dcafb6a6c4adf32f7eeee4a727bf64391caa1b09"
SOURCE_START = "02df465d171abc459531f861f0833466b3a4d56a18cb078c735bb42fe1b0f35c"
DONOR_START = "55ce25f5c7703827349ea213aff78134789928228c55145b178bf56d7df87669"
SOURCE_RELEASE = "1959de970aecee799b8fe4fa67457d53d25e9e30868c323a307e77e452f81fa1"
SOURCE_ARTIFACTS = "9e0d3fad02b98aaf5f8dcbccb4167f94930a061430b2acfe5cf6c89d270528c8"
SOURCE_DRIVER_CONTRACT = "15240438774c25e534a2a302b49d4273f72885086aa61953e4ab72f705cdb5b8"
QDRV_SHA256 = "1dda1a7c7e86bc6391dc113f45d7a3372fcb36894f0a7202abf82688076c35b0"
PROVIDER_SHA256 = "a59f3ae86b1ced8bf330f2748f42d4508017f1284bce77ad69151bf47b8bb13c"
MODULE_DIR = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g"
QDRV_PATH = MODULE_DIR + "/qdrv.ko"
PROVIDER_PATH = MODULE_DIR + "/qtn_radar_shadow_f315.ko"
API_PATH = "usr/libexec/openmitrastar/om-api-v1"
START_PATH = "usr/sbin/om-radio5-start"
RELEASE_PATH = "etc/openmitrastar/release"
ARTIFACTS_PATH = "usr/share/openmitrastar/radio5g/artifacts.sha256"
DRIVER_CONTRACT_PATH = "usr/share/openmitrastar/radio5g/driver-contract.env"
PRODUCT_VERSION = "lyoko-foundation-6.9.3-f325-radar-once-f321-device"
UI_BUILD_ID = "72dd5d1877544af9"
UI_MANIFEST_SHA256 = "4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def pinned(content: bytes, expected: str, label: str) -> None:
    if digest(content) != expected:
        raise ValueError("F325 source drift: " + label)


def api_bytes(source: bytes) -> bytes:
    pinned(source, SOURCE_API, API_PATH)
    anchor = b"\nradios/2g|radios/5g)\n"
    if source.count(anchor) != 1 or b"\nradios/5g/dfs)\n" in source:
        raise ValueError("F325 API route anchor changed")
    branch = b'''\nradios/5g/dfs)
\trequire_read
\tradarctl=${OM_RADARCTL:-/usr/sbin/om-radarctl}
\t[ -x "$radarctl" ] || { error_json '503 Service Unavailable' radar-contract; exit 0; }
\tresult=$(sh "$radarctl" status 2>/dev/null) || { error_json '503 Service Unavailable' radar-status; exit 0; }
\theaders; printf '%s\\n' "$result"
\t;;
'''
    return source.replace(anchor, branch + anchor, 1)


def start_bytes(source: bytes, donor: bytes) -> bytes:
    pinned(source, SOURCE_START, "F321 radio start")
    pinned(donor, DONOR_START, "sealed F315 radio start")
    begin = donor.index(b"[ -w /sys/module/qtn_radar_shadow_f315/parameters/shadow_arm ]")
    end = donor.index(b'log "OMRADIO5_READY ', begin)
    replacement = b'''# F325: the physical gate must explicitly arm acquisition after baseline checks.
grep -qx 'lifecycle=f325-single-boot-reset-required' /proc/openmitrastar_radar_f315/status || refuse radar-once-lifecycle-mismatch
grep -qx 'once_phase=0' /proc/openmitrastar_radar_f315/status || refuse radar-once-already-used
grep -qx 'hardware_dirty=0' /proc/openmitrastar_radar_f315/status || refuse radar-once-dirty-boot
grep -qx 'shadow_arm=0' /proc/openmitrastar_radar_f315/status || refuse radar-shadow-unexpected-arm
grep -qx 'configured=0' /proc/openmitrastar_radar_f315/status || refuse radar-shadow-unexpected-configuration
grep -qx 'callback_invocations=0' /proc/openmitrastar_radar_f315/status || refuse radar-shadow-unexpected-callback
log 'OMF325_RADAR_SHADOW_PENDING configured=0 authority=0 dfs_tx_authorized=0'
'''
    output = donor[:begin] + replacement + donor[end:]
    if b"shadow_enable=1 shadow_arm=0" not in output or b">/sys/module/qtn_radar_shadow_f315/parameters/shadow_arm" in output:
        raise ValueError("F325 must never auto-arm acquisition")
    return output


def release_bytes(source: bytes, build_id: str) -> bytes:
    pinned(source, SOURCE_RELEASE, RELEASE_PATH)
    if not re.fullmatch(r"[a-f0-9]{16}", build_id):
        raise ValueError("invalid F325 build identity")
    changes = {"OPENMITRASTAR_PRODUCT_VERSION": PRODUCT_VERSION, "OPENMITRASTAR_BUILD_ID": build_id}
    lines = source.decode("ascii").splitlines()
    output = [(line.split("=", 1)[0] + "=" + changes[line.split("=", 1)[0]]) if line.split("=", 1)[0] in changes else line for line in lines]
    return ("\n".join(output) + "\n").encode("ascii")


def artifacts_bytes(source: bytes) -> bytes:
    pinned(source, SOURCE_ARTIFACTS, ARTIFACTS_PATH)
    lines = source.decode("ascii").splitlines()
    hits = [index for index, line in enumerate(lines) if line.endswith("  /" + QDRV_PATH)]
    if len(hits) != 1 or any(PROVIDER_PATH in line for line in lines):
        raise ValueError("unexpected radio artifact catalogue")
    lines[hits[0]] = QDRV_SHA256 + "  /" + QDRV_PATH
    lines.append(PROVIDER_SHA256 + "  /" + PROVIDER_PATH)
    return ("\n".join(lines) + "\n").encode("ascii")


def driver_contract_bytes(source: bytes) -> bytes:
    pinned(source, SOURCE_DRIVER_CONTRACT, DRIVER_CONTRACT_PATH)
    lines = source.decode("ascii").splitlines()
    hits = [index for index, line in enumerate(lines) if line.startswith("QDRV_SHA256=")]
    if len(hits) != 1 or any(line.startswith("RADAR_SHADOW_SHA256=") for line in lines):
        raise ValueError("unexpected radio driver contract")
    lines[hits[0]] = "QDRV_SHA256=" + QDRV_SHA256
    lines.append("RADAR_SHADOW_SHA256=" + PROVIDER_SHA256)
    return ("\n".join(lines) + "\n").encode("ascii")


def radio_control_bytes(source: bytes) -> bytes:
    pinned(source, "b681610c554298fe65a3e66bede17739f965201b8cd0e454c137d9cd323d3d11", "F321 radio control")
    anchor = b"#!/bin/ash\n"
    guard = b'''# F325 diagnostics retain the boot profile until full recovery.
case "${1:-}" in
stage_config|apply_config|rollback_config|commit_config|restart_radio)
    printf '%s\\n' '{"ok":false,"schema":"lyoko.radio.control-error/v1","error":"f325-diagnostic-profile-locked-reboot-required"}'
    exit 3
    ;;
esac
'''
    if not source.startswith(anchor):
        raise ValueError("unexpected radio control interpreter")
    return anchor + guard + source[len(anchor):]


def radio_stop_bytes(source: bytes) -> bytes:
    pinned(source, "26d34dc42c55348003dc90baed35c6c50d5ad628ed6dd4217b8b9fd3097c5207", "F321 radio stop")
    anchor = b"#!/bin/ash\n"
    guard = b'''# F325 must not report a radio stop as acquisition-hardware restoration.
if grep -qx 'hardware_dirty=1' /proc/openmitrastar_radar_f315/status 2>/dev/null; then
    printf '%s\\n' 'F325_REBOOT_REQUIRED: capture configuration is retained' >&2
    exit 3
fi
'''
    if not source.startswith(anchor):
        raise ValueError("unexpected radio stop interpreter")
    return anchor + guard + source[len(anchor):]
