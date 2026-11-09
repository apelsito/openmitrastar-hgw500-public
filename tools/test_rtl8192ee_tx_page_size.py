#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


def main() -> int:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "static unsigned int hgw500_tx_page_units = 2;" in text
    assert "module_param_named(hgw500_tx_page_units" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "hgw500_tx_page_units == 4" in text
    assert "tx_page_size = 4;" in text
    print("STATIC_PASS tx-page-units-512-byte-experiment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
