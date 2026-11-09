#!/usr/bin/env python3
"""Offline identity/safety audit for the current TX10 RAM image."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = Path(os.environ.get("OM_W2_2G_LANE", ROOT / "work/mission-state/w2-2g-parity-tx10-controls-v1"))
BUILD = LANE / "build"
BUNDLE = Path(os.environ.get("OM_W2_2G_REALTEK_BUNDLE", ROOT / "outputs/kernel-port/realtek-loop/w2-tx10-rx-signal-safe-v2-RAM-ONLY-NO-FLASH"))
IMAGE = Path(os.environ.get("OM_W2_2G_TFTP", ROOT / "work/tftp/omvl/linux510-w2-2g-parity-tx10-controls-v1-RAM-TEST-NO-FLASH.bin"))
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
EXPECTED_SHA256 = os.environ.get("OM_W2_2G_EXPECTED_IMAGE_SHA256", "998510e1aeabef6e51f953c33533a9b714251dbb5b52062d5eaa112aa431e7ee")
EXPECTED_BYTES = int(os.environ.get("OM_W2_2G_EXPECTED_IMAGE_BYTES", "4331206"))
EXPECTED_CLASSIFICATION = os.environ.get("OM_W2_2G_CLASSIFICATION", "RAM-ONLY-W2-2G-PARITY-TX10-CONTROLS-NO-FLASH")
EXPECTED_PROFILE = os.environ.get("OM_W2_2G_PROFILE", "W2_2G_TX10_RX_SIGNAL_SAFE_CONTROLS_OPEN_DIAG")
SLOT_BYTES = 7_995_392


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checksum_path(raw: str) -> Path:
    normalized = raw.strip().replace("\\", "/")
    if normalized.startswith("/mnt/c/"):
        return Path("C:/" + normalized[len("/mnt/c/"):])
    return Path(normalized)


def main() -> int:
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: object) -> None:
        checks.append({"id": name, "ok": bool(ok), "detail": str(detail)})

    required = {
        "image": IMAGE,
        "manifest": BUILD / "manifest.json",
        "bootbase": BUILD / "bootbase-contract.json",
        "checksums": BUILD / "W2_2G_SHA256SUMS",
        "bundle_manifest": BUNDLE / "manifest.json",
        "rtl8192ee": BUNDLE / "modules/rtl8192ee.ko",
        "source": TRX,
    }
    for name, path in required.items():
        check(f"exists.{name}", path.is_file(), path)
    if not all(path.is_file() for path in required.values()):
        print(json.dumps({"status": "FAIL", "checks": checks}, indent=2))
        return 1

    manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
    bootbase = json.loads(required["bootbase"].read_text(encoding="utf-8"))
    bundle = json.loads(required["bundle_manifest"].read_text(encoding="utf-8"))
    source = TRX.read_text(encoding="utf-8")
    signal_start = source.index("static void _rtl92ee_translate_rx_signal_stuff")
    signal_end = source.index("static void _rtl92ee_insert_emcontent")
    signal_body = source[signal_start:signal_end]

    image_sha = sha256(IMAGE)
    image_bytes = IMAGE.stat().st_size
    artifact = manifest["artifacts"]["tftp_copy"]
    slot = manifest["slot"]
    components = manifest["components"]
    signal = bundle["experiments"].get("hgw500_rx_unaligned_signal", {})

    check("image.sha256", image_sha == EXPECTED_SHA256 == artifact.get("sha256"), image_sha)
    check("image.bytes", image_bytes == EXPECTED_BYTES == artifact.get("bytes"), image_bytes)
    check("image.name", artifact.get("file") == IMAGE.name, artifact.get("file"))
    check("manifest.classification", manifest.get("classification") == EXPECTED_CLASSIFICATION, manifest.get("classification"))
    check("manifest.profile", manifest.get("profile") == EXPECTED_PROFILE, manifest.get("profile"))
    check("manifest.not_flashable", manifest.get("candidate_eligible") is False and manifest.get("flash_supported") is False, (manifest.get("candidate_eligible"), manifest.get("flash_supported")))
    check("slot.fits", slot.get("fits") is True and slot.get("bytes") == SLOT_BYTES and slot.get("candidate_bytes") == image_bytes, slot)
    check("bootbase.accepted", bootbase.get("accepted_by_contract") is True and bootbase.get("errors") == [], bootbase.get("errors"))
    check("bootbase.identity", bootbase.get("sha256") == image_sha and bootbase.get("size") == image_bytes, (bootbase.get("sha256"), bootbase.get("size")))
    check("bundle.identity", components.get("realtek_bundle_manifest_sha256") == sha256(required["bundle_manifest"]), components.get("realtek_bundle_manifest_sha256"))
    check("module.identity", components.get("rtl8192ee_sha256") == sha256(required["rtl8192ee"]), components.get("rtl8192ee_sha256"))
    check("signal.gate", bundle.get("static_gates", {}).get("hgw500_rx_unaligned_signal") == "PASS", bundle.get("static_gates", {}).get("hgw500_rx_unaligned_signal"))
    check("signal.copy", signal.get("aligned_header_copy") is True and signal.get("raw_rx_frame_unchanged") is True, signal)
    check("source.hgw_guard", 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in signal_body, "HGW-only")
    check("source.header_copy", "memcpy(&local_hdr, tmp_buf, copy_len);" in signal_body, "aligned local header")
    check("source.qos_safe", "ieee80211_is_data_qos(fc)" in signal_body and "(struct ieee80211_qos_hdr *)hdr" in signal_body, "fc+aligned qos header")
    check("source.no_qos_raw", "ieee80211_is_data_qos(hdr->frame_control)" not in signal_body and "(struct ieee80211_qos_hdr *)tmp_buf" not in signal_body, "no raw odd qos reads")
    check("module.marker", b"OMRTLRXALIGN stage=signal-safe target=hgw500" in required["rtl8192ee"].read_bytes(), "marker present")

    checksum_failures: list[str] = []
    entries = 0
    for line in required["checksums"].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, raw_path = line.split(None, 1)
        path = checksum_path(raw_path)
        entries += 1
        if not path.is_file() or sha256(path) != expected:
            checksum_failures.append(str(path))
    check("checksums.all", not checksum_failures, f"entries={entries} failures={checksum_failures}")

    failed = [item["id"] for item in checks if not item["ok"]]
    result = {
        "schema": "openmitrastar.w2-tx10-candidate-audit/v1",
        "status": "PASS" if not failed else "FAIL",
        "classification": "OFFLINE-RAM-ONLY-NO-FLASH",
        "image": {"path": str(IMAGE), "bytes": image_bytes, "sha256": image_sha},
        "slot": {
            "bytes": SLOT_BYTES,
            "candidate_bytes": image_bytes,
            "spare_bytes": SLOT_BYTES - image_bytes,
            "fits": image_bytes <= SLOT_BYTES,
        },
        "failed_checks": failed,
        "checks": checks,
        "hardware_actions": False,
        "flash_supported": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
