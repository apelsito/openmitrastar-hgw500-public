#!/usr/bin/env python3
"""Build F126 from F125 with association-window snapshots on the real profile."""
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
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f126-5g-assoc-observe-from-f125"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f125.OUT
SRC_BASE = f125.BASE_OUT
START_ENTRY = f125.START_ENTRY
HASHES_ENTRY = f125.HASHES_ENTRY
PAD_ENTRY = f125.PAD_ENTRY

START_FUNC_ANCHOR = """start_assoc_window_guard()
{
"""

CAPTURE_FUNC_AND_ANCHOR = """capture_assoc_window_snapshot()
{
\treason="$1"
\tcase "$reason" in *[!A-Za-z0-9_.-]*|'') reason=unknown ;; esac
\tprefix="$state/assoc-window-$reason"
\t/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 status >"$prefix.hostapd-status" 2>&1 || true
\t/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta >"$prefix.all_sta" 2>&1 || true
\tif [ -r /run/openmitrastar/radio5g/hostapd.log ]; then
\t\tcp /run/openmitrastar/radio5g/hostapd.log "$prefix.hostapd.log" 2>/dev/null || true
\telif [ -r /var/log/hostapd-wifi0.log ]; then
\t\tcp /var/log/hostapd-wifi0.log "$prefix.hostapd.log" 2>/dev/null || true
\tfi
\t{
\t\t[ -r /sys/class/net/wifi0/flags ] && printf 'flags=' && cat /sys/class/net/wifi0/flags
\t\t[ -r /sys/class/net/wifi0/carrier ] && printf 'carrier=' && cat /sys/class/net/wifi0/carrier
\t\t[ -r /sys/class/net/wifi0/operstate ] && printf 'operstate=' && cat /sys/class/net/wifi0/operstate
\t\t[ -r /sys/module/qdrv/parameters/openmitrastar_rf_enable ] && printf 'rf=' && cat /sys/module/qdrv/parameters/openmitrastar_rf_enable
\t} >"$prefix.wifi0" 2>&1 || true
\tdmesg 2>/dev/null | grep -E 'OMQDRVASSOC|OMQDRVRXMGMT|OMQDRVTXPATH|OMRADIO5_ASSOC_WINDOW|AUTH|ASSOC' | tail -n 220 | redact_mac_text >"$prefix.dmesg" 2>/dev/null || true
\tchmod 0600 "$prefix".* 2>/dev/null || true
}

start_assoc_window_guard()
{
"""

OLD_HOSTAPD_DEAD = """\t\t\tif ! kill -0 "$hostapd_pid" >/dev/null 2>&1; then
\t\t\t\tlog "OMRADIO5_ASSOC_WINDOW event=hostapd-dead action=stop"
\t\t\t\t${OM_RADIO5_STOP:-/usr/sbin/om-radio5-stop} assoc-window-hostapd-dead >/dev/null 2>&1 || true
\t\t\t\texit 0
\t\t\tfi
"""

NEW_HOSTAPD_DEAD = """\t\t\tif ! kill -0 "$hostapd_pid" >/dev/null 2>&1; then
\t\t\t\tcapture_assoc_window_snapshot hostapd-dead
\t\t\t\tlog "OMRADIO5_ASSOC_WINDOW event=hostapd-dead action=stop"
\t\t\t\t${OM_RADIO5_STOP:-/usr/sbin/om-radio5-stop} assoc-window-hostapd-dead >/dev/null 2>&1 || true
\t\t\t\texit 0
\t\t\tfi
"""

OLD_STA_SNAPSHOT = """\t\t\t\t\tdmesg 2>/dev/null | tail -n 120 | redact_mac_text >"$state/assoc-window.dmesg" 2>/dev/null || true
\t\t\t\t\tchmod 0600 "$state/assoc-window.all_sta" "$state/assoc-window.dmesg" 2>/dev/null || true
\t\t\t\t\tlog "OMRADIO5_ASSOC_WINDOW event=sta-observed action=stop window=${guard_window}s"
"""

NEW_STA_SNAPSHOT = """\t\t\t\t\tcapture_assoc_window_snapshot sta-observed
\t\t\t\t\tlog "OMRADIO5_ASSOC_WINDOW event=sta-observed action=stop window=${guard_window}s"
"""

OLD_TIMEOUT = """\t\tlog "OMRADIO5_ASSOC_WINDOW event=timeout action=stop window=${guard_window}s"
\t\t${OM_RADIO5_STOP:-/usr/sbin/om-radio5-stop} assoc-window-timeout >/dev/null 2>&1 || true
"""

NEW_TIMEOUT = """\t\tcapture_assoc_window_snapshot timeout
\t\tlog "OMRADIO5_ASSOC_WINDOW event=timeout action=stop window=${guard_window}s"
\t\t${OM_RADIO5_STOP:-/usr/sbin/om-radio5-stop} assoc-window-timeout >/dev/null 2>&1 || true
"""

OLD_ACTIVATION = """association_policy=$([ "$qdrv_profile" = product-v6 ] && printf first-sta-stop-20s || printf visibility-first-external-30s)
if [ "$qdrv_profile" = product-v6 ]; then
\tstart_assoc_window_guard
fi
printf 'ready\\n' >"$state/ready"
"""

