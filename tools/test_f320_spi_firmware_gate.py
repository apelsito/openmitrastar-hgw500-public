"""Read-only tests over exact F320 artifacts; never rebuild or touch hardware."""
import json
from pathlib import Path
import pytest
import build_f320_spi_control_firmware as firmware
import prepare_f320_spi_read_gate as gate


def test_real_f320_candidate_and_independent_bootbase_contract():
    result = gate.inspect_candidate()
    assert result["sha256"] == gate.EXPECTED_IMAGE
    assert result["bootbase_contract"] == "PASS"


def test_exact_three_path_rootfs_delta_and_no_hardware_claim():
    manifest = json.loads((firmware.DEVICE / "f320-device-bound/manifest.json").read_text())
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == firmware.EXPECTED_CHANGES
    assert manifest["physical_validation"] == {
        **manifest["physical_validation"], "status": "NOT_RUN", "authorized": False}
    assert manifest["storage"]["persistent_writes_enabled"] is False
    assert manifest["spi_control_probe"]["default_access"] == "REFUSED"


@pytest.mark.parametrize("field,value", [("spi_reads_max", 2), ("spi_reads_max", True),
    ("mmio_writes", 1), ("flash_opcodes", 1), ("autoload", True),
    ("spi_address", "0xe4030004"), ("default_access", "ENABLED")])
def test_module_scope_cannot_be_expanded(tmp_path, field, value):
    installed = json.loads((firmware.DEVICE / "f320-device-bound/manifest.json").read_text())
    source = Path(installed["source"]["module_manifest"]).parent
    manifest = json.loads((source / "manifest.json").read_text())
    (tmp_path / (firmware.NAME + ".ko")).write_bytes((source / (firmware.NAME + ".ko")).read_bytes())
    manifest["contract"][field] = value
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="scope changed"):
        firmware.verify_contract(tmp_path)


def test_plan_has_no_hardware_executor():
    text = (gate.ROOT / "tools/prepare_f320_spi_read_gate.py").read_text()
    for forbidden in ("import serial", "import socket", "subprocess.run", "Start-Process"):
        assert forbidden not in text
    assert '"physical_executor": "tools/promote_f320_mtd4.ps1; separate source-bound qualification required"' in text
    assert '"old_f319_ack_reusable": False' in text
