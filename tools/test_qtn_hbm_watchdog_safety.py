#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HBM = (ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c").read_text()
RUNNER = (ROOT / "tools/run_qtn_w3_5g_watchdog_discriminator.py").read_text()
TELEMETRY = (ROOT / "tools/qtn_w3_5g_watchdog_telemetry.sh").read_text()

assert "w3_hbm_timer_reclaim_enable" in HBM
assert "OMHBM stage=timer-reclaim-skipped" in HBM
assert "OMHBM stage=timer-reclaim-enter" in HBM
assert "OMHBM stage=timer-reclaim-exit" in HBM
assert "available > TOPAZ_HBM_EMAC_TX_DONE_COUNT" in HBM
assert "OMHBM stage=txdone-reject" in HBM
assert "for (count = 0; count < available; count++)" in HBM
assert "full = ((wr_raw != rd_raw)" not in HBM
monitor = HBM[HBM.index("static void topaz_hbm_monitor"):]
assert "mod_timer(&hbm_timer, jiffies + intval);" in monitor[:2500]

assert "--seconds must be 150..600" in RUNNER
assert "w3_hbm_timer_reclaim_enable" in RUNNER
assert "PREFLIGHT_PASS=1" in RUNNER
for marker in ("irq8=", "irq20=", "soft_timer=", "soft_netrx=",
               "wifi_rx=", "wifi_tx=", "hostapd=", "hbm_timer_reclaim="):
    assert marker in TELEMETRY

print("QTN_HBM_WATCHDOG_SAFETY_TEST_PASS=1")