NEW_ACTIVATION = """case "$qdrv_profile" in
\tproduct-v6|beacon-lifetime-37527d16)
\t\tassociation_policy=first-sta-stop-20s
\t\tstart_assoc_window_guard
\t\t;;
\t*)
\t\tassociation_policy=visibility-first-external-30s
\t\t;;
esac
printf 'ready\\n' >"$state/ready"
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if "capture_assoc_window_snapshot()" in text:
        raise SystemExit("F126 start script already has association snapshots")
    replacements = (
        (START_FUNC_ANCHOR, CAPTURE_FUNC_AND_ANCHOR, "snapshot_helper"),
        (OLD_HOSTAPD_DEAD, NEW_HOSTAPD_DEAD, "hostapd_dead_snapshot"),
        (OLD_STA_SNAPSHOT, NEW_STA_SNAPSHOT, "sta_observed_snapshot"),
        (OLD_TIMEOUT, NEW_TIMEOUT, "timeout_snapshot"),
        (OLD_ACTIVATION, NEW_ACTIVATION, "beacon_lifetime_activation"),
    )
    patched = text
    applied = []
    for old, new, name in replacements:
        if old not in patched:
            raise SystemExit(f"F126 missing replacement point: {name}")
        patched = patched.replace(old, new, 1)
        applied.append(name)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "applied": applied,
        "fixes": [
            "preserves F125 qdrv and wlan artifacts",
            "activates the association window for beacon-lifetime-37527d16",
            "captures bounded AUTH/ASSOC/QDRV snapshots on sta, timeout and hostapd-dead",
            "does not change queues, DMA, rates, rings, forwarding or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patched_start_data = None
    start_patch = None
    pad_index = old_pad_size = None

    for entry in entries:
        if entry.name == START_ENTRY:
            patched_start_data, start_patch = patch_start(entry.data)
            patched_entries.append(f125.replace_entry(entry, patched_start_data))
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if patched_start_data is None or start_patch is None:
        raise SystemExit(f"missing CPIO entry: {START_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    patched_entries_2: list[f71.CpioEntry] = []
    hashes_patch = None
    start_hash = sha256(patched_start_data)
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = f125.patch_hashes(entry.data, start_hash)
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
        raise SystemExit(f"F126 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F126 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F126 changed CPIO end")

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
        raise SystemExit("F126 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F126 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F126 persistent entry contract failed")

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
        "classification": "F126_FROM_F125_5G_ASSOC_OBSERVE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F125",
            "radio5_start": "activates F125 association window for beacon-lifetime profile and adds bounded snapshots",
            "radio5_stop": "unchanged from F125",
            "radio5_modules": "unchanged from F125",
            "qdrv": "unchanged from F125",
            "wlan": "unchanged from F125",
            "bridge_topology": "unchanged from F125",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F125",
        },
        "runtime_policy": {
            "association_window_profiles": ["product-v6", "beacon-lifetime-37527d16"],
            "snapshot_events": ["sta-observed", "timeout", "hostapd-dead"],
            "persistent_flash_writes": 0,
        },
        "artifacts": {
            "decompressed_payload": {"file": raw_path.name, "bytes": raw_path.stat().st_size, "sha256": sha256(raw_path.read_bytes())},
            "uncompressed_uimage": {"file": uncompressed_path.name, "bytes": uncompressed_path.stat().st_size, "sha256": sha256(uncompressed_path.read_bytes())},
            "lzma": {"file": lzma_path.name, "bytes": lzma_path.stat().st_size, "sha256": sha256(lzma_path.read_bytes())},
            "uimage": {"file": uimage_path.name, "bytes": uimage_path.stat().st_size, "sha256": sha256(uimage_path.read_bytes())},
            "webformat": {"file": web_path.name, "bytes": web_path.stat().st_size, "sha256": sha256(web_path.read_bytes()), "crc32": f71.crc32(web_path.read_bytes())},
            "config": {"file": config_path.name, "bytes": config_path.stat().st_size, "sha256": sha256(config_path.read_bytes())},
            "dtb": {"file": dtb_path.name, "bytes": dtb_path.stat().st_size, "sha256": sha256(dtb_path.read_bytes())},
            "vmlinux": {"file": vmlinux_path.name, "bytes": vmlinux_path.stat().st_size, "sha256": sha256(vmlinux_path.read_bytes())},
        },
        "slot": {"name": "linux_live", "bytes": f71.SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": web_path.stat().st_size <= f71.SLOT_BYTES},
        "bootbase_contract": {"file": contract_path.name, "result": bootbase_contract.get("result"), "candidate_accepted": bootbase_contract.get("candidate", {}).get("accepted")},
        "persistent_entry_contract": {"file": entry_contract_path.name, "result": json.loads(entry_contract_path.read_text(encoding="utf-8")).get("result")},
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = OUT / "SHA256SUMS"
    sum_files = [raw_path, uncompressed_path, lzma_path, uimage_path, web_path, config_path, dtb_path, vmlinux_path, manifest_path, entry_contract_path, contract_path]
    sums.write_text("".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_files), encoding="ascii")
    result = {
        "status": "PASS",
        "build_tag": BUILD_TAG,
        "out": str(OUT.relative_to(ROOT)),
        "webformat": str(web_path.relative_to(ROOT)),
        "webformat_sha256": manifest["artifacts"]["webformat"]["sha256"],
        "candidate_crc32": manifest["artifacts"]["webformat"]["crc32"],
        "full_slot_crc32": f71.crc32(web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)),
        "qdrv_sha256": f122.NEW_QDRV_SHA,
        "wlan_sha256": f122.NEW_WLAN_SHA,
        "fix": "assoc-observe-beacon-lifetime",
    }
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
