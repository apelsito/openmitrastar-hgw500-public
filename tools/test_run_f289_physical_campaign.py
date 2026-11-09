from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f289_physical_campaign.ps1"


def test_f289_campaign_is_bounded_and_compares_against_f287() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_F289_FAULT_ONLY_RESTART_PHYSICAL" in source
    assert "lyoko-foundation-6.4.2-f289-emac-fault-only-restart-device" in source
    assert "f288-emac-rx-fault-20260903\\f288-evaluation.json" in source
    assert "realtek_runs = 3" in source
    assert "expected_rx_ring = 256" in source
    assert "expected_napi_weight = 256" in source
    assert "run_f289_5g_aelita_traffic.py" in source
    assert "router_mutation = $false" in source
    assert "flash = $false" in source


def test_f289_campaign_has_no_flash_primitives() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
