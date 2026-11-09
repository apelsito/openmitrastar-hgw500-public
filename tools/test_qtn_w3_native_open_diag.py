#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parent / "qtn_w3_native_open_diag.sh").read_text()
assert "OPENMITRASTAR_QTN_W3_OPEN_DIAG_RAM_ONLY" in text
assert "ssid=OpenMitraStar-5G" in text
assert "wpa=0" in text
assert "rollback-armed seconds=600" in text
assert "sleep 600" in text
assert 'touch "$root/commit"' in text
assert "flash_erase" not in text and "nandwrite" not in text
print("QTN_NATIVE_OPEN_DIAG_TEST_PASS=1")
