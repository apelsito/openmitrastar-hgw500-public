from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/watch_f314_powercycle_then_flash.ps1"


def test_watcher_is_hash_pinned_and_non_blind() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11" in text
    assert 'candidate_bytes = $expectedBytes' in text
    assert 'No blind input will be sent' in text
    assert "$serial.Write(\" \")" in text
    assert '$serial.Write("`r")' in text
    assert "$breakCount -ge 4" in text
    assert "Hit any key (to stop autoboot|to exit)" in text
    assert "$serial.Write([string][char]0x15)" in text
    assert "$serial.Write([string][char]0x08)" in text
    assert "$atguCount -ge 2" in text
    assert "--uart-attach-topaz" in text
    assert "--skip-reboot" in text
    assert "--erase-bytes 0x5e0000" in text


def test_watcher_only_targets_mtd4_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'target = "physical mtd4/linux_live"' in text
    assert "OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32" in text
    assert "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256" in text
    assert "mtd3" not in text
    assert "mtd5" not in text


def test_watcher_requires_non_dfs_postflash() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "-notin @(36, 40, 44, 48)" in text
    assert "F314 did not boot ready on a non-DFS channel" in text


def test_watcher_runs_resumable_f314_control_matrix() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "run_f314_qtn_control_matrix_gate.py" in text
    assert "OPENMITRASTAR_F314_QTN_CONTROL_MATRIX" in text
    assert "--resume" in text
    assert 'Write-Status "control_matrix_failed"' in text
