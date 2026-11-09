#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parent / "run_qtn_w3_final_5g_pipeline.py").read_text()
for marker in (
    "--hbm-reclaim", "--wait-for-cold-power-cycle",
    "OPENMITRASTAR_QTN_W3_HOSTLINK_VAP_ONCE_RAM_ONLY",
    "OPENMITRASTAR_QTN_W3_NATIVE_MADWIFI_AP_RAM_ONLY",
    "OpenMitraStar-5G", "21317", "channel 36",
):
    assert marker in text
for forbidden in ("flash_erase", "nandwrite", "saveenv", "mtd write"):
    assert forbidden not in text.lower()
print("QTN_FINAL_5G_PIPELINE_TEST_PASS=1")
