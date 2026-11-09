#!/usr/bin/env python3
"""Build F121 from F120 by making the 5 GHz carrier gate observational."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f120_5g_power_selection_from_f119 as f120
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f121-5g-carrier-probe-from-f120"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f120.OUT
SRC_BASE = f120.BASE_OUT
START_ENTRY = f120.START_ENTRY
HASHES_ENTRY = f120.HASHES_ENTRY
PAD_ENTRY = f120.PAD_ENTRY

OLD_COC_BLOCK = """if [ "$qdrv_profile" = product-v6 ]; then
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || refuse wifi0-not-running
else
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ] || refuse wifi0-not-up
fi
[ "$(cat "$rf")" = 1 ] || refuse rf-closed
[ "$compatible_gate_passed" = 1 ] || refuse coc-target-gate
[ "$(cat /sys/class/net/wifi0/carrier)" = 1 ] || refuse coc-carrier-not-ready
pduty_stop_before=$(dmesg | grep -c 'MuC: pduty_stop' || true)
/usr/sbin/iwpriv-qtn wifi0 pm 0 >/dev/null || refuse coc-pm0-set
pm_readback=$(/usr/sbin/iwpriv-qtn wifi0 get_pm 2>/dev/null) || refuse coc-pm0-get
pm_level=$(printf '%s\\n' "$pm_readback" |
\tsed -n 's/.*get_pm:[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p' | head -n 1)
[ "$pm_level" = 0 ] || refuse coc-pm0-readback
pduty_stop_after=$(dmesg | grep -c 'MuC: pduty_stop' || true)
if [ "$pduty_stop_after" -gt "$pduty_stop_before" ]; then
\tpduty_evidence=transition
else
\t# `get_pm:0` is authoritative. The MuC only logs pduty_stop on an actual
\t# transition, so an already-disabled CoC state legitimately has no delta.
\tpduty_evidence=already-zero
fi
"""

NEW_COC_BLOCK = """[ "$(cat "$rf")" = 1 ] || refuse rf-closed
[ "$compatible_gate_passed" = 1 ] || refuse coc-target-gate
pduty_stop_before=$(dmesg | grep -c 'MuC: pduty_stop' || true)
/usr/sbin/iwpriv-qtn wifi0 pm 0 >/dev/null || refuse coc-pm0-set
pm_readback=$(/usr/sbin/iwpriv-qtn wifi0 get_pm 2>/dev/null) || refuse coc-pm0-get
pm_level=$(printf '%s\\n' "$pm_readback" |
\tsed -n 's/.*get_pm:[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p' | head -n 1)
[ "$pm_level" = 0 ] || refuse coc-pm0-readback
pduty_stop_after=$(dmesg | grep -c 'MuC: pduty_stop' || true)
if [ "$pduty_stop_after" -gt "$pduty_stop_before" ]; then
\tpduty_evidence=transition
else
\t# `get_pm:0` is authoritative. The MuC only logs pduty_stop on an actual
\t# transition, so an already-disabled CoC state legitimately has no delta.
\tpduty_evidence=already-zero
fi
product_v6_carrier_gate=1
if [ "$qdrv_profile" = product-v6 ]; then
\tproduct_v6_carrier_gate=0
\tcarrier_wait=0
\twhile [ "$carrier_wait" -lt 15 ]; do
\t\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-waiting-carrier
\t\tif [ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] &&
\t\t\t[ "$(cat /sys/class/net/wifi0/carrier)" = 1 ]; then
\t\t\tproduct_v6_carrier_gate=1
\t\t\tbreak
\t\tfi
\t\tcarrier_wait=$((carrier_wait + 1))
\t\tsleep 1
\tdone
\tif [ "$product_v6_carrier_gate" != 1 ]; then
\t\tlog "OMRADIO5_CARRIER_PENDING flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || true) carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || true) pm=$pm_level action=continue-visibility-probe"
\tfi
else
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ] || refuse wifi0-not-up
fi
"""

OLD_LED_BLOCK = """if [ "$qdrv_profile" = product-v6 ]; then
\t[ -r "$led_dir/brightness" ] || refuse led5g-brightness-missing
\t[ -r "$led_dir/max_brightness" ] || refuse led5g-max-brightness-missing
\tled_max=$(cat "$led_dir/max_brightness" 2>/dev/null || true)
\tcase "$led_max" in ''|*[!0-9]*) refuse led5g-max-brightness-format ;; esac
\t[ "$led_max" -gt 0 ] || refuse led5g-max-brightness-zero
\tled_ready=0
\tled_attempt=0
\twhile [ "$led_attempt" -lt 10 ]; do
\t\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-died-waiting-led
\t\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || refuse wifi0-carrier-lost-waiting-led
\t\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-waiting-led
\t\tled_brightness=$(cat "$led_dir/brightness" 2>/dev/null || true)
\t\tcase "$led_brightness" in ''|*[!0-9]*) refuse led5g-brightness-format ;; esac
\t\tif [ "$led_brightness" = "$led_max" ]; then
\t\t\tled_ready=1
\t\t\tbreak
\t\tfi
\t\tled_attempt=$((led_attempt + 1))
\t\tsleep 1
\tdone
\t[ "$led_ready" = 1 ] || refuse led5g-brightness-not-max
\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-led
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || refuse wifi0-not-running-after-led
\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-after-led
\tled_gate=sysfs-max
else
"""

NEW_LED_BLOCK = """if [ "$qdrv_profile" = product-v6 ] && [ "${product_v6_carrier_gate:-0}" = 1 ]; then
\t[ -r "$led_dir/brightness" ] || refuse led5g-brightness-missing
\t[ -r "$led_dir/max_brightness" ] || refuse led5g-max-brightness-missing
\tled_max=$(cat "$led_dir/max_brightness" 2>/dev/null || true)
\tcase "$led_max" in ''|*[!0-9]*) refuse led5g-max-brightness-format ;; esac
\t[ "$led_max" -gt 0 ] || refuse led5g-max-brightness-zero
\tled_ready=0
\tled_attempt=0
\twhile [ "$led_attempt" -lt 10 ]; do
\t\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-died-waiting-led
\t\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || refuse wifi0-carrier-lost-waiting-led
\t\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-waiting-led
\t\tled_brightness=$(cat "$led_dir/brightness" 2>/dev/null || true)
\t\tcase "$led_brightness" in ''|*[!0-9]*) refuse led5g-brightness-format ;; esac
\t\tif [ "$led_brightness" = "$led_max" ]; then
\t\t\tled_ready=1
\t\t\tbreak
\t\tfi
\t\tled_attempt=$((led_attempt + 1))
\t\tsleep 1
\tdone
\t[ "$led_ready" = 1 ] || refuse led5g-brightness-not-max
\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-led
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || refuse wifi0-not-running-after-led
\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-after-led
\tled_gate=sysfs-max
elif [ "$qdrv_profile" = product-v6 ]; then
\tkill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-carrier-pending
\t[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ] || refuse wifi0-not-up-after-carrier-pending
\t[ "$(cat "$rf")" = 1 ] || refuse rf-lost-after-carrier-pending
\tled_gate=carrier-pending-skip
else
"""

OLD_FINAL_BLOCK = """touch "$state/commit"
chmod 0600 "$state/commit"
if [ -s "$state/rollback.pid" ]; then kill "$(cat "$state/rollback.pid")" >/dev/null 2>&1 || true; fi
rm -f "$conf" "$state/hostapd.get_config"
printf 'ready\\n' >"$state/ready"
printf 'ready\\n' >"$state/state"
if [ "$security_profile" = open-lab ]; then
\tsecurity_result=OPEN-LAB-NO-FLASH
\tpsk_result=unused
else
\tsecurity_result=WPA2-PSK-CCMP
\tpsk_result=redacted
fi
log "OMRADIO5_READY direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 ssid=$ssid region=ES channel=36 bw=80 security=$security_result psk=$psk_result tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile tx_trace=$tx_path_trace_enable fwt_ctrl=absent ioss=untouched led5g=$led_gate dmesg_marker=$led_marker_evidence association_policy=$([ "$qdrv_profile" = product-v6 ] && printf normal || printf visibility-first-external-30s)"
exit 0
"""

NEW_FINAL_BLOCK = """touch "$state/commit"
chmod 0600 "$state/commit"
if [ -s "$state/rollback.pid" ]; then kill "$(cat "$state/rollback.pid")" >/dev/null 2>&1 || true; fi
rm -f "$conf" "$state/hostapd.get_config"
if [ "$security_profile" = open-lab ]; then
\tsecurity_result=OPEN-LAB-NO-FLASH
\tpsk_result=unused
else
\tsecurity_result=WPA2-PSK-CCMP
\tpsk_result=redacted
fi
if [ "$qdrv_profile" = product-v6 ] && [ "${product_v6_carrier_gate:-0}" != 1 ]; then
\tprintf 'carrier-pending\\n' >"$state/state"
\tlog "OMRADIO5_VISIBILITY_PROBE direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 ssid=$ssid region=ES channel=36 bw=80 security=$security_result psk=$psk_result tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile tx_trace=$tx_path_trace_enable fwt_ctrl=absent ioss=untouched led5g=$led_gate dmesg_marker=$led_marker_evidence carrier=pending association_policy=visibility-first-external-30s"
\texit 0
fi
printf 'ready\\n' >"$state/ready"
printf 'ready\\n' >"$state/state"
log "OMRADIO5_READY direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 ssid=$ssid region=ES channel=36 bw=80 security=$security_result psk=$psk_result tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile tx_trace=$tx_path_trace_enable fwt_ctrl=absent ioss=untouched led5g=$led_gate dmesg_marker=$led_marker_evidence association_policy=$([ "$qdrv_profile" = product-v6 ] && printf normal || printf visibility-first-external-30s)"
exit 0
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def replace_entry(entry: f71.CpioEntry, data: bytes) -> f71.CpioEntry:
    return f71.CpioEntry(
        name=entry.name, mode=entry.mode, data=data, ino=entry.ino,
        uid=entry.uid, gid=entry.gid, nlink=entry.nlink, mtime=entry.mtime,
        devmajor=entry.devmajor, devminor=entry.devminor,
        rdevmajor=entry.rdevmajor, rdevminor=entry.rdevminor,
    )


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    for marker in ("OMRADIO5_CARRIER_PENDING", "OMRADIO5_VISIBILITY_PROBE"):
        if marker in text:
            raise SystemExit("F121 start script already contains carrier probe markers")
    for old in (OLD_COC_BLOCK, OLD_LED_BLOCK, OLD_FINAL_BLOCK):
        if old not in text:
            raise SystemExit("F121 missing carrier-probe insertion point")
    patched = text.replace(OLD_COC_BLOCK, NEW_COC_BLOCK, 1)
    patched = patched.replace(OLD_LED_BLOCK, NEW_LED_BLOCK, 1)
    patched = patched.replace(OLD_FINAL_BLOCK, NEW_FINAL_BLOCK, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "fixes": [
            "moves iwpriv pm 0 before the product-v6 carrier observation gate",
            "keeps hostapd/wifi0 alive as carrier-pending visibility probe instead of rollback",
            "skips the LED max gate while product-v6 carrier remains pending",
        ],
    }


