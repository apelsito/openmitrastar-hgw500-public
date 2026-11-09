#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h").read_text()
RX = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c").read_text()

for field in (
    "rx_status_word0", "rx_status_qosctrl", "rx_status_pnlo", "rx_status_pnhi"
):
    assert field in HEADER
assert "sizeof(struct host_rxdesc) != 176" in RX
assert "rx_status_word0) != 156" in RX
assert "gain_db) != 172" in RX
assert "OMQDRVRX stage=descriptor-layout abi=v89" in RX
print("QDRV_V89_RXDESC_LAYOUT_TEST_PASS=1")
