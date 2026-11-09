#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
MONITOR = ROOT / "tools/q3_management_single_session.py"


class EmacManagementLivenessTests(unittest.TestCase):
    def test_uart_heartbeat_has_rx_tx_ring_and_error_state(self):
        source = DRIVER.read_text(encoding="utf-8")
        marker = source[source.index('"OMEMAC poll tick='):source.index(");", source.index('"OMEMAC poll tick='))]
        for field in (
            "rx_cons=%u", "rx_prod=%u", "tx_head=%u", "tx_tail=%u",
            "cur_tx=%08x", "irq20=%u", "pending=%08x", "dma_ctrl=%08x",
            "rx_packets=%lu", "tx_packets=%lu", "rx_errors=%lu",
            "tx_errors=%lu", "queue_stopped=%u", "idle_ms=%lu",
        ):
            self.assertIn(field, marker)

    def test_polling_schedule_and_napi_path_are_unchanged(self):
        source = DRIVER.read_text(encoding="utf-8")
        self.assertIn("schedule_delayed_work(&emac->irq_poll_work, delay)", source)
        self.assertIn("napi_schedule_prep(&emac->napi)", source)
        self.assertIn("qtn_emac_tx_reclaim_locked(emac)", source)
        self.assertIn("qtn_emac_rx_poll(emac, budget)", source)

    def test_polling_recovery_reports_forced_napi_and_rx_restart(self):
        source = DRIVER.read_text(encoding="utf-8")
        self.assertIn("qtn_emac_restart_rx_dma(emac, dma_ctrl)", source)
        self.assertIn("emac->poll_forced_napi++", source)
        self.assertIn("forced_napi=%u", source)
        self.assertIn("rx_restarted=%u", source)
        self.assertIn("rx_restarts=%u", source)
        self.assertIn("rx_head_status=%08x", source)

    def test_rx_restart_is_periodic_not_lifetime_limited(self):
        source = DRIVER.read_text(encoding="utf-8")
        self.assertNotIn("QTN_TOPAZ_EMAC_RX_RESTART_LIMIT", source)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS", source)
        self.assertIn("poll_last_rx_restart_jiffies", source)
        self.assertIn("OMEMAC rx restart reason=stalled-cur-rx", source)
        self.assertIn("rx_restart_throttled=%u", source)

    def test_single_session_monitor_covers_management_layers(self):
        source = MONITOR.read_text(encoding="utf-8")
        for field in (
            "ssh_transport_connections", "ETH_RX_PACKETS", "ETH_TX_PACKETS",
            "IRQ20", "BR_ETH_MEMBER", "ARP_PEER", "DROPBEAR_COUNT",
            "ZOMBIE_COUNT", "FILE_ALLOC", "SOCKETS_USED", "MUC_FATAL_COUNT",
        ):
            self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
