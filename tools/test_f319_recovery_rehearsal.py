"""Local-only preflight and source boundaries for the F314 recovery rehearsal."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f319_bootbase_recovery_rehearsal.ps1"


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
def test_real_local_contract_without_hardware(engine, tmp_path):
    unused = tmp_path / "not-created"
    run = subprocess.run([engine, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                          "-OutputDir", str(unused)], cwd=ROOT, capture_output=True, text=True, timeout=40)
    assert run.returncode == 0, run.stderr
    plan = json.loads(run.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["local_preflight_pass"] is True
    assert plan["hardware_actions_performed"] is False
    assert plan["candidate_sha256"] == "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
    assert plan["candidate_bytes"] == 5292032
    assert plan["current_and_restored_full_slot_crc32"] == "d6b13baa"
    assert plan["bootenv_write"] is False
    assert not unused.exists()


def test_guard_binding_before_reboot_and_restore():
    source = SCRIPT.read_text()
    assert source.index("if (-not $Execute)") < source.index("$guard = Enter-F319HardwareGuard")
    assert source.index("$baseline = Invoke-F319SshScript") < source.index("$guard = Enter-F319HardwareGuard")
    assert source.index("$guard = Enter-F319HardwareGuard") < source.index("$report.binding = Assert-F319UartBinding")
    assert source.index("$report.binding = Assert-F319UartBinding") < source.index("tools/reboot_to_topaz_prompt_sysrq.ps1")
    assert source.index("tools/reboot_to_topaz_prompt_sysrq.ps1") < source.index("& python $runner @common --execute")
    assert "Exit-F319HardwareGuard -Guard $guard" in source
    assert "'--transport', 'uart-ymodem'" in source
    assert "'--skip-reboot', '--uart-attach-topaz'" in source
    assert "recover_to_oem_safety" not in source
    assert "saveenv" not in source and "ATEN " not in source


def test_all_protected_partitions_rechecked_after_write():
    source = (ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1").read_text()
    write = source.index("'mtd4 candidate write'")
    boot = source.index("Send-Uart 'bootselect'")
    for partition in (0, 1, 2, 3, 5):
        assert write < source.index(f"'postwrite protected mtd{partition}'") < boot


def test_wrong_ack_stops_before_evidence_or_hardware(tmp_path):
    unused = tmp_path / "not-created"
    run = subprocess.run(["pwsh.exe", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                          "-Execute", "-Ack", "wrong", "-OutputDir", str(unused)],
                         cwd=ROOT, capture_output=True, text=True, timeout=40)
    assert run.returncode != 0
    assert "acknowledgement required" in run.stderr
    assert not unused.exists()


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
def test_pnp_only_adapter_lookup_without_opening_a_port(engine):
    source = (ROOT / "tools/reboot_to_topaz_prompt_sysrq.ps1").read_text()
    assert source.index("Get-F319SerialDevice -Port") < source.index("$serial.Open()")
    script = r'''
. ./tools/f319_uart_guard.ps1
function Get-CimInstance { @() }
function Get-PnpDevice { [pscustomobject]@{InstanceId='OFFLINE_TEST_ADAPTER';FriendlyName='Synthetic UART (COM999)'} }
$device = Get-F319SerialDevice -Port COM999 -ExpectedPnpDeviceId OFFLINE_TEST_ADAPTER
if ($device.PNPDeviceID -ne 'OFFLINE_TEST_ADAPTER') { throw 'synthetic lookup failed' }
$rejected = $false
try { Get-F319SerialDevice -Port COM999 -ExpectedPnpDeviceId WRONG | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'wrong identity accepted' }
'OFFLINE_PNP_ONLY_PASS'
'''
    run = subprocess.run([engine, "-NoProfile", "-NonInteractive", "-Command", script],
                         cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert "OFFLINE_PNP_ONLY_PASS" in run.stdout
