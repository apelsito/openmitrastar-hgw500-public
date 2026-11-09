#!/usr/bin/env python3
"""Build F112 from F111 by replacing only rtl_pci.ko.

F111 is the current flash-proven Linux 5.10 product image with the RC1 5 GHz
manual stack and the power-table checksum fix.  F112 keeps that image intact
except for the 2.4 GHz PCI helper module: it imports the F106 rtl_pci.ko build
that rearms the normal RX-work reclaim path when the BE guard stop path finds
the delayed work already pending.
"""
from pathlib import Path

import build_f105_2g_be_reclaim_kick_from_f104 as base
import build_f71_qcsapi_interp_from_f70 as f71


base.BUILD_TAG = "f112-2g-be-reclaim-rearm-from-f111"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.SRC_BUILD = base.ROOT / "work/mission-state/q3-persistent-composite-f111-5g-power-md5-fixed-from-f110/build"
base.SRC_BASE = "openmitrastar-linux510-q3-persistent-f111-5g-power-md5-fixed-from-f110-LZMA-OFFLINE-NO-FLASH"
base.REALTEK_BUNDLE = base.ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-be-reclaim-rearm-f106-RAM-ONLY-NO-FLASH"
base.MODULE_REPLACEMENTS = {
    base.RTL_PCI_ENTRY: base.REALTEK_BUNDLE / "modules/rtl_pci.ko",
}
base.CLASSIFICATION = "F112_FROM_F111_2G_RTL_PCI_BE_RECLAIM_REARM_FIXEDSIZE"
base.MODULE_SCOPE = "replaced only rtl_pci.ko with the F106 BE reclaim-rearm build"
base.RECLAIM_SCOPE = (
    "when BE guard stop sees schedule_delayed_work return 0, rearm the normal "
    "RX-work reclaim path with mod_delayed_work instead of leaving the guard "
    "waiting on an already-pending delayed work item"
)

PAD_ENTRY = "usr/share/openmitrastar/radio5g/f110-fixed-size.pad"


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    replacement_hashes = {
        name: f71.sha256(path.read_bytes())
        for name, path in base.MODULE_REPLACEMENTS.items()
    }
    replacement_sizes = {
        name: path.stat().st_size
        for name, path in base.MODULE_REPLACEMENTS.items()
    }
    patched_entries: list[f71.CpioEntry] = []
    reports: dict[str, object] = {}
    seen = set()
    pad_index: int | None = None
    old_pad_size: int | None = None

    for entry in entries:
        if entry.name in base.MODULE_REPLACEMENTS:
            replacement = base.MODULE_REPLACEMENTS[entry.name].read_bytes()
            seen.add(entry.name)
            reports[entry.name] = {
                "old_bytes": len(entry.data),
                "new_bytes": len(replacement),
                "delta_bytes": len(replacement) - len(entry.data),
                "old_sha256": f71.sha256(entry.data),
                "new_sha256": f71.sha256(replacement),
            }
            patched_entries.append(base.replace_entry(entry, replacement))
        elif entry.name == base.RADIO2G_HASHES:
            patched_hashes, report = base.patch_hashes(entry.data, replacement_hashes)
            reports[base.RADIO2G_HASHES] = report
            patched_entries.append(base.replace_entry(entry, patched_hashes))
        elif entry.name == base.RADIO2G_MANIFEST:
            patched_manifest, report = base.patch_radio2g_manifest(
                entry.data, replacement_hashes, replacement_sizes
            )
            reports[base.RADIO2G_MANIFEST] = report
            patched_entries.append(base.replace_entry(entry, patched_manifest))
        else:
            if entry.name == PAD_ENTRY:
                pad_index = len(patched_entries)
                old_pad_size = len(entry.data)
            patched_entries.append(entry)

    missing = sorted(set(base.MODULE_REPLACEMENTS) - seen)
    for required in (base.RADIO2G_HASHES, base.RADIO2G_MANIFEST):
        if required not in reports:
            missing.append(required)
    if pad_index is None or old_pad_size is None:
        missing.append(PAD_ENTRY)
    if missing:
        raise SystemExit(f"missing F112 CPIO entries: {missing!r}")

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    interim_len = start + len(interim_cpio) + len(remainder)
    size_delta = interim_len - len(raw)
    if old_pad_size - size_delta < 0:
        raise SystemExit(
            f"F112 fixed-size padding cannot absorb delta={size_delta}, "
            f"pad={old_pad_size}"
        )

    pad_entry = patched_entries[pad_index]
    new_pad_size = old_pad_size - size_delta
    patched_entries[pad_index] = base.replace_entry(pad_entry, b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F112 fixed-size patch changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F112 fixed-size patch changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F112 fixed-size patch changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F112 fixed-size patch changed CPIO end")

    reports["cpio"] = {
        "start": start,
        "old_end": old_cpio_end,
        "new_end": new_cpio_end,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(result),
        "delta_bytes": len(result) - len(raw),
        "uncompensated_delta_bytes": size_delta,
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
    }
    reports["fixed_size_compensation"] = {
        "entry": PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": new_pad_size,
        "removed_bytes": size_delta,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, reports


base.patch_cpio = patch_cpio


if __name__ == "__main__":
    raise SystemExit(base.main())
