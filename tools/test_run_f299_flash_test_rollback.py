from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMOTER = ROOT / "tools/promote_f299_mtd4_direct.ps1"
CAMPAIGN = ROOT / "tools/run_f299_physical_campaign.ps1"
ROLLBACK = ROOT / "tools/rollback_f299_to_f292_mtd4.ps1"
COORDINATOR = ROOT / "tools/run_f299_flash_test_rollback.ps1"

F299_SHA = "92ddc564fc264e3e7e0e1fd1300e798af959bf6c4280f8972a0b8dba20c6221a"
F299_FULL_CRC = "0b419d91"
F299_FULL_SHA = "9f8a96e00fb838851560809289abaf05986ec56018e9b5ba02c9c35a6bbc2b82"
F292_SHA = "bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e"
F292_FULL_CRC = "e40dada0"
F292_FULL_SHA = "9c6dbb456207eb4006c791be76e8f40d58843e198f03abb9c0676d60202a94b1"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_promoter_pins_exact_f299_and_current_f292_slot() -> None:
    text = source(PROMOTER)
    for marker in (
        F299_SHA,
        F299_FULL_CRC,
        F299_FULL_SHA,
        F292_FULL_CRC,
        F292_FULL_SHA,
        "5259264",
        'target = "mtd4/linux_live"',
        '"--erase-bytes", "0x5e0000"',
        "known_hosts.f299",
        "rx_restart_reason_hw_demand=",
        "rx_restart_last_trigger_pokes=",
    ):
        assert marker in text


def test_rollback_pins_exact_f292_and_requires_current_f299_slot() -> None:
    text = source(ROLLBACK)
    for marker in (
        F292_SHA,
        F292_FULL_CRC,
        F292_FULL_SHA,
        F299_FULL_CRC,
        F299_FULL_SHA,
        "OPENMITRASTAR_ROLLBACK_F299_TO_F292_BB796F40",
        'target = "mtd4/linux_live"',
        "known_hosts.f292",
    ):
        assert marker in text


def test_campaign_requires_three_real_32mib_runs_and_early_proof() -> None:
    text = source(CAMPAIGN)
    for marker in (
        "evaluate_f299_emac_hw_demand_early_restart_result.py",
        "foreach ($runNumber in 1..3)",
        "bytes_per_direction = 33554432",
        "required_median_ratio_to_f290 = 0.95",
        "rx_restart_reason_hw_demand",
        "rx_restart_last_trigger_pokes",
        "fatal_count_before",
        "fatal_count_after",
        "PARTIAL",
        "--profile f299",
        "OPENMITRASTAR_F299_5G_AELITA_TRAFFIC",
        "soak-seconds 120",
        "Quantenna traffic result is not PASS",
        "foreach ($attempt in 1..5)",
        "router SSH command failed after 5 attempts",
        "foreach ($attempt in 1..24)",
        "did not converge",
    ):
        assert marker in text


def test_coordinator_rolls_back_every_non_pass_and_has_no_bypass() -> None:
    text = source(COORDINATOR)
    for marker in (
        F299_SHA,
        F299_FULL_CRC,
        F299_FULL_SHA,
        F292_SHA,
        F292_FULL_CRC,
        F292_FULL_SHA,
        "promote_f299_mtd4_direct.ps1",
        "run_f299_physical_campaign.ps1",
        "rollback_f299_to_f292_mtd4.ps1",
        "automatic_on_any_non_pass = $true",
        "$result.readback.full_slot_crc32",
        "$result.readback.full_slot_sha256",
        "ROLLED_BACK_AFTER_NON_PASS",
        'write_targets = @("mtd4/linux_live")',
    ):
        assert marker in text
    assert "NoRollback" not in text


def test_dry_run_boundaries_precede_hardware_calls() -> None:
    for path in (PROMOTER, CAMPAIGN, ROLLBACK):
        text = source(path)
        boundary = text.index("if (-not $Execute) { exit 0 }")
        executable = text[boundary:]
        assert "Test-Tcp" in executable
        assert "powershell.exe" in executable or path == CAMPAIGN
    coordinator = source(COORDINATOR)
    boundary = coordinator.index("if (-not $Execute) { exit 0 }")
    assert "-Execute -Ack" in coordinator[boundary:]


def test_only_mtd4_is_a_write_target() -> None:
    for path in (PROMOTER, ROLLBACK, COORDINATOR):
        text = source(path)
        assert "mtd4/linux_live" in text
        assert "OM_Q3_FLASH_CANDIDATE" in text or path == COORDINATOR
        assert "mtd3/linux_safety" not in text
