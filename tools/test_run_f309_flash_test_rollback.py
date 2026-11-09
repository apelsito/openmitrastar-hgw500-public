from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROMOTER = ROOT / "tools/promote_f309_mtd4_direct.ps1"
ROLLBACK = ROOT / "tools/rollback_f309_to_f306_mtd4.ps1"
CAMPAIGN = ROOT / "tools/run_f309_physical_campaign.ps1"
COORDINATOR = ROOT / "tools/run_f309_flash_test_rollback.ps1"
POSTFLASH_GATE = ROOT / "tools/post_flash_f214_device_gate.py"
TRAFFIC_5G = ROOT / "tools/run_f293_5g_aelita_traffic.py"

F309_SHA = "bf784c8ca144fbd18f5222a5cd23e909c59b6a1cf3bcabfc2f254fce21f91bf8"
F309_FULL_CRC = "8bf06eee"
F309_FULL_SHA = "260dc685a62215eb4bdbb654668ea734386f1e0fc7a3834d0cc45fb6f4a8eb23"
F306_SHA = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
F306_FULL_CRC = "71548682"
F306_FULL_SHA = "c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36"


def text(path: Path) -> str:
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


def test_promoter_is_pinned_to_f309_and_requires_public_404() -> None:
    source = text(PROMOTER)
    for marker in (
        F309_SHA, F309_FULL_CRC, F309_FULL_SHA, F306_FULL_CRC, F306_FULL_SHA,
        "OPENMITRASTAR_F309_AUTHENTICATED_DASHBOARD_BF784C8C",
        "openmitrastar.f309-authenticated-dashboard-candidate/v1",
        "lyoko-foundation-6.7.4-f309-authenticated-dashboard-device",
        "lyoko-foundation-6.7.4-f309-authenticated-dashboard-device",
        "public_dashboard_404 = $publicDashboardStatus -eq 404",
        "/usr/share/openmitrastar/web/dashboard.html /www/app.js",
        "$manifest.integration.public_dashboard_packaged -ne $false",
        "$manifest.integration.login_api_cgi_byte_identical_to_f306 -ne $true",
    ):
        assert marker in source
    assert 'sha256sum /www/dashboard.html ' not in source


def test_rollback_is_exact_f306_and_accepts_its_historical_public_route() -> None:
    source = text(ROLLBACK)
    for marker in (
        F306_SHA, F306_FULL_CRC, F306_FULL_SHA, F309_FULL_CRC, F309_FULL_SHA,
        "OPENMITRASTAR_ROLLBACK_F309_TO_F306_A245AB17",
        "firmware\\f306-device-bound",
        "openmitrastar.f309-to-f306-rollback-plan/v1",
        "--legacy-dashboard-policy present",
        'legacy_dashboard_policy = "present-exact-f306-rollback"',
    ):
        assert marker in source


def test_successor_detector_uses_result_generated_at_not_directory_mtime(tmp_path: Path) -> None:
    source = text(COORDINATOR)
    start = source.index("function Test-F309FlashCompleted")
    end = source.index("\n$promoteArgs", start)
    function_source = source[start:end]
    assert "generated_at" in function_source
    assert "Where-Object { $_.LastWriteTimeUtc" not in function_source

    build = tmp_path / "f309-device-bound"
    result_dir = build / "flash-one-shot-old-directory-time"
    result_dir.mkdir(parents=True)
    result = {
        "status": "PASS",
        "generated_at": "2026-09-04T19:25:03Z",
        "candidate_sha256": F309_SHA,
        "readback": {"full_slot_crc32": F309_FULL_CRC, "full_slot_sha256": F309_FULL_SHA},
        "physical_write": {"partition": "mtd4/linux_live"},
        "protected_partitions": {"status": "PASS"},
    }
    result_path = result_dir / "result.json"
    result_path.write_text(json.dumps(result), encoding="ascii")
    old = 946684800
    os.utime(result_path, (old, old))
    os.utime(result_dir, (old, old))

    ps1 = tmp_path / "detector.ps1"
    escaped = str(build).replace("'", "''")
    ps1.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"$f309Build='{escaped}'\n"
        f"$f309Sha='{F309_SHA}'\n"
        f"$f309FullCrc='{F309_FULL_CRC}'\n"
        f"$f309FullSha='{F309_FULL_SHA}'\n"
        + function_source
        + "\n$started=[DateTimeOffset]::Parse('2026-09-04T19:22:03Z').UtcDateTime\n"
        + "$result=Test-F309FlashCompleted $started\n"
        + "if(-not $result){exit 7}\nWrite-Output 'DETECTOR_PASS'\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "DETECTOR_PASS" in proc.stdout


def test_coordinator_uses_f309_campaign_and_exact_f306_rollback() -> None:
    source = text(COORDINATOR)
    for marker in (
        F309_SHA, F309_FULL_CRC, F309_FULL_SHA,
        F306_SHA, F306_FULL_CRC, F306_FULL_SHA,
        "promote_f309_mtd4_direct.ps1",
        "run_f309_physical_campaign.ps1",
        "rollback_f309_to_f306_mtd4.ps1",
        "OPENMITRASTAR_F309_AUTHENTICATED_DASHBOARD_BF784C8C",
        "OPENMITRASTAR_F309_AUTHENTICATED_DASHBOARD_PHYSICAL",
        "OPENMITRASTAR_ROLLBACK_F309_TO_F306_A245AB17",
        "ROLLED_BACK_AFTER_NON_PASS",
        'write_targets = @("mtd4/linux_live")',
    ):
        assert marker in source
    assert "rollback_f309_to_f301" not in source


def test_postflash_gate_has_explicit_legacy_dashboard_policy() -> None:
    source = text(POSTFLASH_GATE)
    assert 'choices=("removed", "present", "ignore")' in source
    assert 'default="removed"' in source
    assert 'args.legacy_dashboard_policy == "present"' in source
    assert '"legacy_dashboard_policy": args.legacy_dashboard_policy' in source


def test_f309_5g_profile_is_exact_and_dry_run_only() -> None:
    proc = subprocess.run(
        [sys.executable, str(TRAFFIC_5G), "--profile", "f309"],
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
    assert plan["profile"] == "f309"
    assert plan["firmware"] == "lyoko-foundation-6.7.4-f309-authenticated-dashboard-device"
    assert plan["transfers"] == {"download_bytes": 33554432, "upload_bytes": 33554432}
    assert plan["soak_seconds"] == 120
    assert plan["router_mutations"] is False
    assert plan["flash"] is False
    assert plan["mtd_writes"] is False


def test_all_powershell_scripts_parse_and_dry_run_offline() -> None:
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
    assert rollback["legacy_dashboard_policy"] == "present-exact-f306-rollback"
    assert campaign["hardware_actions_performed"] is False
    assert coordinator["offline_contract_ready"] is True
    assert coordinator["hardware_actions_performed"] is False
    assert coordinator["flash"]["target"] == "mtd4/linux_live"
    assert coordinator["rollback"]["target"] == "mtd4/linux_live"
    assert coordinator["rollback"]["sha256"] == F306_SHA


def test_only_mtd4_is_a_write_target() -> None:
    for path in (PROMOTER, ROLLBACK, COORDINATOR):
        source = text(path)
        assert "mtd4/linux_live" in source
        for forbidden in ('"mtd0/', '"mtd1/', '"mtd2/', '"mtd3/', '"mtd5/'):
            assert forbidden not in source
