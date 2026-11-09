#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QDRV = ROOT / "work/linux510-radio-port/quantenna/qdrv"
RX = QDRV / "qdrv_rx.c"
SCAN = QDRV / "qdrv_scan.c"


class Q3RxSemaphoreHardlockGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rx = RX.read_text(encoding="utf-8")
        cls.scan = SCAN.read_text(encoding="utf-8")

    def test_hgw_uses_rx_fifo_semaphore_not_scan_semaphore(self) -> None:
        selector = self.rx[
            self.rx.index("static __always_inline u32 omqdrvrx_fifo_sem_bit"):
            self.rx.index("static __always_inline bool omqdrvrx_fifo_sem_take")
        ]
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', selector)
        self.assertIn("return READ_ONCE(qw->rx_if.rx_sem_bit);", selector)
        self.assertIn("return READ_ONCE(qw->scan_if.scan_sem_bit);", selector)

    def test_hgw_semaphore_wait_is_bounded(self) -> None:
        helper = self.rx[
            self.rx.index("static __always_inline bool omqdrvrx_fifo_sem_take"):
            self.rx.index("#endif", self.rx.index("static __always_inline bool omqdrvrx_fifo_sem_take"))
        ]
        self.assertIn("OMQDRVRX_SEM_SPIN_LIMIT", helper)
        self.assertIn("stage=sem-timeout", helper)
        self.assertIn("return false;", helper)

    def test_poll_yields_and_reenables_irq_on_timeout(self) -> None:
        poll = self.rx[
            self.rx.index("int __sram_text qdrv_rx_poll"):
            self.rx.index("int qdrv_rx_start", self.rx.index("int __sram_text qdrv_rx_poll"))
        ]
        self.assertNotIn(
            "while (!sem_take(qw->host_sem, qw->scan_if.scan_sem_bit));",
            poll.split("#else", 1)[0],
        )
        self.assertIn("fifo_sem_timeout = true;", poll)
        self.assertIn("napi_complete(&qv1->napi);", poll)
        self.assertIn("qdrv_mac_enable_irq(qw->mac, qw->rxirq);", poll)
        self.assertIn("stage=sem-yield-complete", poll)

    def test_runtime_maps_both_firmware_semaphore_ids(self) -> None:
        self.assertIn("OMQDRVSEM stage=map", self.scan)
        self.assertIn("rx_sem=%u scan_sem=%u", self.scan)
        self.assertIn("selected_rx_sem=%u distinct=%u", self.scan)


if __name__ == "__main__":
    unittest.main(verbosity=2)
