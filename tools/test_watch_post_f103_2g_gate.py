from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "watch_post_f103_2g_gate.ps1"


def test_post_f103_gate_is_postflash_only() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "openmitrastar.f103-postflash-2g-autogate/v1" in text
    assert "touches_uart = $false" in text
    assert "flashes = $false" in text
    assert "waiting for router SSH after F103 flash" in text
    assert "run_aelita_2g_wpa2_speed_router_probe.py" in text
    assert "ssh_openmitrastar_510.ps1" in text
    assert "aelita_radio_goal_decision.ps1" in text


def test_post_f103_gate_has_expected_thresholds_and_recommendations() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "[double]$MinDownloadMbps = 12.0" in text
    assert "[double]$MinUploadMbps = 18.0" in text
    assert "F104_RECOMMENDED_LOW_THROUGHPUT" in text
    assert "F103_ACCEPT_FOR_2G_BASELINE" in text
    assert "F103_GATE_FAIL_RETRY_OR_DIAGNOSE" in text
    assert "arm_f104_2g_be_guard16_flash.ps1 -Execute" in text
    assert "F103_FLASHED_VERIFY_2G" in text
    assert "AllowSshWithoutF103FlashMarker" in text
    assert "router SSH not reachable yet; post-SSH 2.4 gate remains armed" in text
    assert "allow_ssh_without_f103_flash_marker" in text
    assert "goal_decision = $decision" in text
    assert "tcp22 = $tcp22" in text


def test_post_f103_gate_does_not_open_uart_or_write_flash() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    forbidden = (
        "[IO.Ports.SerialPort]::new",
        "SerialPort",
        "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1",
        "mtd_debug",
        "flash_erase",
        "nandwrite",
        "dd if=",
        "dd of=",
        "qtnboot",
    )
    for needle in forbidden:
        assert needle not in text
