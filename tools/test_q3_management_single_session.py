#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/q3_management_single_session.py"
STREAM = ROOT / "tools/q3_client_stream_single_session.py"
WIRELESS = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c"
spec = importlib.util.spec_from_file_location("q3_management_single_session", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)
stream_spec = importlib.util.spec_from_file_location("q3_client_stream_single_session", STREAM)
stream_module = importlib.util.module_from_spec(stream_spec)
assert stream_spec.loader
stream_spec.loader.exec_module(stream_module)


class SingleSessionMonitorTests(unittest.TestCase):
    def sample(self, **values):
        base = {
            "muc_fatal_count": 0, "irq10": 0, "br_eth_member": 1,
            "eth_carrier": "1", "eth_rx_packets": 10, "irq20": 10,
            "proc_count": 20, "dropbear_count": 2, "zombie_count": 0,
            "sunreclaim_kb": 1000,
        }
        base.update(values)
        return base

    def test_remote_command_is_one_bounded_loop_and_read_only(self):
        command = module.remote_command(3, 2, "192.168.1.43")
        self.assertIn('while [ "$i" -lt 3 ]', command)
        self.assertIn("ETH_RX_PACKETS=", command)
        self.assertIn("BR_ETH_MEMBER=", command)
        self.assertIn("DROPBEAR_COUNT=", command)
        self.assertIn("ARP_PEER=", command)
        self.assertIn(r"192\.168\.1\.43", command)
        for forbidden in (">/sys", ">/proc", "\nreboot", "flash_erase", "mtd_debug", "kill "):
            self.assertNotIn(forbidden, command)

    def test_parser(self):
        text = "\n".join([
            f"{module.BEGIN} 0", "UPTIME=12", "ETH_CARRIER=1", "EMAC_TICK_LINE=tick=7", f"{module.END} 0",
        ])
        self.assertEqual(module.parse_remote(text), [{"index": 0, "uptime": 12, "eth_carrier": "1", "emac_tick_line": "tick=7"}])

    def test_classifies_stall_and_resource_growth(self):
        stable_local = [{"ping": True}] * 3
        stalled = [self.sample(), self.sample(), self.sample()]
        self.assertEqual(module.classify(stalled, stable_local, None), "EMAC_RX_AND_IRQ20_STALLED")
        growing = [self.sample(eth_rx_packets=1, irq20=1), self.sample(eth_rx_packets=2, irq20=2), self.sample(eth_rx_packets=3, irq20=3, zombie_count=4)]
        self.assertEqual(module.classify(growing, stable_local, None), "PROCESS_OR_KERNEL_RESOURCE_GROWTH")

    def test_classifies_muc_and_stable(self):
        stable_local = [{"ping": True}] * 3
        muc = [self.sample(eth_rx_packets=1, irq20=1), self.sample(eth_rx_packets=2, irq20=2, muc_fatal_count=1)]
        self.assertEqual(module.classify(muc, stable_local, None), "MUC_FATAL")
        stable = [self.sample(eth_rx_packets=1, irq20=1), self.sample(eth_rx_packets=2, irq20=2), self.sample(eth_rx_packets=3, irq20=3)]
        self.assertEqual(module.classify(stable, stable_local, None), "SINGLE_SESSION_MANAGEMENT_STABLE")

    def test_replacement_stream_avoids_qdrv_control_ioctls(self):
        source = STREAM.read_text(encoding="utf-8")
        remote = source[source.index("def remote_command"):source.index("def parse_line")]
        for forbidden in ("hostapd-cli", "iwpriv", "call_qcsapi", "get_count_associations"):
            self.assertNotIn(forbidden, remote)
        for required in (
            "/sys/class/net/wifi0/statistics/rx_packets",
            "AP-STA-DISCONNECTED",
            "/sys/class/net/br0/brif/eth0",
            "/sys/class/net/br0/brif/wlan0",
            "/sys/class/net/br0/brif/wifi0",
            "/run/openmitrastar/radio2g/hostapd-open.pid",
            "/run/openmitrastar/radio2g/hostapd.pid",
            "MuC exception",
            "Oops",
            "Misaligned Access",
            "Misaligned r/w",
            "Invalid Read",
            "irq8=",
            "irq20=",
        ):
            self.assertIn(required, remote)
        self.assertNotIn("fatal=0", remote)

    def test_client_stream_parser_includes_dual_radio_health(self):
        line = (
            "OMSTREAM seq=7 uptime=90 control=1 assoc=1 wifi_rx=10 wifi_tx=20 "
            "eth_rx=30 eth_tx=40 irq8=50 irq20=60 carrier=1 rf=1 "
            "br_eth=1 br_2g=1 br_5g=1 radio2g=1 fatal=0"
        )
        parsed = stream_module.parse_line(line)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(1, parsed["assoc"])
        self.assertEqual(1, parsed["radio2g"])
        self.assertEqual(0, parsed["fatal"])

    def test_isolated_l3_mode_requires_wifi0_outside_bridge(self):
        source = STREAM.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--isolated-l3", action="store_true")', source)
        self.assertIn("expected_br5 = 0 if args.isolated_l3 else 1", source)
        self.assertIn('"isolated_l3": args.isolated_l3', source)

    def test_zero_station_ioctl_fast_path_is_target_gated(self):
        source = WIRELESS.read_text(encoding="utf-8")
        callback_start = source.index("static void get_node_info_ioctl")
        handler_start = source.index("static int\nieee80211_ioctl_getassoctbl", callback_start)
        callback = source[callback_start:handler_start]
        handler = source[handler_start:source.index("static int", handler_start + 50)]
        self.assertNotIn("copy_to_user", callback)
        self.assertNotIn("copy_from_user", callback)
        self.assertIn("table->array[table->cnt++] = record", callback)
        self.assertIn("table->cnt >= QTN_ASSOC_LIMIT", callback)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', handler)
        self.assertIn("READ_ONCE(vap->iv_sta_assoc) == 0", handler)
        self.assertIn("copy_from_user(&unit_size", handler)
        self.assertIn("kzalloc(sizeof(*table), GFP_KERNEL)", handler)
        self.assertIn("ic->ic_iterate_nodes(&ic->ic_sta, get_node_info_ioctl, table, 1)", handler)
        self.assertIn("copy_to_user(user_table, table, sizeof(*table))", handler)
        self.assertIn("OMQDRVASSOC stage=count-fast-zero", handler)
        self.assertLess(handler.index("ic->ic_iterate_nodes"), handler.index("copy_to_user(user_table"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
