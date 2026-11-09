#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-ipv6-local-policy"
INIT = ROOT / "work/mission-state/w4-rootfs-product/rootfs/etc/init.d/S34-ipv6-local-policy"


def wsl_path(path: Path) -> str:
    value = str(path).replace("\\", "/")
    return f"/mnt/{value[0].lower()}/{value[3:]}"


class Ipv6PolicyTests(unittest.TestCase):
    def test_contract_is_target_gated_and_l2_safe(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("mitrastar,hgw-500bna-qcv2", source)
        self.assertIn("all default eth0 br0", source)
        self.assertIn("bridge_l2_ipv6_untouched", source)
        for forbidden in ("iptables", "ip6tables", "ebtables", "nft", "brctl", "/dev/mtd"):
            self.assertNotIn(forbidden, source)
        self.assertIn("exec /usr/sbin/om-ipv6-local-policy", INIT.read_text(encoding="utf-8"))

    def test_fake_proc_sys_is_idempotently_disabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="om-ipv6-") as directory:
            root = Path(directory)
            compatible = root / "compatible"
            compatible.write_bytes(b"mitrastar,hgw-500bna-qcv2\0")
            conf = root / "conf"
            for scope in ("all", "default", "eth0", "br0"):
                path = conf / scope / "disable_ipv6"
                path.parent.mkdir(parents=True)
                path.write_text("0\n", encoding="ascii")
            state = root / "state.json"
            env = os.environ.copy()
            env.update({
                "OM_IPV6_COMPATIBLE_FILE": wsl_path(compatible),
                "OM_IPV6_CONF_ROOT": wsl_path(conf),
                "OM_IPV6_STATE_FILE": wsl_path(state),
            })
            args = ["wsl.exe", "env", *(f"{k}={v}" for k, v in env.items() if k.startswith("OM_")), "sh", wsl_path(SCRIPT)]
            for _ in range(2):
                result = subprocess.run(args, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("OMIPV6_POLICY_PASS", result.stdout)
            for scope in ("all", "default", "eth0", "br0"):
                self.assertEqual((conf / scope / "disable_ipv6").read_text().strip(), "1")
            self.assertIn('"bridge_l2_ipv6_untouched":true', state.read_text())

    def test_wrong_target_fails_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="om-ipv6-wrong-") as directory:
            root = Path(directory)
            compatible = root / "compatible"
            compatible.write_bytes(b"vendor,other\0")
            conf = root / "conf"
            for scope in ("all", "default", "eth0", "br0"):
                path = conf / scope / "disable_ipv6"
                path.parent.mkdir(parents=True)
                path.write_text("0\n", encoding="ascii")
            env = os.environ.copy()
            env.update({
                "OM_IPV6_COMPATIBLE_FILE": wsl_path(compatible),
                "OM_IPV6_CONF_ROOT": wsl_path(conf),
                "OM_IPV6_STATE_FILE": wsl_path(root / "state.json"),
            })
            result = subprocess.run(
                ["wsl.exe", "env", *(f"{k}={v}" for k, v in env.items() if k.startswith("OM_")), "sh", wsl_path(SCRIPT)],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            for scope in ("all", "default", "eth0", "br0"):
                self.assertEqual((conf / scope / "disable_ipv6").read_text().strip(), "0")


if __name__ == "__main__":
    unittest.main()
