#!/usr/bin/env python3
"""Build F153 from F152 with HGW AP inactivity refresh on valid RX data."""
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
import build_f152_5g_inactivity_trace_from_f151 as f152


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f153-5g-rx-inactivity-refresh-from-f152"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F153_FROM_F152_5G_RX_INACTIVITY_REFRESH"

SRC_BUILD = f152.OUT
SRC_BASE = f152.BASE_OUT
OLD_QDRV_SHA = f152.QDRV_SHA
NEW_QDRV_SHA = "cc3ca17b10cc3efcdc9a37343ead4e0c28be07e331542663b94dd0b2de0b7a61"
WLAN_SHA = f152.NEW_WLAN_SHA

MODULE_BUILD = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-inactivity-refresh-f153-20260831"
MODULE_ROOT = MODULE_BUILD / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna"
NEW_QDRV = MODULE_ROOT / "qdrv/qdrv.ko"
BUILT_WLAN = MODULE_ROOT / "wlan/wlan.ko"
BUILD_PROFILE = MODULE_BUILD / "build-profile.env"
MODULE_MANIFEST = MODULE_BUILD / "module-manifest.tsv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    old_line = f"expected_qdrv_sha={OLD_QDRV_SHA}"
    new_line = f"expected_qdrv_sha={NEW_QDRV_SHA}"
    if text.count(old_line) != 1:
        raise SystemExit("F153 start script missing unique F152 qdrv hash")
    patched = text.replace(old_line, new_line).encode("ascii")
    return patched, {
        "entry": engine.START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_qdrv_sha256": OLD_QDRV_SHA,
        "new_qdrv_sha256": NEW_QDRV_SHA,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    qdrv = NEW_QDRV.read_bytes()
    if sha256(qdrv) != NEW_QDRV_SHA:
        raise SystemExit("F153 rebuilt qdrv hash mismatch")
    if b"OMQTNINACT stage=rx-refresh" not in qdrv:
        raise SystemExit("F153 rebuilt qdrv lacks RX inactivity refresh marker")
    if sha256(BUILT_WLAN.read_bytes()) != WLAN_SHA:
        raise SystemExit("F153 clean-build wlan changed unexpectedly")

    replacements: dict[str, bytes] = {engine.QDRV_ENTRY: qdrv}
    report: dict[str, object] = {
        "qdrv": {
            "entry": engine.QDRV_ENTRY,
            "old_sha256": OLD_QDRV_SHA,
            "new_sha256": NEW_QDRV_SHA,
            "new_bytes": len(qdrv),
            "fixes": [
                "refresh associated AP station inactivity on valid HGW RX data",
                "mirror the normal net80211 RX liveness update in the AuC fast path",
                "retain the bounded F152 inactivity trace for runtime proof",
            ],
        }
    }
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen: set[str] = set()

    for entry in entries:
        if entry.name == engine.QDRV_ENTRY:
            if sha256(entry.data) != OLD_QDRV_SHA:
                raise SystemExit("F153 source qdrv hash mismatch")
            report["qdrv"]["old_bytes"] = len(entry.data)
            patched_entries.append(f125.replace_entry(entry, qdrv))
            seen.add(entry.name)
        elif entry.name == engine.WLAN_ENTRY:
            if sha256(entry.data) != WLAN_SHA:
                raise SystemExit("F153 source wlan hash mismatch")
            patched_entries.append(entry)
            seen.add(entry.name)
        elif entry.name == engine.START_ENTRY:
            data, item = patch_start(entry.data)
            replacements[entry.name] = data
            report["start_script"] = item
            patched_entries.append(f125.replace_entry(entry, data))
            seen.add(entry.name)
        elif entry.name == engine.DRIVER_CONTRACT_ENTRY:
            data, item = f122.patch_driver_contract(entry.data, NEW_QDRV_SHA, WLAN_SHA)
            replacements[entry.name] = data
            report["driver_contract"] = item
            patched_entries.append(f125.replace_entry(entry, data))
            seen.add(entry.name)
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    required = {
        engine.QDRV_ENTRY,
        engine.WLAN_ENTRY,
        engine.START_ENTRY,
        engine.DRIVER_CONTRACT_ENTRY,
    }
    if seen != required:
        raise SystemExit(f"F153 required entries missing: {sorted(required - seen)}")
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
        raise SystemExit(f"F153 fixed-size padding cannot absorb delta={size_delta}")
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
        raise SystemExit("F153 changed fixed payload layout")
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
        "OLD_QDRV_SHA": OLD_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
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
    for path, expected in ((NEW_QDRV, NEW_QDRV_SHA), (BUILT_WLAN, WLAN_SHA)):
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise SystemExit(f"F153 module missing or changed: {path}")

    source = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c").read_text(
        encoding="ascii"
    )
    required_source = (
        'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
        "vap->iv_opmode == IEEE80211_M_HOSTAP",
        "ni->ni_associd != 0",
        "WRITE_ONCE(ni->ni_inact, reload)",
        'OMQTNINACT stage=rx-refresh',
    )
    for marker in required_source:
        if marker not in source:
            raise SystemExit(f"F153 source marker missing: {marker}")

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
        "radio2g": "unchanged from F152",
        "radio5_start_stop_security_topology": "unchanged from F152",
        "radio5_modules": "only qdrv.ko replaced; wlan.ko remains byte-identical",
        "qdrv_rx": "HGW HOSTAP associated-station inactivity refresh on valid RX data",
        "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F152",
    }
    manifest["runtime_policy"] = {
        "liveness_source": "accepted uplink data frame from an associated station",
        "expected_effect": "prevent false station expiry while auc_tx=1 bypasses MuC counters",
        "tx_only_activity": "does not refresh inactivity",
        "inactivity_trace": "F152 bounded wlan trace retained",
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
