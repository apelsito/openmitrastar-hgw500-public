from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
PROMOTER = ROOT / "tools/promote_f310_mtd4_direct.ps1"
ROLLBACK = ROOT / "tools/rollback_f310_to_f309_mtd4.ps1"
CAMPAIGN = ROOT / "tools/run_f310_physical_campaign.ps1"
COORDINATOR = ROOT / "tools/run_f310_flash_test_rollback.ps1"
TRAFFIC_5G = ROOT / "tools/run_f293_5g_aelita_traffic.py"

F310_SHA = "df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330"
F310_FULL_CRC = "115c78af"
F310_FULL_SHA = "3b24a09219485bc68e821d20b4a4a84a0ab31cc005144b492493158bd50d1c09"
F309_SHA = "bf784c8ca144fbd18f5222a5cd23e909c59b6a1cf3bcabfc2f254fce21f91bf8"
F309_FULL_CRC = "8bf06eee"
F309_FULL_SHA = "260dc685a62215eb4bdbb654668ea734386f1e0fc7a3834d0cc45fb6f4a8eb23"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def powershell_json(path: Path) -> dict:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def detector_function() -> str:
    content = source(COORDINATOR)
    start = content.index("function Test-F310FlashCompleted")
    end = content.index("\n$promoteArgs", start)
    return content[start:end]


def write_result(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "status": "PASS",
            "generated_at": "2026-09-04T19:25:03Z",
            "candidate_sha256": F310_SHA,
            "readback": {"full_slot_crc32": F310_FULL_CRC, "full_slot_sha256": F310_FULL_SHA},
            "physical_write": {"partition": "mtd4/linux_live"},
            "protected_partitions": {"status": "PASS"},
        }),
        encoding="ascii",
    )


def test_coordinator_has_no_copy_forward_residuals() -> None:
    content = source(COORDINATOR)
    for forbidden in (
        "rollback_f309_to_f306_mtd4.ps1",
        "rollback_f310_to_f306_mtd4.ps1",
        "Test-F309FlashCompleted",
        "$f309Build",
        'schema = "openmitrastar.f309-',
        'owner = "f309-',
        "F306 was restored",
    ):
        assert forbidden not in content
    for required in (
        "rollback_f310_to_f309_mtd4.ps1",
        "Test-F310FlashCompleted",
        '$f310Build = Join-Path',
        'schema = "openmitrastar.f310-flash-test-rollback-plan/v1"',
        'owner = "f310-flash-test-rollback"',
        F309_SHA,
        F309_FULL_CRC,
        F309_FULL_SHA,
        "Invoke-LoggedPowerShell",
        "$promoteExit = Invoke-LoggedPowerShell",
        "$campaignExit = Invoke-LoggedPowerShell",
        "$rollbackExit = Invoke-LoggedPowerShell",
    ):
        assert required in content


def test_flash_detector_contract_is_ten_attempts_two_seconds() -> None:
    function = detector_function()
    assert "foreach ($attempt in 1..10)" in function
    assert "if ($attempt -lt 10) { Start-Sleep -Seconds 2 }" in function
    assert "result.json" in function
    assert "generated_at" in function
    assert "LastWriteTimeUtc -ge" not in function


def test_flash_detector_waits_for_late_result_json(tmp_path: Path) -> None:
    build = tmp_path / "f310-device-bound"
    result_path = build / "flash-one-shot-delayed" / "result.json"
    script = tmp_path / "detector.ps1"
    escaped = str(build).replace("'", "''")
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"$f310Build='{escaped}'\n"
        f"$f310Sha='{F310_SHA}'\n"
        f"$f310FullCrc='{F310_FULL_CRC}'\n"
        f"$f310FullSha='{F310_FULL_SHA}'\n"
        + detector_function()
        + "\n$started=[DateTimeOffset]::Parse('2026-09-04T19:22:03Z').UtcDateTime\n"
        + "$result=Test-F310FlashCompleted $started\n"
        + "if(-not $result){exit 7}\nWrite-Output 'DETECTOR_RETRY_PASS'\n",
        encoding="utf-8",
    )

    def delayed_write() -> None:
        time.sleep(0.6)
        write_result(result_path)
        old = 946684800
        os.utime(result_path, (old, old))
        os.utime(result_path.parent, (old, old))

    worker = threading.Thread(target=delayed_write)
    worker.start()
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    worker.join(timeout=5)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "DETECTOR_RETRY_PASS" in proc.stdout


