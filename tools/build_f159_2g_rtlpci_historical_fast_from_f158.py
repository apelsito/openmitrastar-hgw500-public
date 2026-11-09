#!/usr/bin/env python3
"""Build F159 from F158 with the last 8 MiB-proven rtl_pci module."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f105_2g_be_reclaim_kick_from_f104 as radio2g
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f158_2g_reclaim_off_from_f157 as f158


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f159-2g-rtlpci-historical-fast-from-f158"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F159_FROM_F158_2G_RTLPCI_HISTORICAL_FAST"

SRC_BUILD = f158.OUT
SRC_BASE = f158.BASE_OUT
REF_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
REF_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
RTL_PCI_ENTRY = radio2g.RTL_PCI_ENTRY
OLD_RTL_PCI_SHA = "6f85efa424c6aa5b693982ae074d268d2312a3f9262238e8c6f5eda16199df63"
NEW_RTL_PCI_SHA = "c6e1c2cd8279cfdeea154b96ecda92a105906d2e25fd713834b9318dc8cf2933"

QDRV_SHA = f158.QDRV_SHA
WLAN_SHA = f158.WLAN_SHA
MODULE_BUILD = f158.MODULE_BUILD
NEW_QDRV = f158.NEW_QDRV
BUILD_PROFILE = f158.BUILD_PROFILE
MODULE_MANIFEST = f158.MODULE_MANIFEST


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reference_rtl_pci() -> bytes:
    raw = (REF_BUILD / f"{REF_BASE}.decompressed.bin").read_bytes()
    _start, entries, _remainder = f71.parse_first_cpio(raw)
    data = next(entry.data for entry in entries if entry.name == RTL_PCI_ENTRY)
    if sha256(data) != NEW_RTL_PCI_SHA:
        raise SystemExit("F159 reference rtl_pci hash mismatch")
    return data


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    replacement = reference_rtl_pci()
    replacement_hashes = {RTL_PCI_ENTRY: NEW_RTL_PCI_SHA}
    replacement_sizes = {RTL_PCI_ENTRY: len(replacement)}
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    report: dict[str, object] = {}
    seen: set[str] = set()

    for entry in entries:
        if entry.name == RTL_PCI_ENTRY:
            if sha256(entry.data) != OLD_RTL_PCI_SHA:
                raise SystemExit("F159 source rtl_pci hash mismatch")
            report[RTL_PCI_ENTRY] = {
                "old_bytes": len(entry.data),
                "new_bytes": len(replacement),
                "old_sha256": OLD_RTL_PCI_SHA,
                "new_sha256": NEW_RTL_PCI_SHA,
            }
            patched_entries.append(f125.replace_entry(entry, replacement))
            seen.add(entry.name)
        elif entry.name == radio2g.RADIO2G_HASHES:
            patched, item = radio2g.patch_hashes(entry.data, replacement_hashes)
            report[radio2g.RADIO2G_HASHES] = item
            patched_entries.append(f125.replace_entry(entry, patched))
            seen.add(entry.name)
        elif entry.name == radio2g.RADIO2G_MANIFEST:
            patched, item = radio2g.patch_radio2g_manifest(
                entry.data, replacement_hashes, replacement_sizes
            )
            report[radio2g.RADIO2G_MANIFEST] = item
            patched_entries.append(f125.replace_entry(entry, patched))
            seen.add(entry.name)
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    required = {RTL_PCI_ENTRY, radio2g.RADIO2G_HASHES, radio2g.RADIO2G_MANIFEST}
    if seen != required:
        raise SystemExit(f"F159 required entries missing: {sorted(required - seen)}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {engine.PAD_ENTRY}")

    interim = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F159 fixed-size padding cannot absorb delta={size_delta}")
    patched_entries[pad_index] = f125.replace_entry(
        patched_entries[pad_index], b"\0" * new_pad_size
    )
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _entries, new_remainder = f71.parse_first_cpio(result)
    if (
        new_start != start
        or new_remainder != remainder
        or len(result) != len(raw)
        or len(result) - len(new_remainder) != old_cpio_end
    ):
        raise SystemExit("F159 changed fixed payload layout")
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
        "radio2g_rtl_pci": "reverted only rtl_pci.ko to the historical 8 MiB-proven c6e1 build",
        "radio2g_rtl8192ee_rates_crypto": "byte-identical to F158",
        "radio2g_loader": "byte-identical F158 no-guard/no-reclaim profile",
        "radio5": "byte-identical F157 persistent br0 WPA2 TX-BA-stable service",
        "kernel_emac_bridge_flash_layout": "unchanged from F158",
    }
    manifest["runtime_policy"] = {
        "rtl_pci_sha256": NEW_RTL_PCI_SHA,
        "evidence_basis": "historical 8 MiB download PASS at 968364 B/s",
        "expected_effect": "remove the later BE reclaim-rearm code from the inactive no-guard profile",
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