def patch_hashes(data: bytes, start_hash: str) -> tuple[bytes, dict[str, object]]:
    out = []
    old_hash = None
    replaced = 0
    for line in data.decode("ascii").splitlines():
        if line.endswith("  /usr/sbin/om-radio5-start"):
            old_hash = line.split()[0]
            out.append(f"{start_hash}  /usr/sbin/om-radio5-start")
            replaced += 1
        else:
            out.append(line)
    if replaced != 1 or old_hash is None:
        raise SystemExit("F121 could not update om-radio5-start hash entry")
    patched = ("\n".join(out) + "\n").encode("ascii")
    return patched, {
        "entry": HASHES_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_start_sha256": old_hash,
        "new_start_sha256": start_hash,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries = []
    patched_start_data = None
    start_patch = hashes_patch = None
    pad_index = old_pad_size = None
    for entry in entries:
        if entry.name == START_ENTRY:
            patched_start_data, start_patch = patch_start(entry.data)
            patched_entries.append(replace_entry(entry, patched_start_data))
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
    patched_entries_2 = []
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            patched_hashes, hashes_patch = patch_hashes(entry.data, sha256(patched_start_data))
            patched_entries_2.append(replace_entry(entry, patched_hashes))
        else:
            patched_entries_2.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    patched_entries = patched_entries_2
    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F121 fixed-size padding cannot absorb delta={size_delta}")
    patched_entries[pad_index] = replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F121 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F121 changed CPIO end")
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
    source_result = SRC_BUILD / "build-result.json"
    for required in (source_raw, source_uncompressed, source_config, source_dtb,
                     source_vmlinux, source_manifest, source_result, f71.TEMPLATE,
                     f71.BOOTBASE, f71.LEGACY_LZMA):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")
    source_raw_bytes = source_raw.read_bytes()
    raw, patch_report = patch_cpio(source_raw_bytes)
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
        raise SystemExit("F121 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F121 webformat exceeds linux_live slot")
    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F121 persistent entry contract failed")
    contract = subprocess.run(
        [sys.executable, str(f71.BOOTBASE), "--candidate-slot", str(web_path),
         "--candidate-name", f"linux_live-{BUILD_TAG}", "--parts-dir", str(f71.PARTS_DIR)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if contract.returncode != 0:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path = OUT / "bootbase-contract.json"
    contract_path.write_text(contract.stdout, encoding="utf-8")
    contract_json = json.loads(contract.stdout)
    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)
    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_result_json = json.loads(source_result.read_text(encoding="utf-8"))
    artifacts = {
        "rootfs": raw_path,
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
    }
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f121-5g-carrier-probe-from-f120/v1",
        "classification": "F121_FROM_F120_5G_CARRIER_OBSERVATION_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "radio2g": "unchanged from F120/F119",
            "radio5_start": "moves pm0 before carrier check and keeps carrier-pending AP up for visibility probe",
            "radio5_modules": "unchanged from F120",
            "radio5_autostart": "unchanged from F120: disabled/manual only",
            "queues_dma_rates_rings": "unchanged from F120",
            "bridge_topology": "unchanged from F120",
            "entry_layout": "same raw size, CPIO end, post-CPIO remainder and entry sample as F120",
        },
        "patch": patch_report,
        "artifacts": {
            key: {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes()),
                  **({"crc32": f71.crc32(path.read_bytes())} if key == "webformat" else {})}
            for key, path in artifacts.items()
        },
        "rootfs": {"rootfs": {"file": raw_path.name, "bytes": raw_path.stat().st_size,
                              "sha256": sha256(raw_path.read_bytes())}},
        "slot": {"name": "linux_live", "bytes": f71.SLOT_BYTES,
                 "candidate_bytes": web_path.stat().st_size,
                 "fits": web_path.stat().st_size <= f71.SLOT_BYTES},
        "bootbase_contract": {"file": contract_path.name, "result": contract_json.get("result"),
                              "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract")},
        "persistent_entry_contract": {"file": entry_contract_path.name,
                                      "result": json.loads(entry_contract_path.read_text(encoding="ascii")).get("result")},
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f121-5g-carrier-probe-from-f120-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "flash": False,
    }
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    lines = [f"{sha256(path.read_bytes())}  {path.name}" for path in sorted(OUT.iterdir()) if path.is_file()]
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    print("F121_BUILD_PASS")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
