from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROMOTER = ROOT / "tools/promote_f306_mtd4_direct.ps1"
CAMPAIGN = ROOT / "tools/run_f306_physical_campaign.ps1"
ROLLBACK = ROOT / "tools/rollback_f306_to_f301_mtd4.ps1"
COORDINATOR = ROOT / "tools/run_f306_flash_test_rollback.ps1"
TRAFFIC_5G = ROOT / "tools/run_f293_5g_aelita_traffic.py"

F306_SHA = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
F306_FULL_CRC = "71548682"
F306_FULL_SHA = "c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36"
F301_SHA = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
F301_FULL_CRC = "2483522f"
F301_FULL_SHA = "c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def powershell_json(path: Path) -> dict:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_promoter_pins_exact_f306_and_requires_current_f301_slot() -> None:
    text = source(PROMOTER)
    for marker in (
        F306_SHA, F306_FULL_CRC, F306_FULL_SHA, F301_FULL_CRC, F301_FULL_SHA,
        "5267456", 'target = "mtd4/linux_live"', '"--erase-bytes", "0x5e0000"',
        "known_hosts.f306", "openmitrastar.f306-unified-product-candidate/v1",
        "radio_payload_file_count -ne 86",
    ):
        assert marker in text


def test_promoter_requires_full_product_contract() -> None:
    text = source(PROMOTER)
    for marker in (
        "WebRequestSession", "login_password", "OMSESSION",
        'dashboard.Content -match "6\\.7\\.3-f306"',
        'foreach ($endpoint in @("status", "firmware", "frontend", "capabilities", "diagnostics", "storage"))',
        'data-mode="', "api_patch_radios_contract", "PATCH) stage_radio_config",
        "radios/2g|radios/5g", "@($api.capabilities.items).Count -eq 23",
        "sha256sum /www/dashboard.html", "store_observer_disabled",
        "multicast_available", "secrets_logged = $false", "session_cookie_logged = $false",
    ):
        assert marker in text
    assert "f2644551" not in text


def test_rollback_pins_exact_f301_and_requires_current_f306_slot() -> None:
    text = source(ROLLBACK)
    for marker in (
        F301_SHA, F301_FULL_CRC, F301_FULL_SHA, F306_FULL_CRC, F306_FULL_SHA,
        "5267456", "OPENMITRASTAR_ROLLBACK_F306_TO_F301_4C280E84",
        'target = "mtd4/linux_live"', "known_hosts.f301",
    ):
        assert marker in text


def test_campaign_runs_one_real_2g_regression_and_full_5g_gate() -> None:
    text = source(CAMPAIGN)
    for marker in (
        "realtek_runs = 1", "realtek_bytes_per_direction = $transferBytes",
        "run_aelita_2g_wpa2_speed_router_probe.py",
        "$summary.controller_download.pass -eq $true",
        "$summary.controller_upload.pass -eq $true",
        "$summary.router_health_gate.pass -eq $true",
        "--profile f306", "OPENMITRASTAR_F306_5G_AELITA_TRAFFIC",
        "--soak-seconds 120", "$qtnData.soak.disconnects -ne 0",
    ):
        assert marker in text


def test_final_health_is_separate_and_retrying() -> None:
    text = source(CAMPAIGN)
    for marker in (
        "Invoke-RouterWithRetry", "foreach ($attempt in 1..5)",
        '"final firmware identity"', '"final boot state"',
        '"final 2.4 GHz state"', '"final 5 GHz state"',
        '"final diagnostics"', 'IndexOf("{")', "monolithic_command = $false",
    ):
        assert marker in text
    assert "$finalHealthCommand" not in text


def test_coordinator_rolls_back_every_non_pass_to_exact_f301() -> None:
    text = source(COORDINATOR)
    for marker in (
        F306_SHA, F306_FULL_CRC, F306_FULL_SHA, F301_SHA, F301_FULL_CRC, F301_FULL_SHA,
        "promote_f306_mtd4_direct.ps1", "run_f306_physical_campaign.ps1",
        "rollback_f306_to_f301_mtd4.ps1", "automatic_on_any_non_pass = $true",
        "$result.readback.full_slot_crc32", "$result.readback.full_slot_sha256",
        "$payload.result", "ROLLED_BACK_AFTER_NON_PASS", 'write_targets = @("mtd4/linux_live")',
        "$_.LastWriteTimeUtc -ge $StartedUtc.AddSeconds(-5)",
        "foreach ($resultFile in $resultFiles)",
    ):
        assert marker in text
    assert "NoRollback" not in text


