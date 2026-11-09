from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f223_flash_test_cycle.ps1"


def test_f223_cycle_has_exact_candidate_and_guardrails() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_F223_FLASH_TEST_A63CCCE6" in source
    assert "a63ccce69776732269ac4c08f29062c74b93eda945c88778ab63efd9215be2bc" in source
    assert "promote_f223_mtd4_direct.ps1" in source
    assert "run_f223_physical_campaign.ps1" in source
    assert "post_flash_f219_package_gate.py" in source
    assert "run_f151_5g_bridge_trial.py" in source
    assert "--erase-bytes 0x5e0000" not in source
    assert 'target = "mtd4/linux_live"' in source
    assert 'next_candidate = "F228"' in source
