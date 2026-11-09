#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_q2_exact_ram_equivalence.py"
SPEC = importlib.util.spec_from_file_location("q2_exact_ram_equivalence", RUNNER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def good_sample(index: int, *, https: bool = False) -> dict[str, object]:
    base = 100 + index * 10
    return {
        "local_ping": True,
        "ssh_primary": True,
        "ssh_fresh": True,
        "http80_cgi_executed": True,
        "getinfo16667_executed": True,
        "http_pid_alive": 1,
        "getinfo_pid_alive": 1,
        "https443_executed": https,
        "https443_closed": not https,
        "https_pid_alive": 1 if https else 0,
        "https_ready": 1 if https else 0,
        "https_pem_present": 1 if https else 0,
        "https_pem_safe": 1 if https else 0,
        "wlan0_closed": 1,
        "wifi0_closed": 1,
        "hostapd_absent": 1,
        "br0_absent": 1,
        "only_radio_degraded": 1,
        "boot_id": "11111111-2222-3333-4444-555555555555",
        "uptime_s": base,
        "eth0_rx_bytes": base * 100,
        "eth0_rx_packets": base,
        "eth0_rx_errors": 0,
        "eth0_tx_bytes": base * 80,
        "eth0_tx_packets": base,
        "eth0_tx_errors": 0,
        "irq20": base,
    }


def good_uart() -> str:
    return "\n".join(
        [
            "topaz>",
            "TFTP from server 192.168.1.43",
            f"Filename '{MODULE.RAM_BOOT_NAME}'.",
            f"Bytes transferred = {MODULE.EXPECTED_BYTES} (0x3f714c)",
            "bootm 0x83000000",
            "Linux version 5.10.260-openmitrastar-radiohw",
            "OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192.168.1.90",
            "OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled",
            "OMINIT_SERVICE_END name=S44-oem-web rc=0",
            "OMINIT_SERVICE_END name=S35-radio-modules rc=1",
            "OMINIT_SERVICE_END name=S50-radio-ap rc=1",
        ]
    )


class Q2ExactRamEquivalenceTests(unittest.TestCase):
    def test_default_is_local_only_and_exact_image_pinned(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(RUNNER)], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OM_Q2_EXACT_RAM_EQ_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn(MODULE.EXPECTED_SHA256, proc.stdout)
        self.assertIn('"uart_log": null', proc.stdout)
        self.assertIn('"uart_opened_by_runner": false', proc.stdout)
        self.assertIn('"flash_actions": false', proc.stdout)

    def test_good_no_pem_management_soak_passes(self) -> None:
        summary, failures = MODULE.evaluate_samples(
            [good_sample(0), good_sample(1), good_sample(2)], 180.1, 180, False, 3600
        )
        self.assertTrue(summary["pass"])
        self.assertEqual([], failures)
        self.assertEqual("closed-without-external-pem", summary["https_policy"])

    def test_good_external_pem_https_soak_passes(self) -> None:
        summary, failures = MODULE.evaluate_samples(
            [good_sample(0, https=True), good_sample(1, https=True)], 180.1, 180, True, 3600
        )
        self.assertTrue(summary["pass"])
        self.assertEqual([], failures)
        self.assertEqual("external-pem-required", summary["https_policy"])

    def test_https_cannot_open_without_external_pem(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["https443_closed"] = False
        samples[1]["https_pid_alive"] = 1
        samples[1]["https_pem_present"] = 1
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180, False, 3600)
        self.assertIn("https_external_pem_policy_failure", failures)

    def test_fail_closed_radio_escape_fails(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["wifi0_closed"] = 0
        samples[1]["hostapd_absent"] = 0
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180, False, 3600)
        self.assertIn("radio_baseline_not_fail_closed", failures)

    def test_dynamic_uart_requires_exact_q2_and_rejects_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "q2-current-boot.log"
            path.write_text(good_uart(), encoding="utf-8")
            os.utime(path, (time.time(), time.time()))
            passed, markers = MODULE.uart_gate(path, max_age_s=3600)
            self.assertTrue(passed, markers)
            path.write_text(good_uart().replace(MODULE.RAM_BOOT_NAME, "q1-old.bin"), encoding="utf-8")
            passed, markers = MODULE.uart_gate(path, max_age_s=3600)
            self.assertFalse(passed)
            self.assertFalse(markers["candidate_tftp_name"])
            path.write_text(good_uart() + "\nKernel panic - not syncing", encoding="utf-8")
            passed, markers = MODULE.uart_gate(path, max_age_s=3600)
            self.assertFalse(passed)
            self.assertFalse(markers["fatal_absent"])

            path.write_text(
                good_uart().replace("OMINIT_SERVICE_END name=S44-oem-web rc=0", "OMINIT_SERVICE_END name=S44-oem-web rc=1"),
                encoding="utf-8",
            )
            passed, markers = MODULE.uart_gate(path, max_age_s=3600)
            self.assertFalse(passed)
            self.assertFalse(markers["http_getinfo_ready"])

    def test_execute_refuses_without_explicit_current_uart(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--execute", "--ack", MODULE.ACK],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("explicit --uart-log", proc.stderr)

    def test_pem_validation_requires_cert_and_private_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "external.pem"
            path.write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n", encoding="utf-8")
            self.assertFalse(MODULE.local_pem_valid(path))
            path.write_text(
                "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n"
                "-----BEGIN PRIVATE KEY-----\ny\n-----END PRIVATE KEY-----\n",
                encoding="utf-8",
            )
            self.assertTrue(MODULE.local_pem_valid(path))

    def test_runner_has_no_uart_or_flash_execution_surface(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        for forbidden in ("import serial", "COM3", "/dev/mtd", "flash_erase", "spi_flash write"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
