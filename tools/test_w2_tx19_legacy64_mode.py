#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_w2_2g_parity_ram_candidate.sh"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    text = BUILDER.read_text(encoding="utf-8", errors="replace")
    require("compact32=${OM_W2_2G_COMPACT32:-1}" in text,
            "builder lacks an explicit global TXBD width selector")
    require("OM_W2_2G_COMPACT32 must be 0 or 1" in text,
            "builder does not validate the selector")
    require("hgw500_txbd_compact32=0" in text and
            "hgw500_txbd_compact32 N" in text,
            "legacy64 rootfs module parameters are not enforced")
    require('"txbd_compact32_global": compact32' in text,
            "manifest does not disclose the selected width")
    require('"txbd_hardware_width_bit15": 0 if compact32 else 1' in text,
            "manifest does not bind the selector to bit15")
    print("STATIC_PASS tx19=clean-global64-single-mode-discriminator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
