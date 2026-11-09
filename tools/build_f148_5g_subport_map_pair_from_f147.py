#!/usr/bin/env python3
"""Build F148 from F147 with a matched qdrv/wlan sub-port mapping pair."""
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
import build_f147_5g_readonly_get_from_f146 as f147


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f148-5g-subport-map-pair-from-f147"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F148_FROM_F147_5G_SUBPORT_MAP_PAIR"

SRC_BUILD = f147.OUT
SRC_BASE = f147.BASE_OUT
OLD_QDRV_SHA = f147.NEW_QDRV_SHA
OLD_WLAN_SHA = engine.WLAN_SHA
NEW_QDRV_SHA = "600a6f98bb3151cf80755bd5132b8bc9a7460b86146557d57ba8c97568d5a581"
NEW_WLAN_SHA = "a750b273c0570c2ccfe0fce3f28a311d2e8e3b9f7d7ef9f7cd9ed48046065233"

MODULE_BUILD = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-subport-map-f148-20260831"
MODULE_ROOT = MODULE_BUILD / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna"
NEW_QDRV = MODULE_ROOT / "qdrv/qdrv.ko"
NEW_WLAN = MODULE_ROOT / "wlan/wlan.ko"
BUILD_PROFILE = MODULE_BUILD / "build-profile.env"
MODULE_MANIFEST = MODULE_BUILD / "module-manifest.tsv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if text.count(OLD_QDRV_SHA) != 1:
        raise SystemExit("F148 start script missing unique F147 qdrv hash")
    patched = text.replace(OLD_QDRV_SHA, NEW_QDRV_SHA).encode("ascii")
    return patched, {
        "entry": engine.START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_qdrv_sha256": OLD_QDRV_SHA,
        "new_qdrv_sha256": NEW_QDRV_SHA,
        "fixes": [
            "keep the F147 RF/VAP/userspace order and TX-power policy",
            "update the qdrv integrity expectation for the matched module pair",
            "do not change 2.4 GHz, rates, rings, forwarding, topology or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    qdrv = NEW_QDRV.read_bytes()
    wlan = NEW_WLAN.read_bytes()
    if sha256(qdrv) != NEW_QDRV_SHA or sha256(wlan) != NEW_WLAN_SHA:
        raise SystemExit("F148 rebuilt module hash mismatch")

    replacements: dict[str, bytes] = {
        engine.QDRV_ENTRY: qdrv,
        engine.WLAN_ENTRY: wlan,
    }
    report: dict[str, object] = {
        "modules": {
            engine.QDRV_ENTRY: {
                "old_sha256": OLD_QDRV_SHA,
                "new_sha256": NEW_QDRV_SHA,
                "new_bytes": len(qdrv),
            },
            engine.WLAN_ENTRY: {
                "old_sha256": OLD_WLAN_SHA,
                "new_sha256": NEW_WLAN_SHA,
                "new_bytes": len(wlan),
            },
        }
    }
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen: set[str] = set()

    for entry in entries:
        if entry.name == engine.START_ENTRY:
            data, item = patch_start(entry.data)
            replacements[entry.name] = data
            report["start_script"] = item
            patched_entries.append(f125.replace_entry(entry, data))
            seen.add(entry.name)
        elif entry.name == engine.DRIVER_CONTRACT_ENTRY:
            data, item = f122.patch_driver_contract(entry.data, NEW_QDRV_SHA, NEW_WLAN_SHA)
            replacements[entry.name] = data
            report["driver_contract"] = item
            patched_entries.append(f125.replace_entry(entry, data))
            seen.add(entry.name)
        elif entry.name in replacements:
            expected = OLD_QDRV_SHA if entry.name == engine.QDRV_ENTRY else OLD_WLAN_SHA
            actual = sha256(entry.data)
            if actual != expected:
                raise SystemExit(f"F148 source module hash mismatch for {entry.name}: {actual}")
            report["modules"][entry.name]["old_bytes"] = len(entry.data)
            patched_entries.append(f125.replace_entry(entry, replacements[entry.name]))
            seen.add(entry.name)
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    for required in (
        engine.QDRV_ENTRY,
        engine.WLAN_ENTRY,
        engine.START_ENTRY,
        engine.DRIVER_CONTRACT_ENTRY,
    ):
        if required not in seen:
            raise SystemExit(f"missing CPIO entry: {required}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {engine.PAD_ENTRY}")

    hashed_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == engine.HASHES_ENTRY:
            data, hashes_patch = f122.patch_hashes(entry.data, replacements)
            hashed_entries.append(f125.replace_entry(entry, data))
        else:
            hashed_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {engine.HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch

    interim = b"".join(f71.serialize_entry(entry) for entry in hashed_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F148 fixed-size padding cannot absorb delta={size_delta}")
    hashed_entries[pad_index] = f125.replace_entry(
        hashed_entries[pad_index], b"\0" * new_pad_size
    )

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in hashed_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    if (
        new_start != start
        or new_remainder != remainder
        or len(result) != len(raw)
        or len(result) - len(new_remainder) != old_cpio_end
    ):
        raise SystemExit("F148 changed fixed payload layout")

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
        "WLAN_SHA": NEW_WLAN_SHA,
    }
    try:
        for name, value in values.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    for path, expected in ((NEW_QDRV, NEW_QDRV_SHA), (NEW_WLAN, NEW_WLAN_SHA)):
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise SystemExit(f"F148 module missing or changed: {path}")
    compat = (ROOT / "work/linux510-radio-port/quantenna/qdrv/compat/include/openmitrastar_qdrv_compat.h").read_text(encoding="ascii")
    if "#define BR_SUBPORT_MAP(port) ((port) | 0x8000U)" not in compat:
        raise SystemExit("F148 mapped sub-port compatibility definition missing")

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
        "radio2g": "unchanged from F147",
        "radio5_start": "unchanged from F147 except qdrv integrity hash",
        "radio5_stop": "unchanged from F147",
        "radio5_modules": "qdrv.ko and wlan.ko replaced as one clean-build pair",
        "qdrv_wlan_contract": "both modules use mapped node indices with bit 0x8000",
        "queues_dma_rates_rings_forwarding_auc_tx": "behavior unchanged from F147",
        "bridge_topology": "unchanged from F147",
    }
    manifest["runtime_policy"] = {
        "subport_mapping": "IEEE80211 node index is mapped before AuC destination validation",
        "expected_effect": "send AP downlink to the associated station node instead of the VAP fallback node",
        "auc_submit_trace": "preserved from F147",
        "post_start_get": "preserved from F147",
        "hostlink_dma_free": "deferred from interrupt/IRQ-disabled context",
        "persistent_flash_writes": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

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
