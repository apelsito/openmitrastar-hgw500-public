from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COORDINATOR = ROOT / "tools/run_f293_flash_test_rollback.ps1"
ROLLBACK = ROOT / "tools/rollback_f293_to_f292_mtd4.ps1"


def test_coordinator_pins_flash_test_and_rollback_artifacts() -> None:
    source = COORDINATOR.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_F293_FLASH_TEST_ROLLBACK_76F07B7D",
        "76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37",
        "bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e",
        "promote_f293_mtd4_direct.ps1",
        "run_f293_physical_campaign.ps1",
        "rollback_f293_to_f292_mtd4.ps1",
        "Test-F293FlashCompleted",
        "ROLLED_BACK_AFTER_FAILED_CAMPAIGN",
        "MANUAL_RECOVERY_REQUIRED",
    ):
        assert marker in source
    assert 'write_targets = @("mtd4/linux_live")' in source
    for forbidden in ("mtd0", "mtd1", "mtd2", "mtd3/linux_safety", "mtd5"):
        assert forbidden not in source.split("protected_partitions =", 1)[0]


def test_rollback_targets_exact_f292_from_f293() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_ROLLBACK_F293_TO_F292_BB796F40",
        "bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e",
        "e93b0320d5a1032182661cdd4a26a31248edec6867328e9f8ac09d0ba662d3bb",
        "3cc67f08",
        'target = "mtd4/linux_live"',
        "lyoko-foundation-6.5.0-f292-emac-diagnostics-ui-device",
        "known_hosts.f292",
    ):
        assert marker in source
