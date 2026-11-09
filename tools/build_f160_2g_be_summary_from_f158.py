#!/usr/bin/env python3
"""Build F160 from F158 with bounded 2.4 GHz BE TX summaries enabled."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f158_2g_reclaim_off_from_f157 as f158


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f160-2g-be-summary-from-f158"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F160_FROM_F158_2G_BE_SUMMARY"

SRC_BUILD = f158.OUT
SRC_BASE = f158.BASE_OUT
QDRV_SHA = f158.QDRV_SHA
WLAN_SHA = f158.WLAN_SHA
MODULE_BUILD = f158.MODULE_BUILD
NEW_QDRV = f158.NEW_QDRV
BUILD_PROFILE = f158.BUILD_PROFILE
MODULE_MANIFEST = f158.MODULE_MANIFEST
PATCH_ENTRY = "usr/sbin/om-radio-modules"

OLD_LOAD = (
    "hgw500_eapol_trace=$radio2g_eapol_trace "
    "hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue "
    "hgw500_tx_queue_guard=0 hgw500_tx_queue_guard_high=64 "
    "hgw500_tx_queue_guard_low=32 hgw500_tx_reclaim_poll=0"
)
NEW_LOAD = OLD_LOAD + " hgw500_be_tx_summary=1"
OLD_VERIFY = (
    "hgw500_txbd_be_legacy64=N hgw500_tx_queue_guard=N \\\n"
    "\t\t\thgw500_tx_queue_guard_high=64 hgw500_tx_queue_guard_low=32 \\\n"
    "\t\t\thgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=N"
)
NEW_VERIFY = OLD_VERIFY.replace(
    "hgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=N",
    "hgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=N \\\n"
    "\t\t\thgw500_be_tx_summary=Y",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_loader(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    for marker, label in ((OLD_LOAD, "load"), (OLD_VERIFY, "verify")):
        if text.count(marker) != 1:
            raise SystemExit(f"F160 loader missing unique {label} marker")
    patched = text.replace(OLD_LOAD, NEW_LOAD, 1).replace(OLD_VERIFY, NEW_VERIFY, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": PATCH_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "parameter": "hgw500_be_tx_summary=1",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    replacements: dict[str, bytes] = {}
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    report: dict[str, object] = {}

    for entry in entries:
        if entry.name == PATCH_ENTRY:
            patched, item = patch_loader(entry.data)
            replacements[entry.name] = patched
            report["radio2g_loader"] = item
            patched_entries.append(f125.replace_entry(entry, patched))
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if PATCH_ENTRY not in replacements:
        raise SystemExit(f"missing CPIO entry: {PATCH_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {engine.PAD_ENTRY}")

    final_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == engine.HASHES_ENTRY:
            patched, hashes_patch = f122.patch_hashes(entry.data, replacements)
            final_entries.append(f125.replace_entry(entry, patched))
        else:
            final_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {engine.HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch

    interim = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F160 fixed-size padding cannot absorb delta={size_delta}")
    final_entries[pad_index] = f125.replace_entry(final_entries[pad_index], b"\0" * new_pad_size)
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _entries, new_remainder = f71.parse_first_cpio(result)
    if (
        new_start != start
        or new_remainder != remainder
        or len(result) != len(raw)
        or len(result) - len(new_remainder) != old_cpio_end
    ):
        raise SystemExit("F160 changed fixed payload layout")
    report["fixed_size_compensation"] = {
        "entry": engine.PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": new_pad_size,
        "removed_bytes": size_delta,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, report


@contextlib.contextmanager
def variant_context():
    names = (
        "BUILD_TAG", "OUT", "BASE_OUT", "CLASSIFICATION", "SRC_BUILD",
        "SRC_BASE", "OLD_QDRV_SHA", "NEW_QDRV_SHA", "NEW_QDRV",
        "BUILD_PROFILE", "MODULE_MANIFEST", "WLAN_SHA",
    )
    old = {name: getattr(engine, name) for name in names}
    values = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "CLASSIFICATION": CLASSIFICATION,
        "SRC_BUILD": SRC_BUILD,
        "SRC_BASE": SRC_BASE,
        "OLD_QDRV_SHA": QDRV_SHA,
        "NEW_QDRV_SHA": QDRV_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILD_PROFILE": BUILD_PROFILE,
        "MODULE_MANIFEST": MODULE_MANIFEST,
        "WLAN_SHA": WLAN_SHA,
    }
    try:
        for name, value in values.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    original = engine.patch_cpio
    with variant_context():
        engine.patch_cpio = patch_cpio
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = engine.main()
        finally:
            engine.patch_cpio = original
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest["change_scope"] = {
        "radio2g_loader": "enable only bounded hgw500_be_tx_summary telemetry",
        "radio2g_modules_rates_crypto": "byte-identical to F158",
        "radio5": "byte-identical F157 persistent br0 WPA2 TX-BA-stable service",
        "kernel_emac_bridge_flash_layout": "unchanged from F158",
    }
    manifest["runtime_policy"] = {
        "hgw500_be_tx_summary": 1,
        "behavior_change": "none; counters and bounded periodic logs only",
        "persistent_flash_writes": 0,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    sums_path = OUT / "SHA256SUMS"
    lines = []
    for line in sums_path.read_text(encoding="ascii").splitlines():
        _digest, name = line.split("  ", 1)
        path = OUT / name
        lines.append(f"{sha256(path.read_bytes())}  {name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
