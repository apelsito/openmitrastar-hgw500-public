"""Offline recovery-proof and in-process lease checks. Never opens UART/SSH."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/f319_recovery_guard.ps1"
SHA = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
VERSION = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
PNP = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"


def ps(script, engine="pwsh.exe", timeout=25):
    return subprocess.run([engine, "-NoProfile", "-NonInteractive", "-Command", script],
                          cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def make_proof(directory):
    restore_dir = directory / "f314-restore"
    platform_dir = directory / "postflash-f314"
    restore_dir.mkdir()
    platform_dir.mkdir()
    evidence = []
    for index in range(5):
        path = restore_dir / f"fixture-{index}.log"
        path.write_bytes(b"synthetic offline fixture\n")
        evidence.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"schema": "openmitrastar.f319-bootbase-recovery-rehearsal-result/v1",
              "status": "PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE", "f314_sha256": SHA,
              "full_slot_crc32": "d6b13baa", "restore_ssh_dependency": False,
              "flash_attempted": True, "protected_partitions_written": False,
              "final_binding": {"NonceObserved": True, "RouterHost": "192.168.1.90",
                                "ExpectedVersion": VERSION, "PnpDeviceId": PNP}}
    restore = {"status": "PASS", "candidate_sha256": SHA,
               "physical_write": {"partition": "mtd4/linux_live", "offset": 0x7e0000, "slot_size": 0x7a0000},
               "readback": {"full_slot_crc32": "d6b13baa", "candidate_prefix_compare": "PASS"},
               "protected_partitions": {"status": "PASS"}, "evidence": evidence}
    platform = {"schema": "openmitrastar.f214-device-postflash/v1", "host": "192.168.1.90", "status": "PASS",
                "checks": {name: True for name in ("ssh_pinned_identity", "kernel", "release", "boot_ready",
                                                   "radio2_ready", "radio5_ready", "no_fatal")}}
    for path, data in ((directory / "result.json", report), (restore_dir / "result.json", restore),
                       (platform_dir / "status.json", platform)):
        path.write_text(json.dumps(data), encoding="utf-8")
    return directory / "result.json"


@pytest.mark.parametrize("case", ["valid", "interrupted", "wrong-image", "wrong-slot", "changed-log", "missing-log", "bad-radio", "missing-check"])
def test_recovery_proof_is_not_just_a_status_string(tmp_path, case):
    result = make_proof(tmp_path)
    target = result
    if case in ("interrupted", "wrong-image"):
        data = json.loads(target.read_text())
        data["status" if case == "interrupted" else "f314_sha256"] = "wrong"
        target.write_text(json.dumps(data))
    elif case == "wrong-slot":
        target = tmp_path / "f314-restore/result.json"
        data = json.loads(target.read_text())
        data["physical_write"]["partition"] = "mtd3/linux_safety"
        target.write_text(json.dumps(data))
    elif case in ("changed-log", "missing-log"):
        target = tmp_path / "f314-restore/fixture-0.log"
        if case == "changed-log": target.write_text("changed")
        else: target.unlink()
    elif case in ("bad-radio", "missing-check"):
        target = tmp_path / "postflash-f314/status.json"
        data = json.loads(target.read_text())
        if case == "bad-radio": data["checks"]["radio5_ready"] = False
        else: del data["checks"]["ssh_pinned_identity"]
        target.write_text(json.dumps(data))
    run = ps(f"$ErrorActionPreference='Stop'; . '{HELPER}'; Get-F319VerifiedRecoveryRehearsal -ResultPath '{result}' | ConvertTo-Json")
    assert (run.returncode == 0) is (case == "valid"), run.stdout + run.stderr


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
def test_live_same_process_lease_required(tmp_path, engine):
    script = r'''
$ErrorActionPreference='Stop'
. ./tools/f319_uart_guard.ps1
. ./tools/f319_recovery_guard.ps1
function Get-F319SerialDevice { [pscustomobject]@{DeviceID='COM999';PNPDeviceID='OFFLINE_RECOVERY_TEST'} }
$lock = Join-Path '__SCOPE__' 'lock'
$guard = Enter-F319HardwareGuard -Port COM999 -ExpectedPnpDeviceId OFFLINE_RECOVERY_TEST -PhysicalLockDir $lock -Owner offline-test -EvidenceDir '__SCOPE__'
try {
    $proof = [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;
        Binding=[pscustomobject]@{NonceObserved=$true;RouterHost='192.168.1.90';ExpectedVersion='lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device';Port='COM999';PnpDeviceId='OFFLINE_RECOVERY_TEST'}}
    $borrowedArguments = @{Guard=$guard;BindingProof=$proof;Port='COM999';ExpectedPnpDeviceId='OFFLINE_RECOVERY_TEST'}
    [void](Assert-F319BorrowedRecoveryGuard @borrowedArguments)
    $rejected=0
    foreach ($mutation in @('token','pid','nonce','board')) {
        $oldToken=$proof.LeaseToken; $oldPid=$proof.OwnerPid; $oldNonce=$proof.Binding.NonceObserved; $oldBoard=$proof.Binding.RouterHost
        switch ($mutation) { token {$proof.LeaseToken='bad'} pid {$proof.OwnerPid=1} nonce {$proof.Binding.NonceObserved=$false} board {$proof.Binding.RouterHost='192.168.1.1'} }
        try { [void](Assert-F319BorrowedRecoveryGuard @borrowedArguments) } catch { $rejected++ }
        $proof.LeaseToken=$oldToken; $proof.OwnerPid=$oldPid; $proof.Binding.NonceObserved=$oldNonce; $proof.Binding.RouterHost=$oldBoard
    }
    $guard.LeaseStream.Dispose()
    try { [void](Assert-F319BorrowedRecoveryGuard @borrowedArguments) } catch { $rejected++ }
    if ($rejected -ne 5) { throw "Expected five rejected proofs, got $rejected" }
    'LIVE_LEASE_AND_FIVE_REJECTIONS_PASS_NO_HARDWARE'
} finally { Exit-F319HardwareGuard -Guard $guard }
'''.replace("__SCOPE__", str(tmp_path))
    run = ps(script, engine)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "FIVE_REJECTIONS_PASS_NO_HARDWARE" in run.stdout


def test_promotion_requires_rehearsal_and_keeps_parent_guard_for_rollback():
    source = (ROOT / "tools/promote_f319_mtd4_direct.ps1").read_text()
    assert source.index("$verifiedRecovery = Get-F319VerifiedRecoveryRehearsal") < source.index("$guard = Enter-F319HardwareGuard")
    assert "if ($flashed -and $guard -and $bindingProof)" in source
    assert "-BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof" in source
    assert source.index("OMF319_AUTOMATIC_F314_RESTORE_START") < source.index("Exit-F319HardwareGuard -Guard $guard")
    branch = source[source.index("if (-not $flashed) {"):source.index("$postflash =")]
    assert "$flashed = $true" in branch


def test_standalone_rollback_retains_fresh_ssh_binding():
    source = (ROOT / "tools/rollback_f319_to_f314_mtd4.ps1").read_text()
    assert "$guard = Enter-F319HardwareGuard" in source
    assert "Assert-F319UartBinding" in source
    assert source.index("Assert-F319BorrowedRecoveryGuard") < source.index("reboot_to_topaz_prompt_sysrq.ps1")


@pytest.mark.parametrize("transport,case,rollback_count", [
    ("uart-ymodem", "probe-fails", 1), ("tftp", "probe-fails", 1),
    ("uart-ymodem", "pass", 0), ("uart-ymodem", "writer-fails", 0),
])
def test_actual_promotion_failure_branch_with_all_io_stubbed(tmp_path, transport, case, rollback_count):
    fake_tools = tmp_path / "tools"
    fake_tools.mkdir()
    (fake_tools / "rollback_f319_to_f314_mtd4.ps1").write_text(r'''
param([switch]$Execute,[string]$Ack,[string]$Port,[string]$ExpectedPnpDeviceId,[string]$RouterHost,
      [string]$Transport,[object]$BorrowedHardwareGuard,[object]$RecoveryBindingProof,[string]$RecoveryRehearsalResultPath)
if ($global:offlineExitCount -ne 0) { throw 'parent guard released before rollback' }
if (-not $BorrowedHardwareGuard -or -not $RecoveryBindingProof) { throw 'missing live parent proof' }
$global:offlineRollbackCount++
''', encoding="utf-8")
    script = r'''
$ErrorActionPreference='Stop'
$root='__ROOT__'; $runDir='__ROOT__/run'; $build='__ROOT__'
$Transport='__TRANSPORT__'; $global:offlineFailure='__CASE__'
$Port='COM999'; $ExpectedPnpDeviceId='OFFLINE'; $sharedLockDir='unused'; $RouterHost='192.168.1.90'
$currentKnownHosts='unused'; $f319KnownHosts='unused'; $currentVersion='F314'; $expectedVersion='F319'
$runner='offline-writer'; $common=@(); $TftpHost='unused'; $stamp='offline'; $probeAck='unused'
$expectedSha256='unused'; $currentF314FullSlotCrc32='unused'
$verifiedRecovery=[pscustomobject]@{ResultPath='offline-proof'}
$global:offlineExitCount=0; $global:offlineRollbackCount=0
function Enter-F319HardwareGuard { [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=42;LeaseToken='offline'} }
function Assert-F319UartBinding { [pscustomobject]@{NonceObserved=$true} }
function Exit-F319HardwareGuard { $global:offlineExitCount++ }
function powershell.exe {
    $global:LASTEXITCODE=0
    if (($args -join ' ') -match 'run_f319_spi_owner_probe' -and $global:offlineFailure -eq 'probe-fails') { $global:LASTEXITCODE=1 }
}
function python {
    $global:LASTEXITCODE=0
    if (($args -join ' ') -match 'offline-writer' -and $global:offlineFailure -eq 'writer-fails') { $global:LASTEXITCODE=1 }
}
$source=Get-Content -LiteralPath '__PROMOTER__' -Raw
$start=$source.IndexOf('$guard = $null')
if ($start -lt 0) { throw 'production try block missing' }
$caught=$false
try { & ([scriptblock]::Create($source.Substring($start))) } catch { $caught=$true }
Write-Output ('OFFLINE_RESULT=' + ([ordered]@{rollback_count=$global:offlineRollbackCount;exit_count=$global:offlineExitCount;caught=$caught;hardware_actions=$false} | ConvertTo-Json -Compress))
'''.replace("__ROOT__", str(tmp_path)).replace("__TRANSPORT__", transport).replace("__CASE__", case).replace(
        "__PROMOTER__", str(ROOT / "tools/promote_f319_mtd4_direct.ps1"))
    run = ps(script)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(next(line.partition("=")[2] for line in run.stdout.splitlines() if line.startswith("OFFLINE_RESULT=")))
    assert result["rollback_count"] == rollback_count, run.stdout + run.stderr
    assert result["exit_count"] == 1
    assert result["caught"] is (case != "pass")
    assert result["hardware_actions"] is False
