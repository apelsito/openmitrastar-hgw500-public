from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f172_physical_campaign.ps1"


def test_campaign_is_explicit_and_non_flashing() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'OPENMITRASTAR_F172_PHYSICAL_CAMPAIGN' in text
    assert 'expected_napi_weight = 128' in text
    assert "napi_weight=128" in text
    assert "$run -le 3" in text
    assert "--traffic-direction both" in text
    assert "evaluate_f172_emac_napi128_result.py" in text
    assert "run_aelita_2g_wpa2_speed_router_probe.py" in text
    for forbidden in ("spi_flash", "flash_erase", "mtd_debug", "fw_setenv"):
        assert forbidden not in text


def test_campaign_requires_f172_runtime_before_client_mutation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    identity = text.index("napi_weight=128")
    runner = text.index("run_aelita_2g_wpa2_speed_router_probe.py")
    assert identity < runner