def test_promoter_and_rollback_contracts_are_exact() -> None:
    promote = source(PROMOTER)
    rollback = source(ROLLBACK)
    for marker in (
        F310_SHA, F310_FULL_CRC, F310_FULL_SHA,
        "OPENMITRASTAR_F310_CANONICAL_FRONTEND_IDENTITY_DF451D72",
        "openmitrastar.f310-canonical-frontend-identity-candidate/v1",
        "frontend_identity_lf_only",
        "OMF310_FRONTEND_LF_ONLY",
        'public_dashboard_404 = $publicDashboardStatus -eq 404',
        'dashboard.Content -match "6\\.7\\.5-f310"',
        "foreach ($attempt in 1..36)",
    ):
        assert marker in promote
    assert "6\\.7\\.4-f310" not in promote
    for marker in (
        F309_SHA, F309_FULL_CRC, F309_FULL_SHA,
        "OPENMITRASTAR_ROLLBACK_F310_TO_F309_BF784C8C",
        "firmware\\f309-device-bound",
        "openmitrastar.f310-to-f309-rollback-plan/v1",
        'legacy_dashboard_policy = "removed-exact-f309-rollback"',
        "--legacy-dashboard-policy removed",
        "f540aa6365aeecb9d7f8ebe4fa8c4b2966de971acb5abf91132ed3a817ba59a2",
        "/usr/share/openmitrastar/web/dashboard.html /www/app.js",
    ):
        assert marker in rollback
    assert 'sha256sum /www/dashboard.html ' not in rollback
    assert "present-exact-f306" not in rollback


def test_f310_5g_profile_is_exact_and_offline() -> None:
    proc = subprocess.run(
        [sys.executable, str(TRAFFIC_5G), "--profile", "f310"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["profile"] == "f310"
    assert plan["firmware"] == "lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device"
    assert plan["router_mutations"] is False
    assert plan["flash"] is False
    assert plan["mtd_writes"] is False


def test_powershell_scripts_parse_and_dry_run_offline() -> None:
    for path in (PROMOTER, ROLLBACK, CAMPAIGN, COORDINATOR):
        escaped = str(path).replace("'", "''")
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"[scriptblock]::Create((Get-Content -Raw -LiteralPath '{escaped}')) | Out-Null"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"{path.name}: {proc.stderr}"

    promote = powershell_json(PROMOTER)
    rollback = powershell_json(ROLLBACK)
    campaign = powershell_json(CAMPAIGN)
    coordinator = powershell_json(COORDINATOR)
    assert promote["hardware_actions_performed"] is False
    assert promote["public_dashboard_policy"] == "404-not-packaged"
    assert rollback["hardware_actions_performed"] is False
    assert rollback["legacy_dashboard_policy"] == "removed-exact-f309-rollback"
    assert campaign["hardware_actions_performed"] is False
    assert coordinator["offline_contract_ready"] is True
    assert coordinator["hardware_actions_performed"] is False
    assert coordinator["flash_detection"] == {
        "evidence": "result.json/generated_at",
        "attempts": 10,
        "delay_seconds": 2,
        "directory_mtime_authoritative": False,
    }
    assert coordinator["rollback"]["sha256"] == F309_SHA


def test_only_mtd4_is_a_write_target() -> None:
    for path in (PROMOTER, ROLLBACK, COORDINATOR):
        content = source(path)
        assert "mtd4/linux_live" in content
        for forbidden in ('"mtd0/', '"mtd1/', '"mtd2/', '"mtd3/', '"mtd5/'):
            assert forbidden not in content
