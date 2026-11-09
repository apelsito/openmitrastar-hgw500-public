#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "work/linux510-radio-port/quantenna/platform/ruby/runtime_compat.c").read_text()
assert "DBG_LL_WARNING" in text
assert "DBG_LF_ALL & ~0x0001f800U" in text
assert "OMQDRVDBG stage=defaults" in text
assert "module_init(openmitrastar_runtime_compat_init)" in text
print("QTN_RUNTIME_DEBUG_DEFAULTS_TEST_PASS=1")
