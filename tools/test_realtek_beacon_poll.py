#!/usr/bin/env python3
"""Static gate for the MitraStar RTL8192EE beacon PCIe poll trigger."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "work/kernel-port/linux-5.10"
RTLWIFI = ROOT / "drivers/net/wireless/realtek/rtlwifi"


def block(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(f"STATIC_FAIL {message}")


pci = (RTLWIFI / "pci.c").read_text(encoding="utf-8")
trx = (RTLWIFI / "rtl8192ee/trx.c").read_text(encoding="utf-8")

policy = block(pci, "static void _rtl_pci_init_struct", "static int _rtl_pci_init_tx_ring")
require('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in policy,
        "machine guard missing")
require("pdev->irq == 28" in policy and "PCI_VENDOR_ID_REALTEK" in policy and
        "RTL_PCI_8192EE_DID" in policy, "10ec:818b IRQ28 guard missing")

poll = trx[trx.index("void rtl92ee_tx_polling"):]
guard = poll.index("hw_queue == BEACON_QUEUE")
managed = poll.index("rtlpci->irq_line_lifecycle_managed", guard)
trigger = poll.index("rtl_write_word(rtlpriv, REG_PCIE_CTRL_REG, BIT(4))", managed)
trace_return = poll.index("if (!trace)", trigger)
require(guard < managed < trigger < trace_return,
        "beacon trigger is unguarded or occurs after trace-only return")
require("trigger_id <= 8" in poll, "beacon trigger logging is unbounded")
require("ring->cur_tx_wp = 0" in trx and "ring->cur_tx_rp = 0" in trx,
        "beacon fixed-descriptor contract changed")

prepare = block(pci, "static void _rtl_pci_prepare_bcn_tasklet", "static void _rtl_pci_init_trx_var")
own = prepare.index("HW_DESC_OWN")
barrier = prepare.index("dma_wmb()", own)
poll_call = prepare.index("tx_polling(hw, BEACON_QUEUE)", barrier)
marker = prepare.index("OMRTLTX4 stage=beacon-tasklet-poll", poll_call)
require(own < barrier < poll_call < marker,
        "beacon tasklet does not publish and poll fixed BCNQ descriptor")
require("rtlpci->irq_line_lifecycle_managed" in prepare,
        "beacon tasklet poll lacks HGW/IRQ28 guard")

print("STATIC_PASS cause=beacon-poll-trigger-missing")
print("STATIC_PASS scope=mitrastar+irq28+10ec:818b+beacon-only")
print("STATIC_PASS action=tasklet-dma_wmb-and-BEACON_QUEUE-poll")
