#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-spi-owner-probe/qtn-topaz-spi-owner-probe.c"
OUT = ROOT / "outputs/kernel-port/f319-spi-owner-probe-20260905"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = SOURCE.read_text(encoding="ascii")
    for marker in (
        "readl(", "readb(", "writel(", "writeb(", "memcpy_fromio",
        "memcpy_toio", "mtd_device_register", "SPI_WRITE_ENABLE",
        "SPI_PAGE_PROGRAM", "SPI_SECTOR_ERASE", "SPI_GBLOCK",
    ):
        assert marker not in source
    assert "request_mem_region(TOPAZ_SPI_BASE_PHYS" in source
    assert "ioremap(TOPAZ_SPI_BASE_PHYS" in source
    assert "transaction_provider_ready" in source

    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_f319_spi_owner_probe.py"), "--replace-existing"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "OFFLINE_CLAIM_ONLY_MODULE_NOT_LOADED"
    assert manifest["contract"]["exclusive_resource_claim"] is True
    assert manifest["contract"]["mmio_reads"] == 0
    assert manifest["contract"]["mmio_writes"] == 0
    assert manifest["contract"]["mtd_registration"] is False
    assert manifest["contract"]["transaction_provider_ready"] is False
    module = OUT / manifest["artifact"]["file"]
    assert digest(module) == manifest["artifact"]["sha256"]
    for line in (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert digest(OUT / name) == expected
    print("F319 SPI owner probe tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
