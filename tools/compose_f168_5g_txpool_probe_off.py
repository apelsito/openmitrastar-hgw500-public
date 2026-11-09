#!/usr/bin/env python3
"""Compose the offline F168-5G candidate from F167 kernel and gated qdrv."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs/kernel-port/f168-5g-txpool-probe-off-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f168-5g-txpool-probe-off/build"
BASE = "openmitrastar-linux510-q3-persistent-f168-5g-txpool-probe-off-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def variant_context():
    old = engine.ASSETS, engine.OUT, engine.BASE
    try:
        engine.ASSETS, engine.OUT, engine.BASE = ASSETS, OUT, BASE
        yield
    finally:
        engine.ASSETS, engine.OUT, engine.BASE = old


def main() -> int:
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    path = OUT / "manifest.json"
    manifest = json.loads(path.read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f168-5g-txpool-probe-off/v1",
        "classification": "F168_5G_TXPOOL_PROBE_DEFAULT_OFF_OFFLINE_CANDIDATE",
        "candidate_eligible": False,
        "flash_supported": False,
        "change_scope": {
            "base": "installed F167",
            "kernel_emac": "byte-identical to F167",
            "radio5_qdrv": "gate F155 HBM pool MMIO sampling behind a default-off read-only module parameter",
            "radio5_behavior": "GSO segmentation, RX inactivity refresh, auc_tx, tx_ba_disable=1, WPA2, ES region and bridge unchanged",
            "wlan_auc_muc_tqe_hbm_fwt": "wlan and firmware byte-identical; TQE/HBM behavior unchanged; fwt_ctrl remains unloaded",
        },
        "hypothesis": {
            "claim": "removing two HBM availability MMIO reads from every AuC submission can reduce host-path overhead/jitter",
            "evidence": "all captured F157-F167 qdrv counters report openmitrastar_auc_busy_total=0 while GSO drops remain 0",
            "physical_proof_required": True,
        },
        "physical_gate": {
            "script": "tools/run_f168_5g_physical_gate.ps1",
            "runs": 3,
            "duration_seconds_each": 300,
            "transfer_mib_each_direction": 32,
            "acceptance": "all runs PASS; zero disconnects/fatals/AuC busy/GSO drops; no WPA2, ES-region, bridge, management or 2.4 GHz regression; measurable median gain versus F167",
        },
        "source": {
            "firmware": "F167",
            "kernel": "byte-identical F167 kernel",
            "rootfs": "F167 SquashFS with only qdrv and integrity metadata replaced",
        },
    })
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
