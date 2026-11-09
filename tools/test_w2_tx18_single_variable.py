#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_w2_2g_parity_ram_candidate.sh"
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    builder = BUILDER.read_text(encoding="utf-8", errors="replace")
    pci = PCI.read_text(encoding="utf-8", errors="replace")
    trx = TRX.read_text(encoding="utf-8", errors="replace")

    require("mgmt_split=${OM_W2_2G_MGMT_SPLIT:-1}" in builder,
            "builder lacks explicit management split selector")
    require("hgw500_txbd_mgmt_split=0" in builder and
            "hgw500_txbd_mgmt_split=N" in builder,
            "builder cannot disable inherited management split")
    require('mgmt_split = sys.argv[13] == "1"' in builder and
            '"txbd_mgmt_split": mgmt_split' in builder,
            "manifest does not disclose management split state")
    require("OMRTLTX17 stage=beacon-aperture" in pci,
            "beacon aperture correction missing")
    require("static bool hgw500_txbd_mgmt_split;" in trx,
            "management split is not an explicit opt-in parameter")

    print("STATIC_PASS tx18=tx17-beacon128-with-mgmt-split-disabled")
    print("STATIC_PASS comparison=single-runtime-parameter-removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