def test_coordinator_detects_the_shared_soak_lock_before_execute() -> None:
    text = source(COORDINATOR)
    boundary = text.index("if (-not $Execute) { exit 0 }")
    for marker in (
        "outputs\\locks\\f301-physical-radio.lock", "Get-HardwareLockState",
        "Get-Process -Id", "execute_allowed_now", "offline_contract_ready",
        "Refusing campaign: F301 physical lock is active",
        "physical lock could not be acquired atomically",
        'owner = "f306-flash-test-rollback"',
    ):
        assert marker in text
    assert text.index("$lockState = Get-HardwareLockState") < boundary
    assert text.index("if ($lockState.active)") > boundary


def test_5g_runner_has_exact_f306_profile() -> None:
    text = source(TRAFFIC_5G)
    for marker in (
        '"f306": {',
        '"version": "lyoko-foundation-6.7.3-f306-unified-product-device"',
        '"ack": "OPENMITRASTAR_F306_5G_AELITA_TRAFFIC"',
        '"schema": "openmitrastar.f306-5g-aelita-traffic"',
    ):
        assert marker in text


def test_dry_run_boundaries_precede_hardware_calls() -> None:
    for path in (PROMOTER, CAMPAIGN, ROLLBACK):
        text = source(path)
        boundary = text.index("if (-not $Execute) { exit 0 }")
        executable = text[boundary:]
        assert "Test-Tcp" in executable
        assert "powershell.exe" in executable or path == CAMPAIGN
    coordinator = source(COORDINATOR)
    boundary = coordinator.index("if (-not $Execute) { exit 0 }")
    assert "-Execute" in coordinator[boundary:]


def test_only_mtd4_is_a_write_target() -> None:
    for path in (PROMOTER, ROLLBACK, COORDINATOR):
        text = source(path)
        assert "mtd4/linux_live" in text
        assert "OM_Q3_FLASH_CANDIDATE" in text or path == COORDINATOR
        assert "mtd3/linux_safety" not in text
        for forbidden in ('"mtd0/', '"mtd1/', '"mtd2/', '"mtd3/', '"mtd5/'):
            assert forbidden not in text


def test_all_powershell_files_parse_without_execution() -> None:
    for path in (PROMOTER, CAMPAIGN, ROLLBACK, COORDINATOR):
        escaped = str(path).replace("'", "''")
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"[scriptblock]::Create((Get-Content -Raw -LiteralPath '{escaped}')) | Out-Null"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False,
        )
        assert proc.returncode == 0, f"{path.name}: {proc.stderr}"


def test_all_dry_runs_are_offline_and_contract_ready() -> None:
    promote = powershell_json(PROMOTER)
    campaign = powershell_json(CAMPAIGN)
    rollback = powershell_json(ROLLBACK)
    coordinator = powershell_json(COORDINATOR)

    assert promote["mode"] == campaign["mode"] == rollback["mode"] == "dry-run"
    assert promote["hardware_actions_performed"] is False
    assert campaign["hardware_actions_performed"] is False
    assert rollback["hardware_actions_performed"] is False
    assert coordinator["mode"] == "dry-run"
    assert coordinator["offline_contract_ready"] is True
    assert coordinator["ready"] is (not coordinator["hardware_lock"]["active"])
    assert coordinator["execute_allowed_now"] == coordinator["ready"]
    assert coordinator["hardware_actions_performed"] is False
    assert coordinator["flash"]["target"] == "mtd4/linux_live"
    assert coordinator["rollback"]["target"] == "mtd4/linux_live"
    assert coordinator["rollback"]["sha256"] == F301_SHA


def test_f306_5g_profile_dry_run_is_exact_and_offline() -> None:
    proc = subprocess.run(
        ["python", str(TRAFFIC_5G), "--profile", "f306"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["profile"] == "f306"
    assert plan["firmware"] == "lyoko-foundation-6.7.3-f306-unified-product-device"
    assert plan["transfers"] == {"download_bytes": 33554432, "upload_bytes": 33554432}
    assert plan["soak_seconds"] == 120
    assert plan["router_mutations"] is False
    assert plan["flash"] is False
    assert plan["mtd_writes"] is False
