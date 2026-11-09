from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f296_store_protection_probe.ps1"


def test_gate_is_exact_and_read_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_F296_STORE_PROTECTION_READONLY_2F00A2DB",
        "lyoko-foundation-6.5.3-f296-store-protection-ui-device",
        "2b9c7adc2ec6ecfc40e7f150d468feea61c7b9468db57a68cbdfa0327b10c2c6",
        "2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8",
        "sha256sum /dev/mtdblock4",
        "store_dpb_scan_count",
        "control_restored",
        "read_commands_only",
        "rmmod qtn_topaz_store_protection_observer",
        "mtd_write_attempted = $false",
    ):
        assert marker in source
    for forbidden in (
        "flash_erase",
        "nandwrite",
        "mtd_debug",
        "dd of=/dev/mtd",
        "allow_write=1",
        "register_mtd=1",
    ):
        assert forbidden not in source


def test_gate_uses_uart_and_pinned_ssh_identity() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "capture_topaz_uart_resilient.ps1" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "known_hosts.f296" in source
    assert "ServerAliveInterval=5" in source
    assert "ServerAliveCountMax=2" in source
