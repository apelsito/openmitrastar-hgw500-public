#!/usr/bin/env python3
"""Static gate for the MitraStar RTL818b AP-transition IRQ window."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_KERNEL = Path(
    r"\\wsl.localhost\podman-mem9-tidb\home\user\mitrastar-linux-5.10.260"
)


def function(text: str, signature: str, next_signature: str) -> str:
    start = text.index(signature)
    end = text.index(next_signature, start)
    return text[start:end]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"STATIC_FAIL {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL)
    args = parser.parse_args()

    rtlwifi = args.kernel_root / "drivers/net/wireless/realtek/rtlwifi"
    pci = (rtlwifi / "pci.c").read_text(encoding="utf-8")
    hw = (rtlwifi / "rtl8192ee/hw.c").read_text(encoding="utf-8")

    policy = function(pci, "static void _rtl_pci_init_struct", "static int _rtl_pci_init_tx_ring")
    require('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in policy,
            "managed IRQ policy is not machine-scoped")
    require("pdev->irq == 28" in policy, "managed IRQ policy is not IRQ28-scoped")
    require("pdev->vendor == PCI_VENDOR_ID_REALTEK" in policy,
            "managed IRQ policy is not Realtek-scoped")
    require("pdev->device == RTL_PCI_8192EE_DID" in policy,
            "managed IRQ policy is not 10ec:818b-scoped")

    beacon = function(hw, "void rtl92ee_set_beacon_related_registers", "void rtl92ee_set_beacon_interval")
    tokens = [
        "rtlpci->irq_line_lifecycle_managed",
        "!rtlpci->irq_line_disabled",
        "rtlpci->irq_enabled",
        "disable_irq(rtlpci->pdev->irq)",
        "rtl92ee_disable_interrupt(hw)",
        "rtl92ee_enable_interrupt(hw)",
        "enable_irq(rtlpci->pdev->irq)",
    ]
    positions = [beacon.index(token) for token in tokens]
    require(positions == sorted(positions), "IRQ hold/device mask/restore order changed")
    require("pr_info_once(\"OMRTL stage=beacon-irq-window protected" in beacon,
            "bounded runtime marker missing")
    require(beacon.count("rtl92ee_enable_interrupt(hw)") == 1,
            "unexpected duplicate device IRQ restore")

    handler = function(pci, "static irqreturn_t _rtl_pci_interrupt", "static void _rtl_pci_irq_tasklet")
    deferred = function(handler, "if (rtlpci->irq_enabled == 0)", "spin_lock_irqsave")
    require("rtlpci->irq_line_lifecycle_managed" in deferred,
            "deferred ACK is not limited to managed IRQ lifecycle")
    require("interrupt_recognized(hw, &intvec)" in deferred,
            "managed deferred branch does not acknowledge device ISR")
    require("OMRTL stage=irq-deferred-acked" in deferred,
            "managed deferred ACK marker missing")

    print("STATIC_PASS policy=mitrastar+irq28+10ec:818b")
    print("STATIC_PASS order=line-hold>device-mask>registers>device-enable>line-release")
    print("STATIC_PASS logging=pr_info_once")
    print("STATIC_PASS deferred=managed-intx-device-ack")


if __name__ == "__main__":
    main()
