#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
SCRIPT = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-ledctl"
CONTRACT = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/share/openmitrastar/leds/hgw500-leds.json"
DOC = ROOT / "docs/HGW500_LED_CONTROL.md"


class Hgw500LedControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = DRIVER.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_all_five_oem_channels_are_bound(self):
        for marker in (
            "#define HGW500_WLAN2G_LED_PIN\t11",
            "#define HGW500_WLAN5G_LED_PIN\t1",
            "#define HGW500_SIGNALB_LED_PIN\t10",
            "#define HGW500_SIGNALG_LED_PIN\t9",
            'openmitrastar:green:wlan2g',
            'openmitrastar:green:wlan5g',
            'openmitrastar:panel:signalb',
            'openmitrastar:panel:signalg',
            'openmitrastar:panel:signalr',
            'topaz:stage0:alive',
        ):
            self.assertIn(marker, self.driver)

    def test_dts_opt_in_is_explicit(self):
        for marker in (
            "mitrastar,panel-led-controls;",
            "mitrastar,signalb-led-pin = <10>;",
            "mitrastar,signalb-led-active-high;",
            "mitrastar,signalg-led-pin = <9>;",
            "mitrastar,signalg-led-active-low;",
            "mitrastar,signalr-led-pin = <7>;",
            "mitrastar,signalr-led-active-high;",
            "qtn,recovery-led-pin = <9>;",
            "qtn,recovery-led-active-low;",
        ):
            self.assertIn(marker, self.dts)

    def test_contract_is_complete_and_cautious(self):
        self.assertEqual(self.contract["physical_windows"], 3)
        self.assertEqual(
            {item["gpio"] for item in self.contract["channels"]},
            {1, 7, 9, 10, 11},
        )
        self.assertIn("red on GPIO7", self.contract["warning"])
        self.assertIn("green on GPIO9", self.contract["warning"])
        self.assertEqual(self.contract["boot_policy"]["gpio"], 9)
        self.assertEqual(self.contract["boot_policy"]["physical_colour"], "green")
        self.assertIn("GPIO10", self.contract["warning"])
        self.assertTrue(DOC.is_file())

    def _wsl_path(self, path: Path) -> str:
        completed = subprocess.run(
            ["wsl.exe", "-e", "wslpath", "-a", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        return completed.stdout.strip()

    def _run(self, root: Path, *args: str, diagnostic: bool = False):
        if not shutil.which("wsl.exe"):
            self.skipTest("WSL unavailable")
        script = self._wsl_path(SCRIPT)
        fake = self._wsl_path(root)
        if diagnostic:
            argv = " ".join(["--diagnostic", *args])
        else:
            argv = " ".join(args)
        paths = {
            "OM_LED_WIFI2G_PATH": f"{fake}/wifi2g",
            "OM_LED_WIFI5G_PATH": f"{fake}/wifi5g",
            "OM_LED_SIGNALB_PATH": f"{fake}/signalb",
            "OM_LED_SIGNALG_PATH": f"{fake}/signalg",
            "OM_LED_SIGNALR_PATH": f"{fake}/signalr",
        }
        environment = " ".join(f"{key}='{value}'" for key, value in paths.items())
        return subprocess.run(
            [
                "wsl.exe", "-e", "sh", "-lc",
                f"{environment} OM_LED_SLEEP_CMD=true sh '{script}' {argv}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def _fake_sysfs(self, root: Path):
        names = ("wifi2g", "wifi5g", "signalb", "signalg", "signalr")
        for index, name in enumerate(names):
            (root / name).write_bytes((str(index % 2) + "\n").encode("ascii"))
        (root / "signalg").write_bytes(b"255\n")

    def test_cli_status_write_guard_colour_and_restore(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".codex_tmp") as directory:
            fake = Path(directory)
            self._fake_sysfs(fake)

            status = self._run(fake, "status")
            self.assertEqual(status.returncode, 0, status.stdout)
            payload = json.loads(status.stdout)
            self.assertEqual(set(payload["channels"]), {"wifi2g", "wifi5g", "signalb", "signalg", "signalr"})
            self.assertIn("signalr=red", payload["lower_colour_mapping"])
            self.assertIn("signalg=green", payload["lower_colour_mapping"])
            self.assertEqual(payload["boot_colour"], "green")
            self.assertEqual(payload["channels"]["signalg"]["brightness"], "1")

            normal = self._run(fake, "set", "wifi2g", "on")
            self.assertEqual(normal.returncode, 0, normal.stdout)
            self.assertEqual((fake / "wifi2g").read_text().strip(), "1")

            refused = self._run(fake, "set", "signalb", "on")
            self.assertEqual(refused.returncode, 4, refused.stdout)

            colour = self._run(fake, "color", "amber", diagnostic=True)
            self.assertEqual(colour.returncode, 0, colour.stdout)
            self.assertEqual((fake / "signalb").read_text().strip(), "0")
            self.assertEqual((fake / "signalg").read_text().strip(), "1")
            self.assertEqual((fake / "signalr").read_text().strip(), "1")

            before = {
                path: path.read_text(encoding="ascii")
                for path in fake.iterdir()
            }
            identified = self._run(fake, "identify", "1", diagnostic=True)
            self.assertEqual(identified.returncode, 0, identified.stdout)
            self.assertIn("OMLED_IDENTIFY_PASS restored=1", identified.stdout)
            after = {path: path.read_text(encoding="ascii") for path in before}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
