#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_comm.c").read_text()
assert "OMQDRVHIF stage=raw-begin" in text
assert "OMQDRVHIF stage=raw off=%u" in text
assert "for (i = 0; i < 32; i += 8)" in text
assert "!(flags & NETDEV_F_EXTERNAL)" in text
print("QDRV_HIFINFO_RAW_TRACE_TEST_PASS=1")
