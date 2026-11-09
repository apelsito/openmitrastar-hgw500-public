from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_realtek_warm_rxguard_diagnostic_cycle.ps1"
IMAGE = ROOT / "work/tftp/omvl/linux510-product-cgi-nowdt-diagnostic-v1-RAM-ONLY.bin"
EXPECTED = "b63a31eaa5104e77a7af5bf07197bf30f58b2925ab07e2580487b94a967e8f53"


class DiagnosticCycleTests(unittest.TestCase):
    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(RUNNER),
                *args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )

    def test_exact_image_is_present_and_pinned(self) -> None:
        self.assertEqual(IMAGE.stat().st_size, 6_758_400)
        self.assertEqual(hashlib.sha256(IMAGE.read_bytes()).hexdigest(), EXPECTED)

    def test_default_dry_run_is_secret_free_and_flash_free(self) -> None:
        secret = "test-only-rxguard-passphrase"
        with tempfile.TemporaryDirectory() as directory:
            psk = Path(directory) / "external.psk"
            psk.write_text(secret, encoding="ascii")
            proc = self.invoke("-PskFile", str(psk), "-AutoDiscoverClient")
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        self.assertIn("OMRTL_RXGUARD_DIAGNOSTIC_CYCLE_DRY_RUN_PASS=1", output)
        self.assertIn(EXPECTED, output)
        self.assertNotIn(secret, output)
        self.assertNotIn("EXECUTE_RAM\"", output)

    def test_execute_without_ack_fails_before_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            psk = Path(directory) / "external.psk"
            psk.write_text("test-only-rxguard-passphrase", encoding="ascii")
            proc = self.invoke(
                "-ExecuteRam", "-PskFile", str(psk), "-AutoDiscoverClient"
            )
        output = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requires exact -AckRamOnly", output)
        self.assertNotIn("RAMSSH_CYCLE_START", output)

    def test_policy_contains_uart_capture_and_three_layer_rollback(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        for required in (
            "capture_topaz_uart.ps1",
            "run_realtek_warm_rxguard_isolated.ps1",
            "OMAP_ISOLATED_GATE_PASS keep_ap=0 rollback=PASS",
            "OMRTL_RXGUARD_HOST_ROLLBACK_PASS=1",
            "Invoke-ExactRamBoot $false \"recovery\"",
            "fw-warm-preclean",
            '"-UartLog", $activeUartLog',
            "OMRTL stage=rx-(?:defer|work)",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "flashcp",
            "mtd_debug",
            "/dev/mtd",
            "saveenv",
            "flwrite",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
