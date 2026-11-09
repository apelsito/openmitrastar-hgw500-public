#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = Path(
    os.environ.get(
        "OM_W2_2G_LANE",
        ROOT / "work/mission-state/w2-2g-parity-tx3-aelita-v1",
    )
)
BUILD = LANE / "build"
ROOTFS_BUILD = LANE / "rootfs-build"
VARIANT_SLUG = os.environ.get("OM_W2_2G_VARIANT_SLUG", "tx3")
STAGE = Path(
    os.environ.get(
        "OM_W2_2G_STAGE_A",
        "/home/user/openmitrastar-build/w2-2g-parity-tx3-aelita-v1/rootfs-a",
    )
)
BASE = os.environ.get(
    "OM_W2_2G_BASE",
    "openmitrastar-linux510-w2-2g-parity-tx3-v1-RAM-ONLY-NO-FLASH",
)
CLASSIFICATION = os.environ.get(
    "OM_W2_2G_CLASSIFICATION",
    "RAM-ONLY-W2-2G-PARITY-TX3-NO-FLASH",
)
COMPACT32 = os.environ.get("OM_W2_2G_COMPACT32", "1") == "1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_wsl_stage_path(path: Path) -> bool:
    return os.name == "nt" and path.as_posix().startswith("/home/")


def _wsl_bytes(path: Path) -> bytes:
    return subprocess.check_output(
        ["wsl.exe", "-e", "sh", "-lc", f"cat -- {shlex.quote(path.as_posix())}"]
    )


