#!/usr/bin/env python3
"""Offline contract checks for the composed Q1 RAM-only product."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/mission-state/q1-full-product"
BUILD = LANE / "build"
ROOTFS_BUILD = LANE / "rootfs-build"
BASE = "openmitrastar-linux510-q1-full-product-v1-RAM-ONLY"
EXPECTED_BASE_ROOTFS = "5d0536fa7917f47b0fe4f70ac90699dcb194f9ff3c98c4d9738531c0c6c404fa"
EXPECTED_RTL_MANIFEST = "c210392680a374e6b170456533141a8d1bc87a25042adbac6a7b178ea9fcb8e9"
EXPECTED_QTN_MANIFEST = "6f5b86911e45a08934049305589bdfb0cff488012936f162b9c826f4adddfca7"
EXPECTED_QDRV = "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20"
EXPECTED_HBM = "c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    rootfs_manifest = json.loads((ROOTFS_BUILD / "manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((BUILD / "manifest.json").read_text(encoding="utf-8"))
    image = BUILD / f"{BASE}.webformat.bin"
    require(rootfs_manifest["base_rootfs"]["sha256"] == EXPECTED_BASE_ROOTFS, "base rootfs drift")
    components = rootfs_manifest["components"]
    require(components["realtek_v4_manifest_sha256"] == EXPECTED_RTL_MANIFEST, "Realtek V4 drift")
    require(components["quantenna_module_manifest_sha256"] == EXPECTED_QTN_MANIFEST, "QTN manifest drift")
    require(components["qdrv_sha256"] == EXPECTED_QDRV, "qdrv drift")
    require(components["hbm_sha256"] == EXPECTED_HBM, "HBM drift")
    require(rootfs_manifest["runtime"]["management_ipv4"] == "192.168.1.90", "management IP drift")
    require(rootfs_manifest["runtime"]["management_port"] == 80, "OEM web port drift")
    require(rootfs_manifest["security"]["psk_bundled"] is False, "PSK bundled")
    require(rootfs_manifest["security"]["private_mac_bundled"] is False, "private MAC bundled")
    require(rootfs_manifest["security"]["watchdog_enabled"] is False, "watchdog enabled")
    require(candidate["profile"] == "Q1_FULL_PRODUCT", "wrong candidate profile")
    require(candidate["candidate_eligible"] is False, "RAM candidate promoted")
    require(candidate["flash_supported"] is False, "RAM candidate permits flash")
    require(candidate["private_build"] is False, "private build unexpectedly set")
    require(candidate["security"]["private_mac_bundled"] is False, "candidate private MAC bundled")
    require(candidate["security"]["secret_value_recorded"] is False, "candidate records a secret")
    require(candidate["security"]["missing_credentials_fail_closed"] is True, "candidate is not fail closed")
    require(candidate["completion_claims"] == {
        "full_product": False, "oem_parity_100": False, "radio2g": False, "radio5g": False
    }, "unsupported completion claim")
    require(candidate["capabilities"]["both_radios_fail_closed_without_credentials"] is True,
            "credential fail-closed gate missing")
    require(candidate["capabilities"]["watchdog_enabled"] is False, "candidate watchdog enabled")
    require(sha(image) == candidate["artifacts"]["webformat"]["sha256"], "candidate image hash mismatch")
    require(candidate["artifacts"]["webformat"]["bytes"] == image.stat().st_size, "candidate size mismatch")
    require(candidate["runtime_gates"]["exact_candidate_ram_boot"] == "pending", "hardware claim drift")
    require(candidate["runtime_gates"]["flash"] == "forbidden-by-classification", "flash classification drift")
    require(candidate["kernel_integration_gates"]["product_watchdog_canary"] is False, "WDT canary enabled")
    require(candidate["ram_only_layout"]["ranges_disjoint"] is True, "RAM ranges overlap")
    require(candidate["ram_only_layout"]["linux_live_slot_fit"] is False, "overslot classification lost")
    require(candidate["ram_only_layout"]["uimage_header_crc"] == "PASS", "header CRC not proven")
    require(candidate["ram_only_layout"]["uimage_data_crc"] == "PASS", "data CRC not proven")

    extract = ROOTFS_BUILD / "test-extract"
    if extract.exists():
        subprocess.run(["rm", "-rf", str(extract)], check=True)
    subprocess.run(["unsquashfs", "-no-progress", "-d", str(extract),
                    str(ROOTFS_BUILD / "openmitrastar-q1-full-product-rootfs-v1.squashfs")],
                   check=True, stdout=subprocess.DEVNULL)
    require(sha(extract / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko") ==
            "f58fd065903c946f601e368e0c2b269050ff41e90b6b1752e401d5a459af4a9d", "RTL module not V4")
    require(sha(extract / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko") ==
            EXPECTED_QDRV, "integrated qdrv mismatch")
    require(sha(extract / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hbm.ko") ==
            EXPECTED_HBM, "integrated HBM mismatch")
    require((extract / "usr/sbin/om-radio-credential-check").is_file(), "credential gate absent")
    require((extract / "usr/share/openmitrastar/radio5g/runtime-contract.json").is_file(), "5G contract absent")
    forbidden = list(extract.rglob("*.psk")) + list(extract.rglob("qtn-mac0addr"))
    require(not forbidden, f"secret-like files bundled: {forbidden}")
    subprocess.run(["rm", "-rf", str(extract)], check=True)

    print(
        "OMQ1_OFFLINE_TEST_PASS "
        f"image_sha256={sha(image)} bytes={image.stat().st_size} "
        "management=192.168.1.90:80 realtek=v4 qdrv=rxalign hbm=c5084d18 "
        "credentials=external watchdog=0 hardware_pass=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"OMQ1_OFFLINE_TEST_FAIL reason={exc}", file=sys.stderr)
        raise SystemExit(1)
