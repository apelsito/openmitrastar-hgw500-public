#!/usr/bin/env python3
"""Build F128 from F127 by adding 5 GHz TX-power visibility gates."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f126_5g_assoc_observe_from_f125 as f126
import build_f127_5g_persistent_ap_from_f126 as f127
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f128-5g-visibility-power-gate-from-f127"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f127.OUT
SRC_BASE = f127.BASE_OUT
START_ENTRY = f127.START_ENTRY
HASHES_ENTRY = f127.HASHES_ENTRY
PAD_ENTRY = f127.PAD_ENTRY

OLD_VAP_FUNCTION_END = """\tlog "OMRADIO5_VAP_CREATE_REPLY status=ok label=$label reply_len=$reply_len"
}

mkdir -p "$state"
"""

NEW_VISIBILITY_FUNCTIONS = """\tlog "OMRADIO5_VAP_CREATE_REPLY status=ok label=$label reply_len=$reply_len"
}

qtn_visibility_snapshot()
{
\tlabel=$1
\t{
\t\tprintf 'label=%s\\n' "$label"
\t\tprintf 'rf=%s\\n' "$(cat "$rf" 2>/dev/null || true)"
\t\t/usr/sbin/iwconfig-qtn wifi0 2>&1 || true
\t\t/usr/sbin/iwpriv-qtn wifi0 get_region 2>&1 || true
\t\t/usr/sbin/iwpriv-qtn wifi0 get_mode 2>&1 || true
\t\t/usr/sbin/iwpriv-qtn wifi0 get_doth 2>&1 || true
\t\t/usr/sbin/iwpriv-qtn wifi0 get_tpc 2>&1 || true
\t\t/usr/sbin/iwpriv-qtn wifi0 get_pm 2>&1 || true
\t\tif [ -r "$state/hostapd.log" ]; then
\t\t\tprintf 'hostapd_tail_begin\\n'
\t\t\ttail -n 120 "$state/hostapd.log"
\t\t\tprintf 'hostapd_tail_end\\n'
\t\tfi
\t} >"$state/visibility-$label.log" 2>/dev/null || true
\tchmod 0600 "$state/visibility-$label.log" 2>/dev/null || true
}

require_radio5_visibility_state()
{
\tlabel=$1
\t/usr/sbin/iwconfig-qtn wifi0 >"$state/iwconfig-$label.log" 2>&1 ||
\t\trefuse "visibility-iwconfig-$label"
\ttx_power=$(sed -n 's/.*Tx-Power:\\([0-9][0-9]*\\) dBm.*/\\1/p' "$state/iwconfig-$label.log" | head -n 1)
\tcase "$tx_power" in ''|*[!0-9]*) qtn_visibility_snapshot "$label-no-txpower"; refuse "visibility-txpower-parse-$label" ;; esac
\tif [ "$tx_power" -le 0 ]; then
\t\tqtn_visibility_snapshot "$label-txpower-zero"
\t\trefuse "visibility-txpower-zero-$label"
\tfi
\tgrep -Fq 'Frequency:5.18 GHz' "$state/iwconfig-$label.log" || {
\t\tqtn_visibility_snapshot "$label-frequency"
\t\trefuse "visibility-frequency-$label"
\t}
\tif [ -r "$state/hostapd.log" ]; then
\t\ttail -n 120 "$state/hostapd.log" >"$state/hostapd-tail-$label.log" 2>/dev/null || true
\t\tchmod 0600 "$state/hostapd-tail-$label.log" 2>/dev/null || true
\t\t! grep -Fq 'Mode: (null)' "$state/hostapd-tail-$label.log" || {
\t\t\tqtn_visibility_snapshot "$label-hostapd-mode-null"
\t\t\trefuse "visibility-hostapd-mode-null-$label"
\t\t}
\t\t! grep -Fq 'Frequency: -1 MHz' "$state/hostapd-tail-$label.log" || {
\t\t\tqtn_visibility_snapshot "$label-hostapd-frequency-invalid"
\t\t\trefuse "visibility-hostapd-frequency-invalid-$label"
\t\t}
\tfi
\tlog "OMRADIO5_VISIBILITY_STATE_PASS label=$label tx_power_dbm=$tx_power"
}

