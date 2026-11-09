#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/reboot_boot_ramssh.ps1"
READY = ROOT / "tools/verify_product_ready.py"


class ReadyFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.boot = BOOT.read_text(encoding="utf-8")
        cls.ready = READY.read_text(encoding="utf-8")

    def test_uart_marker_is_bounded_and_not_authoritative(self) -> None:
        self.assertIn("[int]$ReadyUartWaitSeconds = 15", self.boot)
        self.assertIn("RAMSSH_CYCLE_UART_READY_FALLBACK=ssh-product-state", self.boot)
        self.assertIn("Wait-Uart $ReadyPattern 'userspace_ready_uart' $ReadyUartWaitSeconds", self.boot)
        self.assertNotIn("Wait-Uart $ReadyPattern 'userspace_ready' 90", self.boot)

    def test_autoboot_stop_uses_a_burst_not_one_fragile_byte(self) -> None:
        self.assertIn("function Send-AutobootStopBurst", self.boot)
        self.assertIn("foreach ($attempt in 1..4)", self.boot)
        self.assertGreaterEqual(self.boot.count("Send-AutobootStopBurst"), 3)

    def test_authenticated_product_gate_runs_after_ssh(self) -> None:
        ssh = self.boot.index("RAMSSH_CYCLE_SSH_PASS=1")
        product = self.boot.index("verify_product_ready.py", ssh)
        final = self.boot.index("RAMSSH_CYCLE_BOOT_PASS=1", product)
        self.assertLess(ssh, product)
        self.assertLess(product, final)
        self.assertIn("Authenticated product-state gate failed", self.boot)

    def test_product_probe_requires_real_state_and_management_carrier(self) -> None:
        self.assertIn("/run/openmitrastar/boot-state", self.ready)
        self.assertIn("/sys/class/net/eth0/carrier", self.ready)
        self.assertIn('case "$state" in ready|degraded)', self.ready)
        self.assertIn('[ "$carrier" = 1 ] || exit 21', self.ready)
        self.assertIn("tools/ramssh_exec.py", self.ready)
        self.assertIn("OMPRODUCT_READY_SSH_GATE_PASS", self.ready)
        self.assertIn("time.monotonic()", self.ready)


if __name__ == "__main__":
    unittest.main(verbosity=2)
