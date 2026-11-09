#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/collect_w2_2g_client_gate.py"


RAW_PREASSOC = """OM_BOOT_STATE_BEGIN
degraded
OM_BOOT_STATE_END
OM_RADIO_STATE_BEGIN
ready
OM_RADIO_STATE_END
OM_HOSTAPD_STATUS_BEGIN
state=ENABLED
channel=1
ssid[0]=OpenMitraStar-2G-DIAG
num_sta[0]=0
OM_HOSTAPD_STATUS_END
OM_HOSTAPD_ALL_STA_BEGIN
OM_HOSTAPD_ALL_STA_END
OM_IW_STATION_BEGIN
OM_IW_STATION_END
OM_BRIF_BEGIN
wlan0
eth0
OM_BRIF_END
OM_NETDEV_BEGIN
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  eth0:  263044    2418    0   10    0     0          0         0   226300     881    0    0    0     0       0          0
 wlan0:       0       0    0    0    0     0          0         0   198122    1649    0    0    0     0       0          0
   br0:  226844    2383    0   11    0     0          0       503   226120     879    0    0    0     0       0          0
OM_NETDEV_END
OM_INTERRUPTS_BEFORE_BEGIN
 20:       3294  ARC In-core Intc  20  eth0
 28:      11701  ARC In-core Intc  28  rtl_pci
OM_INTERRUPTS_BEFORE_END
OM_INTERRUPTS_AFTER_BEGIN
 20:       3304  ARC In-core Intc  20  eth0
 28:      11801  ARC In-core Intc  28  rtl_pci
OM_INTERRUPTS_AFTER_END
OM_DMESG_SAFETY_BEGIN
<5>Kernel command line: earlycon=uart8250 panic=10
OM_DMESG_SAFETY_END
OM_TXBD_BEGIN
<6>rtl_pci: OMRTLTX3 stage=txbd-ring q=0 stride=32 compact=1
<6>rtl_pci: OMRTLTX3 stage=txbd-ring q=1 stride=32 compact=1
<6>rtl_pci: OMRTLTX3 stage=txbd-ring q=2 stride=32 compact=1
<6>rtl_pci: OMRTLTX3 stage=txbd-ring q=3 stride=32 compact=1
<6>rtl_pci: OMRTLTX3 stage=txbd-ring q=4 stride=64 compact=0
OM_TXBD_END
"""


class CollectW2GateTests(unittest.TestCase):
    def test_candidate_identity_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.txt"
            out = Path(tmp) / "evidence.json"
            raw.write_text(RAW_PREASSOC, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--input-raw",
                    str(raw),
                    "--output",
                    str(out),
                    "--image-path",
                    "work/tftp/omvl/tx5.bin",
                    "--image-sha256",
                    "a" * 64,
                    "--image-bytes",
                    "1234",
                    "--image-variant",
                    "TX5",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            evidence = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(evidence["classification"], "RAM-ONLY-TX5-LIVE-CLIENT-GATE-NO-FLASH")
            self.assertEqual(evidence["image"]["path"], "work/tftp/omvl/tx5.bin")
            self.assertEqual(evidence["image"]["sha256"], "a" * 64)
            self.assertEqual(evidence["image"]["bytes"], 1234)

    def test_preassociation_snapshot_is_parseable_and_evaluates_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.txt"
            out = Path(tmp) / "evidence.json"
            raw.write_text(RAW_PREASSOC, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--input-raw",
                    str(raw),
                    "--output",
                    str(out),
                    "--evaluate",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            evidence = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(evidence["associated"])
            self.assertFalse(evidence["authorized"])
            self.assertTrue(evidence["bridge_eth0_wlan0"])
            self.assertTrue(evidence["irq28_progress"])
            self.assertTrue(evidence["hostapd_stable"])
            self.assertTrue(evidence["no_kernel_oops"])
            self.assertEqual(evidence["observed"]["ssid"], "OpenMitraStar-2G-DIAG")
            self.assertEqual(evidence["observed"]["txbd_layout"]["q4"], "stride64 beacon compact=0")

            result = json.loads(out.with_suffix(out.suffix + ".result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("associated", result["failures"])
            self.assertIn("download_mbps", result["failures"])


if __name__ == "__main__":
    unittest.main()
