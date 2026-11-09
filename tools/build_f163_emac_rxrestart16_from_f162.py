#!/usr/bin/env python3
"""Build F163 from F162 by reducing the EMAC RX restart threshold 63 -> 16."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f103_emac_rxrestart_63pokes_from_f101 as engine
import build_f71_qcsapi_interp_from_f70 as f71
import build_f162_2g_tqe_readonly_from_f157 as f162


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f163-emac-rxrestart16-from-f162"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
SRC_BUILD = f162.OUT
SRC_BASE = f162.BASE_OUT

OLD_CONTEXT = bytes.fromhex("aa1500161108d50f4a2300204a22002093010000")
NEW_CONTEXT = bytes.fromhex("aa150016110815044a2300204a22002093010000")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_one(blob: bytes, label: str) -> tuple[bytes, dict[str, object]]:
    count = blob.count(OLD_CONTEXT)
    if count != 1:
        raise SystemExit(f"{label}: expected one F162 threshold context, found {count}")
    offset = blob.find(OLD_CONTEXT)
    patched = blob[:offset] + NEW_CONTEXT + blob[offset + len(OLD_CONTEXT):]
    return patched, {
        "label": label,
        "offset": offset,
        "old_context_hex": OLD_CONTEXT.hex(),
        "new_context_hex": NEW_CONTEXT.hex(),
        "old_same_cur_rx_pokes": 63,
        "new_same_cur_rx_pokes": 16,
        "old_approx_trigger_ms": 15750,
        "new_approx_trigger_ms": 4000,
        "old_sha256": sha256(blob),
        "new_sha256": sha256(patched),
        "bytes": len(blob),
        "delta_bytes": 0,
    }


@contextlib.contextmanager
def variant_context():
    names = ("BUILD_TAG", "OUT", "BASE_OUT", "SRC_BUILD", "SRC_BASE", "OLD_CONTEXT", "NEW_CONTEXT", "patch_one")
    old = {name: getattr(engine, name) for name in names}
    values = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "SRC_BUILD": SRC_BUILD,
        "SRC_BASE": SRC_BASE,
        "OLD_CONTEXT": OLD_CONTEXT,
        "NEW_CONTEXT": NEW_CONTEXT,
        "patch_one": patch_one,
    }
    try:
        for name, value in values.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    with variant_context():
        rc = engine.main()
    if rc:
        return rc

    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_bytes = source_raw.read_bytes()
    candidate_bytes = raw_path.read_bytes()
    cpio_start, _entries, source_remainder = f71.parse_first_cpio(source_bytes)
    new_cpio_start, _new_entries, candidate_remainder = f71.parse_first_cpio(candidate_bytes)
    cpio_end = len(source_bytes) - len(source_remainder)
    changed_offsets = [
        index for index, (old, new) in enumerate(zip(source_bytes, candidate_bytes))
        if old != new
    ]
    manifest_offset = source_bytes.find(OLD_CONTEXT)
    expected_offsets = [
        manifest_offset + index
        for index, (old, new) in enumerate(zip(OLD_CONTEXT, NEW_CONTEXT))
        if old != new
    ]
    contract = {
        "schema": "openmitrastar.kernel-fixed-size-entry-contract/v1",
        "result": "PASS" if (
            len(source_bytes) == len(candidate_bytes)
            and cpio_start == new_cpio_start
            and source_bytes[:cpio_end] == candidate_bytes[:cpio_end]
            and changed_offsets == expected_offsets
            and candidate_remainder.count(NEW_CONTEXT) == 1
            and candidate_remainder.count(OLD_CONTEXT) == 0
        ) else "FAIL",
        "checks": {
            "raw_bytes_match": len(source_bytes) == len(candidate_bytes),
            "cpio_start_match": cpio_start == new_cpio_start,
            "cpio_unchanged": source_bytes[:cpio_end] == candidate_bytes[:cpio_end],
            "changed_offsets_exact": changed_offsets == expected_offsets,
            "new_context_once": candidate_remainder.count(NEW_CONTEXT) == 1,
            "old_context_absent": candidate_remainder.count(OLD_CONTEXT) == 0,
        },
        "changed_offsets": changed_offsets,
    }
    entry_path = OUT / "kernel-entry-contract.json"
    entry_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="ascii")
    if contract["result"] != "PASS":
        raise SystemExit("F163 kernel fixed-size entry contract failed")

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest["schema"] = "openmitrastar.q3-persistent-composite-f163-emac-rxrestart16-from-f162/v1"
    manifest["classification"] = "F163_FROM_F162_EMAC_RXRESTART_THRESHOLD_16POKES_FIXEDSIZE"
    manifest["change_scope"] = {
        "base": "F162 dual-radio with read-only TQE counters",
        "kernel_emac": "one fixed-size ARC branch immediate: RX restart threshold 63 -> 16 pokes",
        "radio2g_radio5_modules": "unchanged byte-for-byte from F162",
        "queues_dma_rates_rings_forwarding_bridge": "unchanged",
        "flash_layout": "unchanged",
    }
    manifest["runtime_policy"] = {
        "poll_interval_ms": 10,
        "stall_poke_interval_ms": 250,
        "restart_threshold_pokes": 16,
        "approx_restart_after_stall_ms": 4000,
        "restart_cooldown_ms": 10000,
        "expected_effect": "recover a proven eth0 RX DMA stall before TCP times out",
    }
    manifest["persistent_entry_contract"] = {"file": entry_path.name, "result": "PASS"}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    result_path = OUT / "build-result.json"
    result = json.loads(result_path.read_text(encoding="ascii"))
    result["schema"] = "openmitrastar.f163-emac-rxrestart16-from-f162-build/v1"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sum_paths = [path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS"]
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sorted(sum_paths)),
        encoding="ascii",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