mkdir -p "$state"
"""

OLD_CONFIG_BLOCK = """/usr/sbin/iwpriv-qtn wifi0 region 21317 >/dev/null || refuse region-set
/usr/sbin/iwpriv-qtn wifi0 mode 11ac80Edge+ >/dev/null || refuse mode-set
/usr/sbin/iwconfig-qtn wifi0 essid "$ssid" >/dev/null || refuse ssid-set
/usr/sbin/iwconfig-qtn wifi0 channel 36 >/dev/null || refuse channel-set
[ "$(cat "$rf")" = 1 ] || refuse rf-not-open-during-config
/usr/sbin/iwpriv-qtn wifi0 get_region | grep -q 'get_region:21317' || refuse region-readback
/usr/sbin/iwpriv-qtn wifi0 get_mode | grep -Eqi '11ac80' || refuse mode-readback
/usr/sbin/iwconfig-qtn wifi0 | grep -Fq "ESSID:\\"$ssid\\"" || refuse ssid-readback
/usr/sbin/iwconfig-qtn wifi0 | grep -Fq 'Frequency:5.18 GHz' || refuse channel-readback
"""

NEW_CONFIG_BLOCK = """/usr/sbin/iwpriv-qtn wifi0 region 21317 >/dev/null || refuse region-set
/usr/sbin/iwpriv-qtn wifi0 mode 11ac80Edge+ >/dev/null || refuse mode-set
/usr/sbin/iwconfig-qtn wifi0 essid "$ssid" >/dev/null || refuse ssid-set
/usr/sbin/iwconfig-qtn wifi0 channel 36 >/dev/null || refuse channel-set
[ "$(cat "$rf")" = 1 ] || refuse rf-not-open-during-config
/usr/sbin/iwpriv-qtn wifi0 get_region | grep -q 'get_region:21317' || refuse region-readback
/usr/sbin/iwpriv-qtn wifi0 get_mode | grep -Eqi '11ac80' || refuse mode-readback
/usr/sbin/iwconfig-qtn wifi0 | grep -Fq "ESSID:\\"$ssid\\"" || refuse ssid-readback
/usr/sbin/iwconfig-qtn wifi0 | grep -Fq 'Frequency:5.18 GHz' || refuse channel-readback
qtn_txpower_val=16717057
qtn_reg_txpower_val=65301
/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/init-txpower.log" 2>&1 || refuse txpower-init
/usr/sbin/iwpriv-qtn wifi0 cfg_txpower "$qtn_txpower_val" >"$state/cfg-txpower.log" 2>&1 || refuse txpower-cfg
/usr/sbin/iwpriv-qtn wifi0 cfg_reg_txpower "$qtn_reg_txpower_val" >"$state/cfg-reg-txpower.log" 2>&1 || refuse txpower-reg-cfg
/usr/sbin/iwpriv-qtn wifi0 doth 1 >"$state/doth-set.log" 2>&1 || refuse doth-enable
/usr/sbin/iwpriv-qtn wifi0 get_doth | grep -q 'get_doth:1' || refuse doth-readback
/usr/sbin/iwpriv-qtn wifi0 tpc 1 >"$state/tpc-set.log" 2>&1 || refuse tpc-enable
/usr/sbin/iwpriv-qtn wifi0 get_tpc | grep -q 'get_tpc:1' || refuse tpc-readback
/usr/sbin/iwpriv-qtn wifi0 tpc_interval 30 >"$state/tpc-interval.log" 2>&1 || refuse tpc-interval
log "OMRADIO5_TXPOWER_PARITY init=$qtn_txpower_val reg=$qtn_reg_txpower_val doth=1 tpc=1 source=oem-start-vap"
"""

OLD_POST_HOSTAPD_BLOCK = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""

NEW_POST_HOSTAPD_BLOCK = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
require_radio5_visibility_state post-hostapd
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""

OLD_POST_COC_BLOCK = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-coc
[ "$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping)" = PONG ] || refuse hostapd-pong-after-coc
[ -e /sys/class/net/br0/brif/eth0 ] || refuse management-lost-after-coc
"""

NEW_POST_COC_BLOCK = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead-after-coc
[ "$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping)" = PONG ] || refuse hostapd-pong-after-coc
require_radio5_visibility_state post-coc
[ -e /sys/class/net/br0/brif/eth0 ] || refuse management-lost-after-coc
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if "OMRADIO5_TXPOWER_PARITY" in text or "OMRADIO5_VISIBILITY_STATE_PASS" in text:
        raise SystemExit("F128 start script already contains visibility power gates")
    replacements = (
        (OLD_VAP_FUNCTION_END, NEW_VISIBILITY_FUNCTIONS),
        (OLD_CONFIG_BLOCK, NEW_CONFIG_BLOCK),
        (OLD_POST_HOSTAPD_BLOCK, NEW_POST_HOSTAPD_BLOCK),
        (OLD_POST_COC_BLOCK, NEW_POST_COC_BLOCK),
    )
    patched = text
    for old, new in replacements:
        if old not in patched:
            raise SystemExit("F128 missing visibility-power insertion point")
        patched = patched.replace(old, new, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "fixes": [
            "seeds the qdrv TX power table before hostapd using the OEM start-vap encoding",
            "enables 802.11h/DOTH and TPC before hostapd instead of after failed visibility",
            "refuses ready when iwconfig-qtn reports Tx-Power:0 dBm",
            "refuses ready when the hostapd tail still reports Mode: (null) or Frequency: -1 MHz",
            "does not change qdrv, wlan, queues, DMA, rates, rings, forwarding, bridge topology or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    original = f127.patch_start
    f127.patch_start = patch_start
    try:
        return f127.patch_cpio(raw)
    finally:
        f127.patch_start = original


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
        raise SystemExit("F128 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F128 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F128 persistent entry contract failed")

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
        "classification": "F128_FROM_F127_5G_VISIBILITY_POWER_GATE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F127",
            "radio5_start": "adds qdrv TX-power parity before hostapd and fail-closed visibility gates",
            "radio5_stop": "unchanged from F127",
            "radio5_modules": "unchanged from F127",
            "qdrv": "unchanged from F127",
            "wlan": "unchanged from F127",
            "bridge_topology": "unchanged from F127",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F127",
        },
        "runtime_policy": {
            "persistent_ap_profiles": ["product-v6", "beacon-lifetime-37527d16"],
            "association_window_auto_stop": False,
            "visibility_false_ready_allowed": False,
            "txpower_zero_ready_allowed": False,
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
    sum_files = [raw_path, uncompressed_path, lzma_path, uimage_path, web_path, config_path, dtb_path, vmlinux_path, manifest_path, entry_contract_path, contract_path]
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_files), encoding="ascii")
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
        "fix": "5g-txpower-parity-and-fail-closed-visibility-ready-gates",
    }
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
