#!/usr/bin/env python3
"""Offline identity and safety audit for the TX9 global32/RX-unaligned RAM candidate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/mission-state/w2-2g-parity-tx9-global32-rx-unaligned-v1"
BUILD = LANE / "build"
ROOTFS_BUILD = LANE / "rootfs-build"
BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/w2-tx9-global32-rx-unaligned-RAM-ONLY-NO-FLASH"
IMAGE = ROOT / "work/tftp/omvl/linux510-w2-2g-parity-tx9-global32-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin"
EXPECTED_SHA256 = "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a"
EXPECTED_BYTES = 4_329_980
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

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"id": name, "ok": bool(ok), "detail": detail})

    required = {
        "image": IMAGE,
        "manifest": BUILD / "manifest.json",
        "bootbase_contract": BUILD / "bootbase-contract.json",
        "checksums": BUILD / "W2_2G_SHA256SUMS",
        "rootfs_manifest": ROOTFS_BUILD / "manifest.json",
        "bundle_manifest": BUNDLE / "manifest.json",
    }
    for name, path in required.items():
        check(f"exists.{name}", path.is_file(), str(path))
    if not all(path.is_file() for path in required.values()):
        rendered = {"schema": "openmitrastar.w2-tx9-candidate-audit/v1", "status": "FAIL", "checks": checks}
        print(json.dumps(rendered, indent=2, sort_keys=True))
        return 1

    manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
    bootbase = json.loads(required["bootbase_contract"].read_text(encoding="utf-8"))
    rootfs = json.loads(required["rootfs_manifest"].read_text(encoding="utf-8"))
    bundle = json.loads(required["bundle_manifest"].read_text(encoding="utf-8"))

    actual_size = IMAGE.stat().st_size
    actual_sha = sha256(IMAGE)
    tftp = manifest.get("artifacts", {}).get("tftp_copy", {})
    slot = manifest.get("slot", {})
    radio = manifest.get("radio2g", {})
    experiments = bundle.get("experiments", {})
    compact = experiments.get("hgw500_txbd_compact32", {})
    rx_unaligned = experiments.get("hgw500_rx_unaligned_header", {})

    check("image.bytes", actual_size == EXPECTED_BYTES == tftp.get("bytes"), f"actual={actual_size}")
    check("image.sha256", actual_sha == EXPECTED_SHA256 == tftp.get("sha256"), actual_sha)
    check("image.name", tftp.get("file") == IMAGE.name, str(tftp.get("file")))
    check(
        "manifest.classification",
        manifest.get("classification") == "RAM-ONLY-W2-2G-PARITY-TX9-GLOBAL32-RX-UNALIGNED-NO-FLASH",
        str(manifest.get("classification")),
    )
    check("manifest.profile", manifest.get("profile") == "W2_2G_TX9_GLOBAL32_RX_UNALIGNED_OPEN_DIAG", str(manifest.get("profile")))
    check("manifest.candidate_eligible.false", manifest.get("candidate_eligible") is False, repr(manifest.get("candidate_eligible")))
    check("manifest.flash_supported.false", manifest.get("flash_supported") is False, repr(manifest.get("flash_supported")))
    check("slot.name", slot.get("name") == "linux_live", str(slot.get("name")))
    check("slot.bytes", slot.get("bytes") == SLOT_BYTES, str(slot.get("bytes")))
    check("slot.candidate_bytes", slot.get("candidate_bytes") == actual_size, str(slot.get("candidate_bytes")))
    check("slot.fits", slot.get("fits") is True and actual_size <= SLOT_BYTES, f"candidate={actual_size} slot={SLOT_BYTES}")
    check("slot.bootbase_contract", slot.get("bootbase_contract") == "PASS", str(slot.get("bootbase_contract")))

    check("radio.compact32.global", radio.get("txbd_compact32_global") is True, repr(radio.get("txbd_compact32_global")))
    check("radio.compact32.data_only.false", radio.get("txbd_compact32_data_queues_only") is False, repr(radio.get("txbd_compact32_data_queues_only")))
    check("radio.width_bit15.clear", radio.get("txbd_hardware_width_bit15") == 0, str(radio.get("txbd_hardware_width_bit15")))
    check("radio.rx_bridge.open_diag", radio.get("ssid") == "OpenMitraStar-2G-DIAG" and radio.get("security") == "OPEN-DIAGNOSTIC", f"ssid={radio.get('ssid')} security={radio.get('security')}")

    check("bootbase.accepted", bootbase.get("accepted_by_contract") is True, repr(bootbase.get("accepted_by_contract")))
    check("bootbase.candidate_eligible.false", bootbase.get("candidate_eligible") is False, repr(bootbase.get("candidate_eligible")))
    check("bootbase.errors.empty", bootbase.get("errors") == [], repr(bootbase.get("errors")))
    check("bootbase.kind", bootbase.get("kind") == "bootbase-oem-ras-slot", str(bootbase.get("kind")))
    check("bootbase.identity", bootbase.get("sha256") == actual_sha and bootbase.get("size") == actual_size, f"sha={bootbase.get('sha256')} size={bootbase.get('size')}")
    check("bootbase.arch.arc", bootbase.get("header", {}).get("arch") == 19, str(bootbase.get("header", {}).get("arch")))
    check("bootbase.compression.lzma", bootbase.get("header", {}).get("compression") == 3, str(bootbase.get("header", {}).get("compression")))
    check("bootbase.scope.ram_only", "RAM-only" in str(bootbase.get("scope_note")), str(bootbase.get("scope_note")))

    check("rootfs.candidate_eligible.false", rootfs.get("candidate_eligible") is False, repr(rootfs.get("candidate_eligible")))
    check("rootfs.flash_supported.false", rootfs.get("flash_supported") is False, repr(rootfs.get("flash_supported")))
    check("rootfs.hardware_actions.false", rootfs.get("hardware_actions") is False, repr(rootfs.get("hardware_actions")))
    check("rootfs.network_actions.false", rootfs.get("network_actions") is False, repr(rootfs.get("network_actions")))

    check("bundle.candidate_eligible.false", bundle.get("candidate_eligible") is False, repr(bundle.get("candidate_eligible")))
    check("bundle.rx_unaligned.present", bool(rx_unaligned), "experiment manifest entry")
    check("bundle.rx_unaligned.static_pass", bundle.get("static_gates", {}).get("hgw500_rx_unaligned_header") == "PASS", str(bundle.get("static_gates", {}).get("hgw500_rx_unaligned_header")))
    check("bundle.compact32.present", bool(compact), "experiment manifest entry")
    check("bundle.compact32.global32", compact.get("hybrid_layout") is False and compact.get("txbd_entry_bytes") == 32, f"hybrid={compact.get('hybrid_layout')} bytes={compact.get('txbd_entry_bytes')}")
    check("bundle.compact32.desc_clear", compact.get("recycled_tx_descriptor_cleared") is True, repr(compact.get("recycled_tx_descriptor_cleared")))
    check("bundle.compact32.static_pass", bundle.get("static_gates", {}).get("hgw500_txbd_global_width_bit") == "PASS", str(bundle.get("static_gates", {}).get("hgw500_txbd_global_width_bit")))
    safety = bundle.get("safety", {})
    check("bundle.safety.no_router", safety.get("router_accessed") is False, repr(safety.get("router_accessed")))
    check("bundle.safety.no_uart", safety.get("uart_used") is False, repr(safety.get("uart_used")))
    check("bundle.safety.no_network", safety.get("network_used") is False, repr(safety.get("network_used")))
    check("bundle.safety.no_flash", safety.get("flash_supported") is False, repr(safety.get("flash_supported")))

    checksum_failures: list[str] = []
    checksum_entries = 0
    for line in required["checksums"].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, raw_path = line.split(None, 1)
        path = checksum_path(raw_path)
        checksum_entries += 1
        if not path.is_file() or sha256(path) != expected:
            checksum_failures.append(str(path))
    check("checksums.all", not checksum_failures, f"entries={checksum_entries} failures={checksum_failures}")

    failed = [item["id"] for item in checks if not item["ok"]]
    result = {
        "schema": "openmitrastar.w2-tx9-candidate-audit/v1",
        "status": "PASS" if not failed else "FAIL",
        "classification": "OFFLINE-RAM-ONLY-NO-FLASH-CANDIDATE-AUDIT",
        "image": {"path": str(IMAGE), "bytes": actual_size, "sha256": actual_sha},
        "slot": {"name": "linux_live", "bytes": SLOT_BYTES, "fits": actual_size <= SLOT_BYTES},
        "bootbase_contract": "PASS" if bootbase.get("accepted_by_contract") is True else "FAIL",
        "candidate_eligible": False,
        "flash_supported": False,
        "failed_checks": failed,
        "checks": checks,
        "hardware_actions": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