def _wsl_test_file(path: Path) -> bool:
    return (
        subprocess.run(
            ["wsl.exe", "-e", "sh", "-lc", f"test -f {shlex.quote(path.as_posix())}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _wsl_has_match(path: Path, pattern: str) -> bool:
    cmd = (
        f"find {shlex.quote(path.as_posix())} -maxdepth 1 "
        f"-name {shlex.quote(pattern)} -print -quit | grep -q ."
    )
    return (
        subprocess.run(
            ["wsl.exe", "-e", "sh", "-lc", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def artifact_text(path: Path) -> str:
    if path.exists():
        return path.read_text()
    if _is_wsl_stage_path(path):
        return _wsl_bytes(path).decode("utf-8")
    return path.read_text()


def artifact_bytes(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    if _is_wsl_stage_path(path):
        return _wsl_bytes(path)
    return path.read_bytes()


def artifact_is_file(path: Path) -> bool:
    if path.is_file():
        return True
    if _is_wsl_stage_path(path):
        return _wsl_test_file(path)
    return False


class W2TwoGParityCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUILD / "manifest.json").read_text())
        cls.rootfs_manifest = json.loads(
            (ROOTFS_BUILD / "manifest.json").read_text()
        )

    def test_ram_only_and_reproducible(self) -> None:
        fast = bool(self.manifest["reproducibility"].get("fast_iteration", False))
        self.assertEqual(
            self.manifest["classification"],
            CLASSIFICATION,
        )
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["flash_supported"])
        self.assertEqual(
            self.manifest["reproducibility"]["rootfs_two_builds_identical"],
            not fast,
        )
        self.assertEqual(
            self.manifest["reproducibility"]["kernel_two_isolated_builds_identical"],
            not fast,
        )
        self.assertEqual(
            self.manifest["reproducibility"]["lzma_two_encodes_identical"],
            not fast,
        )
        self.assertEqual(
            self.manifest["reproducibility"]["webformat_two_builds_identical"],
            not fast,
        )
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertEqual(self.manifest["slot"]["bootbase_contract"], "PASS")
        if fast:
            self.assertTrue(
                (
                    ROOTFS_BUILD
                    / f"openmitrastar-w2-2g-parity-{VARIANT_SLUG}-rootfs-v1.squashfs"
                ).is_file()
            )
        else:
            self.assertEqual(
                sha256(ROOTFS_BUILD / f"openmitrastar-w2-2g-parity-{VARIANT_SLUG}-rootfs-v1-a.squashfs"),
                sha256(ROOTFS_BUILD / f"openmitrastar-w2-2g-parity-{VARIANT_SLUG}-rootfs-v1-b.squashfs"),
            )

    def test_tx1_and_baseline_parameters(self) -> None:
        script = artifact_text(STAGE / "usr/sbin/om-radio-modules")
        self.assertIn("hgw500_tx_dma_wmb=1", script)
        self.assertIn("hgw500_tx_close_diag=1", script)
        self.assertIn(
            f"hgw500_txbd_compact32={1 if COMPACT32 else 0}", script
        )
        self.assertIn("hgw500_tx_ampdu_disable=0", script)
        self.assertIn("hgw500_honest_tx_ack=0", script)
        self.assertIn("debug_level=0", script)
        radio = self.manifest["radio2g"]
        self.assertTrue(radio["tx_dma_wmb"])
        all_queues = ["BK", "BE", "VI", "VO", "BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"]
        self.assertFalse(radio["txbd_compact32_data_queues_only"])
        self.assertEqual(COMPACT32, radio["txbd_compact32_global"])
        self.assertEqual(0 if COMPACT32 else 1, radio["txbd_hardware_width_bit15"])
        self.assertEqual(all_queues if COMPACT32 else [], radio["txbd_compact32_queues"])
        self.assertEqual([] if COMPACT32 else all_queues, radio["txbd_preserved_64_queues"])
        self.assertEqual(COMPACT32, radio["txbd_oem_parity_claim"])
        self.assertEqual(radio["ampdu_policy"], "baseline")
        self.assertEqual(radio["ack_policy"], "baseline")

    def test_secure_credential_contract_without_secret(self) -> None:
        radio = self.manifest["radio2g"]
        self.assertEqual(radio["ssid"], "OpenMitraStar-2G-DIAG")
        self.assertEqual(radio["security"], "OPEN-DIAGNOSTIC")
        self.assertFalse(radio["uses_psk"])
        self.assertEqual(radio["final_secure_capability"]["security"], "WPA2-PSK-CCMP")
        self.assertEqual(
            radio["final_secure_capability"]["psk_source"],
            "current-unit-mtd5-read-only-to-tmpfs-0600",
        )
        self.assertFalse(self.manifest["security"]["psk_bundled"])
        serialized = json.dumps(self.manifest)
        self.assertNotRegex(serialized, r"wpa_passphrase\s*=\s*[^$\s]")
        diag = artifact_text(STAGE / "usr/sbin/om-radio2g-diag-start")
        self.assertIn("ssid=OpenMitraStar-2G-DIAG", diag)
        self.assertIn("'wpa=0'", diag)
        self.assertNotIn("wpa_passphrase=", diag)
        self.assertIn("om_wlan2g_led off", diag)
        self.assertIn("om_wlan2g_led on", diag)
        stop = artifact_text(STAGE / "usr/sbin/om-radio-stop")
        self.assertIn("openmitrastar:green:wlan2g/brightness", stop)
        self.assertIn("printf '0\\n'", stop)
        self.assertTrue(artifact_is_file(STAGE / "usr/sbin/om-origin-import"))
        self.assertTrue(artifact_is_file(STAGE / "usr/sbin/om-radio-start"))

    def test_network_and_control_contract(self) -> None:
        radio = self.manifest["radio2g"]
        self.assertEqual(radio["bridge"], "br0:eth0+wlan0")
        self.assertEqual(radio["dhcp"], "upstream-pass-through")
        self.assertFalse(radio["local_dhcp_server"])
        self.assertFalse(radio["nat"])
        self.assertTrue(radio["led_gpio11_active_low"])
        self.assertEqual(radio["button_gpio2"]["short"], "none")
        self.assertEqual(radio["button_gpio2"]["long_ms"], 5000)
        self.assertEqual(radio["button_daemon"], "/usr/sbin/om-buttond")
        buttond = artifact_bytes(STAGE / "usr/sbin/om-buttond")
        self.assertTrue(buttond.startswith(b"\x7fELF"))
        self.assertIn(b"buttond-start", buttond)
        buttond_init = artifact_text(STAGE / "etc/init.d/S52-buttond")
        self.assertIn("/usr/sbin/om-buttond /dev/input/event0", buttond_init)
        self.assertEqual(radio["wps2g"], "absent-current-unit-contract")
        self.assertFalse(self.manifest["security"]["wps2g_enabled"])
        self.assertIn(
            "om-radio2g-diag-start",
            artifact_text(STAGE / "etc/init.d/S50-radio-ap"),
        )
        feature_dir = STAGE / "etc/openmitrastar/features"
        if feature_dir.exists():
            self.assertFalse(any(feature_dir.glob("q3-radio5-*")))
        elif _is_wsl_stage_path(feature_dir):
            self.assertFalse(_wsl_has_match(feature_dir, "q3-radio5-*"))
        else:
            self.fail(f"missing feature directory: {feature_dir}")
        defaults = (
            STAGE / "usr/share/openmitrastar/config-schema/v1/defaults.conf"
        )
        defaults_text = artifact_text(defaults)
        self.assertIn("RADIO2G_SSID=OpenMitraStar-2G-DIAG", defaults_text)
        self.assertIn("RADIO5G_ENABLE=0", defaults_text)
        dtb = artifact_bytes(BUILD / f"{BASE}.dtb")
        vmlinux = artifact_bytes(BUILD / f"{BASE}.vmlinux")
        self.assertIn(b"mitrastar,wlan2g-led-active-low", dtb)
        self.assertIn(b"mitrastar,wifi-short-action-none", dtb)
        self.assertIn(b"GPIO2 long press: userspace 2.4 GHz toggle transaction requested", vmlinux)

    def test_hardware_completion_is_not_claimed(self) -> None:
        gates = self.manifest["runtime_gates"]
        for key in (
            "exact_image_ram_boot",
            "origin_psk_import",
            "wpa2_client_association",
            "upstream_dhcp_client",
            "dns_and_https_from_client",
            "bidirectional_min_5_mbps",
            "directional_ratio_min_0_5",
            "be_queue_max_below_384",
            "ten_minute_soak",
        ):
            self.assertIn("PENDING", gates[key])
        self.assertEqual(gates["flash"], "FORBIDDEN")

    def test_artifact_hashes(self) -> None:
        for key in ("initramfs", "config", "vmlinux", "uimage", "dtb", "webformat"):
            item = self.manifest["artifacts"][key]
            path = BUILD / item["file"]
            self.assertEqual(path.stat().st_size, item["bytes"])
            self.assertEqual(sha256(path), item["sha256"])


if __name__ == "__main__":
    unittest.main()
