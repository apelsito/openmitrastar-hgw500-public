#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "work/kernel-port/modules/f315_radar_shadow"
MAIN = SOURCE_DIR / "qtn_radar_shadow_f315_main.c"
CORE = SOURCE_DIR / "f315_radar_core.c"
HEADER = SOURCE_DIR / "f315_radar_core.h"
BUILDER = ROOT / "tools/build_f315_radar_shadow_offline.py"
OUT = ROOT / "outputs/kernel-port/f315-radar-shadow-20260905"

EXPECTED_API = {
    "detect_drv_sample_loc_get", "dfs_rqmt_code", "radar_disable",
    "radar_enable", "radar_get_chan", "radar_get_status",
    "radar_ocac_info_addr_get", "radar_record_buffer_pt", "radar_register",
    "radar_register_is_dfs_chan", "radar_register_is_dfs_weather_chan",
    "radar_register_statcb", "radar_set_bw", "radar_set_chan",
    "radar_set_shared_params", "radar_start", "radar_stop",
    "sta_dfs_is_region_required",
}


def test_source_contract() -> None:
    main = MAIN.read_text(encoding="ascii")
    core = CORE.read_text(encoding="ascii")
    header = HEADER.read_text(encoding="ascii")
    assert "static bool shadow_enable;" in main
    assert "module_param(shadow_enable, bool, 0444);" in main
    assert "module_param(shadow_arm, bool, 0600);" in main
    assert "if (!shadow_enable || !f315_value_allowed(id, value))" in main
    assert "radar_get_status(void)\n{\n\treturn false;" in main
    assert "radar_start(const char *region)\n{\n\tpr_warn_once" in main
    assert "callback_invocations=0" in main
    assert "callback_storage=0" in main
    assert "callback_allowed=0" in main
    assert "F315_MAX_PULSES 18U" in header
    assert "F315_ZC_WORDS 28U" in header
    assert "f315_decode_pulse_pair" in core
    assert "f315_decode_zc_words" in core
    assert "f315_preprocess" in core
    assert "f315_classify_shadow" in core
    for marker in ("qdrv_radar_detected", "mark_radar", "request_irq", ".proc_write"):
        assert marker not in main + core
    assert not re.search(r"static\s+.*\(\*.*callback", main)
    exports = set(re.findall(r"EXPORT_SYMBOL\(([^)]+)\);", main))
    assert exports == EXPECTED_API


def test_generated_evidence() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["contract"]["callback_invocation_present"] is False
    assert manifest["contract"]["radar_get_status"] is False
    assert manifest["tests"] == {
        "host_core": "PASS", "arc700_module": "PASS", "import_resolution": "PASS"
    }
    assert manifest["qdrv_link_probe"]["status"] == "PASS"
    assert manifest["qdrv_link_probe"]["internal_qdrv_radar_compat_removed"] is True
    assert len(manifest["qdrv_link_probe"]["resolved_imports"]) == 16
    assert manifest["safety"] == {
        "router": False, "uart": False, "tftp": False, "flash": False, "mtd": False
    }
    exports = set((OUT / "provider-exports.txt").read_text(encoding="ascii").splitlines())
    assert exports == EXPECTED_API
    imports = (OUT / "provider-imports.txt").read_text(encoding="ascii")
    assert "qdrv_radar_detected" not in imports
    assert "mark_radar" not in imports
    assert "MISSING" not in (OUT / "provider-import-contract.txt").read_text(encoding="ascii")
    strings = (OUT / "provider-strings.txt").read_text(encoding="ascii")
    assert "callback_invocations=0" in strings


def main() -> int:
    test_source_contract()
    proc = subprocess.run(
        [sys.executable, str(BUILDER), "--replace-existing"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    test_generated_evidence()
    print(proc.stdout.strip())
    print("F315 offline tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
