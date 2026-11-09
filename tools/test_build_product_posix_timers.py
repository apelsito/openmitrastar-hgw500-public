#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "tools/build_product_posix_timers_incremental.sh").read_text()
assert "--enable POSIX_TIMERS" in text
assert "CONFIG_POSIX_TIMERS=y" in text
assert "uImage.bin" in text
assert "bootbase-contract.json" in text
assert "RAM-ONLY-NO-FLASH" in text
for forbidden in ("flash_erase", "nandwrite", "saveenv", "mtd write"):
    assert forbidden not in text.lower()
print("PRODUCT_POSIX_TIMERS_BUILD_TEST_PASS=1")
