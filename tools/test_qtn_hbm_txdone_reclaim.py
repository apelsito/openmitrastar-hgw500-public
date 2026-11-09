#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HBM = (ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c").read_text()
TQE = (ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c").read_text()

assert "OMHBM stage=txdone-reclaim" in HBM
monitor = HBM[HBM.index("static void topaz_hbm_monitor"):]
assert "topaz_hbm_filter_txdone_pool();" in monitor[:1800]
tx = TQE[TQE.index("static int tqe_tx"):]
assert "topaz_hbm_filter_txdone_pool();" in tx[:9000]
assert "OPENMITRASTAR_QDRV_V89_PAIR" in tx[:9000]
print("QTN_HBM_TXDONE_RECLAIM_TEST_PASS=1")
