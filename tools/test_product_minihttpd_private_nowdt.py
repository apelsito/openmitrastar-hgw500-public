#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "work/mission-state/f3-product-minihttpd-private-nowdt/build"
BASE = "openmitrastar-linux510-product-minihttpd-posix-private-nowdt-v1"
MANIFEST = BUILD / "manifest.json"
CONTRACT = BUILD / "bootbase-contract.json"
ROOTFS_MANIFEST = ROOT / "work/mission-state/w4-rootfs-product/build/manifest.json"
TFTP = ROOT / "work/tftp/omvl/linux510-product-minihttpd-posix-private-nowdt-v1-RAM-ONLY.bin"
RECEIVER_SHA256 = "588a917d1c3d77a757e800fbb04db7661a52799d4309cb1753afcd7f9617d3b5"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rootfs = json.loads(ROOTFS_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["private_build"] is True
    assert manifest["security"]["psk_bundled"] is True
    assert manifest["security"]["ssh_key_only"] is True
    assert manifest["product_watchdog"]["enabled"] is False
    assert manifest["kernel_integration_gates"]["posix_timers"] is True
    assert manifest["kernel_integration_gates"]["product_watchdog_canary"] is False
    assert manifest["source_rootfs"]["sha256"] == rootfs["rootfs"]["sha256"]
    assert manifest["source_rootfs_manifest_sha256"] == sha(ROOTFS_MANIFEST)
    assert manifest["cgi_runtime"]["firmware_receiver_sha256"] == RECEIVER_SHA256
    assert manifest["cgi_runtime"]["mini_httpd_sha256"] == rootfs["inputs"]["cgi_mini_httpd_sha256"]
    assert manifest["cgi_runtime"]["dispatcher_sha256"] == rootfs["inputs"]["cgi_dispatcher_sha256"]
    assert manifest["offline_gates"]["hardware_ram_boot_exact_image"] == "pending"
    assert all(manifest["reproducibility"].values())
    assert contract["accepted_by_contract"] is True and contract["errors"] == []

    for name, artifact in manifest["artifacts"].items():
        path = TFTP if name == "tftp_copy" else BUILD / artifact["file"]
        assert path.is_file(), name
        assert path.stat().st_size == artifact["bytes"], name
        assert sha(path) == artifact["sha256"], name
    assert manifest["artifacts"]["webformat"]["bytes"] < 0x7A0000
    assert sha(TFTP) == manifest["artifacts"]["tftp_copy"]["sha256"]

    with tempfile.TemporaryDirectory(prefix="om-private-nowdt-") as directory:
        target = Path(directory)
        with (BUILD / f"{BASE}.initramfs.cpio").open("rb") as source:
            result = subprocess.run(
                ["cpio", "--extract", "--make-directories", "--preserve-modification-time"],
                cwd=target,
                stdin=source,
                capture_output=True,
            )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        receiver = target / "usr/libexec/openmitrastar/om-firmware-recv"
        assert sha(receiver) == RECEIVER_SHA256
        assert stat.S_IMODE(receiver.stat().st_mode) == 0o755
        psk = target / "persist/openmitrastar/wifi/wpa2.psk"
        assert psk.is_file() and psk.stat().st_size > 1
        assert stat.S_IMODE(psk.stat().st_mode) == 0o600
        assert (target / "usr/sbin/mini_httpd").is_file()
        assert (target / "usr/libexec/openmitrastar/om-oem-cgi").is_file()
        assert (target / "usr/sbin/om-firmware-stage").is_file()

    print(
        "OMPRODUCT_PRIVATE_NOWDT_TEST_PASS "
        f"image_sha256={manifest['artifacts']['webformat']['sha256']} "
        f"image_bytes={manifest['artifacts']['webformat']['bytes']} "
        f"rootfs_sha256={manifest['source_rootfs']['sha256']} "
        f"receiver_sha256={RECEIVER_SHA256} repro=2/2 watchdog=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
