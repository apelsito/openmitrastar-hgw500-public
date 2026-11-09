#!/usr/bin/env python3
"""Build F137 from F136 by rearming wifi0 after hostapd and observing post-CoC."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f136_5g_defer_post_hostapd_visibility_from_f133 as f136
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f137-5g-post-hostapd-rearm-from-f136"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F137_FROM_F136_5G_POST_HOSTAPD_REARM_OBSERVE"

SRC_BUILD = f136.OUT
SRC_BASE = f136.BASE_OUT
START_ENTRY = f136.START_ENTRY
HASHES_ENTRY = f136.HASHES_ENTRY
PAD_ENTRY = f136.PAD_ENTRY

OLD_START_SHA = "b97ae29ebf5d24ba78b5abe5bba817116ba830c7e4a918035c7d9e6514448d2d"

OLD_POST_HOSTAPD_GATE = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
observe_radio5_visibility_state post-hostapd continue-to-coc
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""

NEW_POST_HOSTAPD_GATE = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
printf '1\\n' >"$rf" || refuse post-hostapd-rf-open
[ "$(cat "$rf")" = 1 ] || refuse post-hostapd-rf-readback
ifconfig wifi0 up || refuse post-hostapd-wifi0-up
/usr/sbin/iwconfig-qtn wifi0 essid "$ssid" >/dev/null || refuse post-hostapd-ssid-refresh
/usr/sbin/iwconfig-qtn wifi0 channel 36 >/dev/null || refuse post-hostapd-channel-refresh
/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/post-hostapd-init-txpower.log" 2>&1 || refuse post-hostapd-txpower-init
sleep 2
log "OMRADIO5_POST_HOSTAPD_REARM flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || true) carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || true) rf=$(cat "$rf" 2>/dev/null || true) action=visibility-observe source=f137"
observe_radio5_visibility_state post-hostapd continue-to-coc
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""

OLD_POST_COC_GATE = """[ "$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping)" = PONG ] || refuse hostapd-pong-after-coc
require_radio5_visibility_state post-coc
[ -e /sys/class/net/br0/brif/eth0 ] || refuse management-lost-after-coc
"""

NEW_POST_COC_GATE = """[ "$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping)" = PONG ] || refuse hostapd-pong-after-coc
printf '1\\n' >"$rf" || refuse post-coc-rf-open
ifconfig wifi0 up >/dev/null 2>&1 || log "OMRADIO5_POST_COC_UP_FAILED flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || true) carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || true) source=f137"
sleep 2
log "OMRADIO5_POST_COC_REARM flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || true) carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || true) rf=$(cat "$rf" 2>/dev/null || true) action=visibility-observe source=f137"
observe_radio5_visibility_state post-coc continue-carrier-probe
[ -e /sys/class/net/br0/brif/eth0 ] || refuse management-lost-after-coc
"""

OLD_CARRIER_PENDING_BLOCK = """elif [ "$qdrv_profile" = product-v6 ]; then
\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-carrier-pending
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ] || refuse wifi0-not-up-after-carrier-pending
\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-after-carrier-pending
\tled_gate=carrier-pending-skip
"""

NEW_CARRIER_PENDING_BLOCK = """elif [ "$qdrv_profile" = product-v6 ]; then
\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-carrier-pending
\tif [ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ]; then
\t\twifi0_up=1
\telse
\t\twifi0_up=0
\tfi
\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-after-carrier-pending
\tlog "OMRADIO5_CARRIER_PENDING_OBSERVE flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || true) carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || true) operstate=$(cat /sys/class/net/wifi0/operstate 2>/dev/null || true) wifi0_up=$wifi0_up source=f137"
\tled_gate=carrier-pending-skip
"""

OLD_VISIBILITY_PROBE_EXIT = """if [ "$qdrv_profile" = product-v6 ] && [ "${product_v6_carrier_gate:-0}" != 1 ]; then
\tprintf 'carrier-pending\\n' >"$state/state"
\tlog "OMRADIO5_VISIBILITY_PROBE direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 ssid=$ssid region=ES channel=36 bw=80 security=$security_result psk=$psk_result tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile tx_trace=$tx_path_trace_enable fwt_ctrl=absent ioss=untouched led5g=$led_gate dmesg_marker=$led_marker_evidence carrier=pending association_policy=visibility-first-external-30s"
\texit 0
fi
"""

NEW_VISIBILITY_PROBE_EXIT = """if [ "$qdrv_profile" = product-v6 ] && [ "${product_v6_carrier_gate:-0}" != 1 ]; then
\tprintf 'carrier-pending\\n' >"$state/state"
\tcapture_assoc_window_snapshot carrier-pending-initial
\tstart_assoc_window_guard
\tlog "OMRADIO5_VISIBILITY_PROBE direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 ssid=$ssid region=ES channel=36 bw=80 security=$security_result psk=$psk_result tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile tx_trace=$tx_path_trace_enable fwt_ctrl=absent ioss=untouched led5g=$led_gate dmesg_marker=$led_marker_evidence carrier=pending association_policy=visibility-first-external-30s source=f137"
\texit 0
fi
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    actual = sha256(data)
    if actual != OLD_START_SHA:
        raise SystemExit(f"F137 start input hash mismatch: {actual}")
    text = data.decode("ascii")
    if "OMRADIO5_POST_HOSTAPD_REARM" in text:
        raise SystemExit("F137 start script already contains post-hostapd rearm marker")
    replacements = (
        (OLD_POST_HOSTAPD_GATE, NEW_POST_HOSTAPD_GATE, "post_hostapd_rearm"),
        (OLD_POST_COC_GATE, NEW_POST_COC_GATE, "post_coc_observe"),
        (OLD_CARRIER_PENDING_BLOCK, NEW_CARRIER_PENDING_BLOCK, "carrier_pending_observe"),
        (OLD_VISIBILITY_PROBE_EXIT, NEW_VISIBILITY_PROBE_EXIT, "carrier_pending_assoc_window"),
    )
    patched = text
    applied: list[str] = []
    for old, new, name in replacements:
        if old not in patched:
            raise SystemExit(f"F137 missing insertion point: {name}")
        patched = patched.replace(old, new, 1)
        applied.append(name)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_sha256": OLD_START_SHA,
        "new_sha256": sha256(patched_bytes),
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "applied": applied,
        "fixes": [
            "keeps F136 qdrv and post-hostapd Tx-Power observation",
            "reopens RF and raises wifi0 after hostapd before the visibility probe",
            "turns post-CoC Tx-Power:0 into an observation window instead of immediate rollback",
            "captures carrier-pending association evidence before stopping",
            "does not change 2.4 GHz, qdrv, wlan, queues, DMA, rates, rings, bridge topology, forwarding or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    replacements: dict[str, bytes] = {}
    start_patch = None
    pad_index = old_pad_size = None

    for entry in entries:
        if entry.name == START_ENTRY:
            start_data, start_patch = patch_start(entry.data)
            replacements[START_ENTRY] = start_data
            patched_entries.append(f125.replace_entry(entry, start_data))
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if start_patch is None:
        raise SystemExit(f"missing CPIO entry: {START_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    patched_entries_2: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = f122.patch_hashes(entry.data, replacements)
            patched_entries_2.append(f125.replace_entry(entry, hashes_data))
        else:
            patched_entries_2.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    patched_entries = patched_entries_2

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F137 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F137 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F137 changed CPIO end")

    return result, {
        "start_script": start_patch,
        "artifact_hashes": hashes_patch,
        "cpio": {
            "start": start,
            "old_end": old_cpio_end,
            "new_end": new_cpio_end,
            "old_raw_bytes": len(raw),
            "new_raw_bytes": len(result),
            "delta_bytes": 0,
            "uncompensated_delta_bytes": size_delta,
            "remainder_bytes": len(remainder),
            "remainder_sha256": sha256(remainder),
        },
        "fixed_size_compensation": {
            "entry": PAD_ENTRY,
            "old_padding_bytes": old_pad_size,
            "new_padding_bytes": new_pad_size,
            "removed_bytes": size_delta,
            "raw_bytes_preserved": True,
            "cpio_end_preserved": True,
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        f71.BOOTBASE,
        f71.LEGACY_LZMA,
    ):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    raw, patch_report = patch_cpio(source_raw.read_bytes())
    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    dtb_path = OUT / f"{BASE_OUT}.dtb"
    vmlinux_path = OUT / f"{BASE_OUT}.vmlinux"

    raw_path.write_bytes(raw)
    shutil.copy2(source_config, config_path)
    shutil.copy2(source_dtb, dtb_path)
    shutil.copy2(source_vmlinux, vmlinux_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F137 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F137 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F137 persistent entry contract failed")

    contract = subprocess.run(
        [
            sys.executable,
            str(f71.BOOTBASE),
            "--candidate-slot",
            str(web_path),
            "--candidate-name",
            f"linux_live-{BUILD_TAG}",
            "--parts-dir",
            str(f71.PARTS_DIR),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if contract.returncode != 0:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path = OUT / "bootbase-contract.json"
    contract_path.write_text(contract.stdout, encoding="utf-8")
    bootbase_contract = json.loads(contract.stdout)

    source_manifest_data = json.loads(source_manifest.read_text(encoding="ascii"))
    manifest = {
        "schema": f"openmitrastar.q3-persistent-composite-{BUILD_TAG}/v1",
        "classification": CLASSIFICATION,
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F136",
            "radio5_modules": "unchanged from F136",
            "qdrv": "unchanged from F136; HR one-shot remains disabled",
            "wlan": "unchanged from F136",
            "radio5_start": "rearms wifi0/RF/txpower after hostapd and observes post-CoC Tx-Power:0 instead of immediate rollback",
            "radio5_stop": "unchanged from F136",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F136",
            "bridge_topology": "unchanged from F136; wifi0 remains outside br0",
        },
        "runtime_policy": {
            "hr_timer": "not armed on qdrv_wlan_init",
            "post_hostapd_txpower_zero": "snapshot, rearm wifi0 and continue to CoC/PM0",
            "post_coc_visibility": "snapshot and continue to carrier/association observation",
            "carrier_pending": "does not claim ready; captures association-window evidence",
            "persistent_flash_writes": 0,
        },
        "artifacts": {},
        "slot": {
            "name": "linux_live",
            "bytes": f71.SLOT_BYTES,
            "candidate_bytes": web_path.stat().st_size,
            "fits": web_path.stat().st_size <= f71.SLOT_BYTES,
        },
        "bootbase_contract": {
            "file": contract_path.name,
            "result": bootbase_contract.get("result"),
            "candidate_accepted": bootbase_contract.get("candidate_accepted"),
        },
        "persistent_entry_contract": {
            "file": entry_contract_path.name,
            "result": "PASS",
        },
        "security": {
            "touches_router": False,
            "flash": False,
            "opens_uart": False,
        },
    }
    artifact_paths = {
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "config": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
    }
    for key, path in artifact_paths.items():
        item = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()),
        }
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item

    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sha_lines = []
    for path in (
        raw_path,
        uncompressed_path,
        lzma_path,
        uimage_path,
        web_path,
        config_path,
        dtb_path,
        vmlinux_path,
        contract_path,
        entry_contract_path,
        manifest_path,
    ):
        sha_lines.append(f"{sha256(path.read_bytes())}  {path.name}\n")
    (OUT / "SHA256SUMS").write_text("".join(sha_lines), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
