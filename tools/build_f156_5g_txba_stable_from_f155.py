#!/usr/bin/env python3
"""Build F156 from F155 with the proven conservative TX-BA policy."""
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
import build_f155_5g_txpool_trace_from_f154 as f155


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f156-5g-txba-stable-from-f155"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F156_FROM_F155_5G_TXBA_STABLE"

SRC_BUILD = f155.OUT
SRC_BASE = f155.BASE_OUT
QDRV_SHA = f155.NEW_QDRV_SHA
WLAN_SHA = f155.WLAN_SHA
MODULE_BUILD = f155.MODULE_BUILD
NEW_QDRV = f155.NEW_QDRV
BUILD_PROFILE = f155.BUILD_PROFILE
MODULE_MANIFEST = f155.MODULE_MANIFEST

INSERT_AFTER = b'[ "$ready" = 1 ] || refuse hostapd-not-ready\n'
TXBA_POLICY = (
    b'/usr/sbin/iwpriv-qtn wifi0 setparam 402 1 >"$state/txba-disable.log" 2>&1 || refuse txba-disable\n'
    b'/usr/sbin/iwpriv-qtn wifi0 getparam 402 2>/dev/null | grep -q \'getparam:1\' || refuse txba-readback\n'
    b"log 'OMRADIO5_TXBA_POLICY disabled=1 source=f156 reason=stable-linux510-auctx'\n"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    if data.count(INSERT_AFTER) != 1:
        raise SystemExit("F156 start script insertion point is not unique")
    if b"OMRADIO5_TXBA_POLICY" in data:
        raise SystemExit("F156 source already contains TX-BA policy")
    patched = data.replace(INSERT_AFTER, INSERT_AFTER + TXBA_POLICY)
    return patched, {
        "entry": engine.START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "policy": "tx_ba_disable=1",
        "readback": "iwpriv-qtn wifi0 getparam 402 reports 1",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    replacements: dict[str, bytes] = {}
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen = False
    report: dict[str, object] = {}

    for entry in entries:
        if entry.name == engine.START_ENTRY:
            data, item = patch_start(entry.data)
            replacements[entry.name] = data
            report["start_script"] = item
            patched_entries.append(f125.replace_entry(entry, data))
            seen = True
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    if not seen:
        raise SystemExit(f"missing CPIO entry: {engine.START_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {engine.PAD_ENTRY}")

    final_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == engine.HASHES_ENTRY:
            data, hashes_patch = f122.patch_hashes(entry.data, replacements)
            final_entries.append(f125.replace_entry(entry, data))
        else:
            final_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {engine.HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch

    interim = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F156 fixed-size padding cannot absorb delta={size_delta}")
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
        raise SystemExit("F156 changed fixed payload layout")
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
        "radio2g": "unchanged from F155",
        "radio5_modules": "byte-identical to F155",
        "radio5_security_topology": "unchanged from F155",
        "radio5_start": "set and verify tx_ba_disable=1 after hostapd becomes ready",
        "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F155",
    }
    manifest["runtime_policy"] = {
        "tx_ba_disable": 1,
        "evidence": "F155 temporary BA-off trial passed 8 MiB bidirectional traffic and soak",
        "expected_effect": "avoid intermittent AuC downlink degradation after AP/client re-association",
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
