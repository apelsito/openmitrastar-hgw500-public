from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f182_spi_probe_boot as f182  # noqa: E402


def test_boot_script_is_nonfatal_and_read_only() -> None:
    script = (f182.SOURCE_OVERLAY / "etc/init.d/S31-spi-probe").read_text(encoding="utf-8")
    assert "insmod" in script
    assert "write_capable" in script
    assert "spi-probe.state" in script
    assert "exit 0" in script
    for forbidden in ("rmmod", "flash_erase", "mtd_debug", "dd of=", "mount"):
        assert forbidden not in script


def test_built_f182_contract() -> None:
    manifest_path = f182.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f180 = json.loads((f182.F180_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f182-spi-probe-boot/v1"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == f180["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["spi_probe"]["write_capable"] is False
    assert manifest["safety"]["module_registers_mtd"] is False
    assert manifest["safety"]["module_has_write_path"] is False
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "etc/init.d/S31-spi-probe" in changed
    assert "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/diagnostics/qtn-topaz-spi-probe.ko" in changed
