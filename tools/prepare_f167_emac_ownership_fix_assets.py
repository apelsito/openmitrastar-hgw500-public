#!/usr/bin/env python3
"""Build F167 assets with corrected RX descriptor ownership telemetry."""
from __future__ import annotations

from pathlib import Path

import prepare_f164_squashfs_assets as engine


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    old_out = engine.OUT
    old_kernel_out = engine.KERNEL_OUT
    try:
        engine.OUT = ROOT / "outputs/kernel-port/f167-emac-ownership-fix-20260901"
        engine.KERNEL_OUT = "/home/user/openmitrastar-build/f167-emac-ownership-fix"
        return engine.main()
    finally:
        engine.OUT = old_out
        engine.KERNEL_OUT = old_kernel_out


if __name__ == "__main__":
    raise SystemExit(main())

