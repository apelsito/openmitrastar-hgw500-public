#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "work/mission-state/w4-rootfs-product"
IMPORTER = PRODUCT / "rootfs/usr/sbin/om-origin-import"
CONFIG_PREPARE = PRODUCT / "rootfs/usr/sbin/om-config-prepare"
DEFAULTS = PRODUCT / "rootfs/usr/share/openmitrastar/config-schema/v1/defaults.conf"
POLICY = PRODUCT / "rootfs/usr/share/openmitrastar/origin-mtd5/current-unit.policy"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
FRAGMENT = PRODUCT / "kernel/topaz-product-rootfs.fragment"
CURRENT_MTD5 = (
    ROOT
    / "outputs/flash-backups/hgw500-physical-ssh-20260820/current-unit"
    / "hgw500_mtdblock5.bin"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def to_wsl(path: Path) -> str:
    if os.name != "nt":
        return str(path.resolve())
    value = str(path.resolve()).replace("\\", "/")
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/mnt/{value[0].lower()}/{value[3:]}"
    return value


def run_wsl_script(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assignments = [
        f"{key}={to_wsl(Path(value)) if key != 'OM_ORIGIN_TEST_MODE' else value}"
        for key, value in env.items()
        if key.startswith("OM_")
    ]
    if os.name != "nt":
        command = ["env", *assignments, "sh", to_wsl(script)]
    else:
        command = [
            "wsl.exe",
            "-d",
            "podman-mem9-tidb",
            "-u",
            "root",
            "-e",
            "env",
            *assignments,
            "sh",
            to_wsl(script),
        ]
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
    )


def policy_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


class OriginMtd5ReadOnlyTest(unittest.TestCase):
    def test_kernel_lane_is_fixed_read_only_and_arc_safe(self) -> None:
        dts = DTS.read_text(encoding="utf-8")
        fragment = FRAGMENT.read_text(encoding="utf-8")
        self.assertIn('origin_data: flash@90f80000', dts)
        self.assertIn('compatible = "mtd-rom";', dts)
        self.assertIn('reg = <0x90f80000 0x00080000>;', dts)
        self.assertIn('linux,mtd-name = "data";', dts)
        self.assertIn('no-unaligned-direct-access;', dts)
        self.assertNotIn('compatible = "cfi-flash";', dts)
        for required in (
            "CONFIG_MTD_ROM=y",
            "CONFIG_MTD_PHYSMAP=y",
            "CONFIG_MTD_PHYSMAP_OF=y",
            "# CONFIG_MTD_BLOCK is not set",
            "CONFIG_MTD_BLOCK_RO=y",
            "CONFIG_JFFS2_FS=y",
        ):
            self.assertIn(required, fragment)

    def test_userspace_has_no_flash_mutation_path(self) -> None:
        text = IMPORTER.read_text(encoding="utf-8")
        for forbidden in (
            "flashcp",
            "flash_erase",
            "mtd_debug",
            "MEMERASE",
            "openmitrastar.persist=rw",
            "mount -o remount,rw",
            "dd of=",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("jffs2-magic", text)
        self.assertIn("hash-mismatch", text)
        self.assertIn("config-model-mismatch", text)
        self.assertIn("psk-source-mismatch", text)
        self.assertIn("secrets=redacted", text)

    def make_fixture(self, root: Path, *, policy_hash: str | None = None) -> tuple[dict[str, str], str]:
        dev = root / "dev"
        persist = root / "persist"
        runtime_parent = root / "run/openmitrastar"
        state = root / "state"
        for directory in (dev, persist, runtime_parent, state):
            directory.mkdir(parents=True, exist_ok=True)

        raw = bytearray(b"\x85\x19")
        raw.extend(bytes((index * 17 + 3) & 0xFF for index in range(524286)))
        raw_bytes = bytes(raw)
        (dev / "mtd5").write_bytes(raw_bytes)
        (dev / "mtdblock5").write_bytes(b"")
        (root / "proc-mtd").write_bytes((
            'dev:    size   erasesize  name\n'
            'mtd5: 00080000 00010000 "data"\n'
        ).encode("ascii"))
        (root / "proc-mounts").write_bytes(
            f"/dev/mtdblock5 {to_wsl(persist)} jffs2 ro,noatime 0 0\n".encode("ascii")
        )
        (root / "compatible").write_bytes(
            b"mitrastar,hgw-500bna-qcv2\0quantenna,topaz\0snps,arc\0"
        )

        secret = "UnitTestSecret123"
        (persist / "config.xml").write_bytes(
            b"<Device><Model>HGW-500BNA-QCv2</Model>"
        )
        (persist / "hostapd.conf").write_bytes((
            "interface=wifi0\nbridge=br0\nhw_mode=a\n"
            "ssid=OpenMitraStar-Test5G\nwpa_passphrase=" + secret + "\n"
        ).encode("ascii"))
        (persist / "wireless_conf.txt").write_bytes(b"staticip=0\n")
        (persist / "wifi_default_key").write_bytes(secret.encode("ascii"))
        (persist / "tr069_Key").write_bytes(b"")

        values = {
            "schema": "openmitrastar.origin-mtd5/v1",
            "compatible": "mitrastar,hgw-500bna-qcv2",
            "model": "HGW-500BNA-QCv2",
            "label": "data",
            "size": "00080000",
            "erase_size": "00010000",
            "sha256": policy_hash or digest(raw_bytes),
        }
        policy = root / "policy"
        policy.write_bytes(
            "".join(f"{key}={value}\n" for key, value in values.items()).encode("ascii")
        )
        env = os.environ.copy()
        env.update(
            {
                "OM_ORIGIN_POLICY": str(policy),
                "OM_PROC_MTD_FILE": str(root / "proc-mtd"),
                "OM_PROC_MOUNTS_FILE": str(root / "proc-mounts"),
                "OM_DEV_ROOT": str(dev),
                "OM_PERSIST_MOUNT": str(persist),
                "OM_COMPATIBLE_FILE": str(root / "compatible"),
                "OM_ORIGIN_RUNTIME_ROOT": str(runtime_parent / "origin-mtd5"),
                "OM_SECRETS_ROOT": str(runtime_parent / "secrets"),
                "OM_STATE_DIR": str(state),
                "OM_ORIGIN_TEST_MODE": "1",
            }
        )
        return env, secret

    def test_imports_validated_config_and_psk_without_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, secret = self.make_fixture(root)
            result = run_wsl_script(IMPORTER, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            transcript = result.stdout + result.stderr
            self.assertIn("OMORIGIN_READY", transcript)
            self.assertIn("secrets=redacted", transcript)
            self.assertNotIn(secret, transcript)

            runtime = root / "run/openmitrastar/origin-mtd5"
            psk = root / "run/openmitrastar/secrets/wpa2.psk"
            self.assertEqual(psk.read_text(encoding="ascii"), secret + "\n")
            self.assertFalse((runtime / "wpa2.psk").exists())
            runtime_conf = (runtime / "runtime.conf").read_text(encoding="ascii")
            self.assertIn("ORIGIN_MTD5_IMPORTED=1", runtime_conf)
            self.assertIn("RADIO5G_INTERFACE=wifi0", runtime_conf)
            self.assertIn("RADIO5G_SSID=OpenMitraStar-Test5G", runtime_conf)
            self.assertNotIn(secret, runtime_conf)

            config_runtime = root / "run/openmitrastar/config"
            config_env = os.environ.copy()
            config_env.update(
                {
                    "OM_CONFIG_DEFAULTS": str(DEFAULTS),
                    "OM_CONFIG_PERSIST_ROOT": str(root / "no-overrides"),
                    "OM_CONFIG_RUNTIME": str(config_runtime),
                    "OM_ORIGIN_RUNTIME": str(runtime / "runtime.conf"),
                    "OM_CONFIG_NO_SIDE_EFFECTS": "1",
                }
            )
            config_result = run_wsl_script(CONFIG_PREPARE, config_env)
            self.assertEqual(
                config_result.returncode, 0, config_result.stdout + config_result.stderr
            )
            active = (config_runtime / "active.conf").read_text(encoding="ascii")
            self.assertIn("ORIGIN_MTD5_IMPORTED=1", active)
            self.assertIn("RADIO5G_SSID=OpenMitraStar-Test5G", active)
            self.assertIn("RADIO5G_CONFIG_SOURCE=origin-mtd5-validated", active)
            self.assertNotIn(secret, active)

    def test_hash_mismatch_fails_before_secret_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env, secret = self.make_fixture(root, policy_hash="0" * 64)
            result = run_wsl_script(IMPORTER, env)
            self.assertNotEqual(result.returncode, 0)
            transcript = result.stdout + result.stderr
            self.assertIn("OMORIGIN_REFUSED reason=hash-mismatch", transcript)
            self.assertNotIn(secret, transcript)
            self.assertFalse((root / "run/openmitrastar/secrets/wpa2.psk").exists())

    def test_current_unit_jffs2_inventory_is_bound_without_secret_output(self) -> None:
        values = policy_values(POLICY)
        raw = CURRENT_MTD5.read_bytes()
        self.assertEqual(len(raw), 524288)
        self.assertEqual(digest(raw), values["sha256"])
        image = to_wsl(CURRENT_MTD5)

        def jffs2_command(*args: str) -> list[str]:
            if os.name != "nt":
                return ["jffs2reader", *args]
            return [
                "wsl.exe",
                "-d",
                "podman-mem9-tidb",
                "-u",
                "root",
                "-e",
                "jffs2reader",
                *args,
            ]

        listing = subprocess.run(
            jffs2_command(image, "-d", "/"),
            capture_output=True,
            check=True,
        ).stdout
        for name in (b"/config.xml", b"/hostapd.conf", b"/wireless_conf.txt", b"/wifi_default_key"):
            self.assertIn(name, listing)

        def read_jffs2(path: str) -> bytes:
            return subprocess.run(
                jffs2_command(image, "-f", path),
                capture_output=True,
                check=True,
            ).stdout

        config = read_jffs2("/config.xml")
        hostapd = read_jffs2("/hostapd.conf")
        key = read_jffs2("/wifi_default_key").rstrip(b"\r\n")
        self.assertIn(values["model"].encode("ascii"), config)
        hostapd_psk = next(
            line.split(b"=", 1)[1]
            for line in hostapd.splitlines()
            if line.startswith(b"wpa_passphrase=")
        )
        self.assertEqual(hostapd_psk, key)
        self.assertGreaterEqual(len(key), 8)
        self.assertLessEqual(len(key), 63)


if __name__ == "__main__":
    unittest.main()
