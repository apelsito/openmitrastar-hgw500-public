"""Existing-permission mode: local fixtures and cmdlet mocks, never device/network access."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

import f325_existing_permission_contract as permission
import f325_ethernet_execution_contract as contract
import test_f325_ethernet_runtime as flow


def ps_file(code):
    # This fixture is larger than Windows' 32767-character command-line limit.
    with tempfile.TemporaryDirectory(prefix="f326-permission-tests-") as directory:
        path = Path(directory) / "mock-only.ps1"
        path.write_text("$ErrorActionPreference='Stop'\n" + code, encoding="utf-8")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(path)],
                                cwd=flow.ROOT, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)


def binding():
    return permission.validate_permission(permission.PERMISSION, permission.PERMISSION_SHA,
                                          python_executable=permission.PROGRAM)


def existing_setup():
    value = flow.quote(json.dumps(binding()))
    return flow.setup() + f"""
$script:permission=ConvertFrom-Json {value}
$script:plan.network.firewall_mode='existing-permission'
$script:plan.network.existing_permission=$script:permission
$script:plan.network.python_executable=$script:permission.python_executable
$script:rollback.network.firewall_mode='existing-permission'
$script:rollback.network.existing_permission=$script:permission
$script:rollback.network.python_executable=$script:permission.python_executable
"""


SNAPSHOT_MOCKS = r"""
$script:p=$script:permission.projection
function Get-Item {param($LiteralPath)
 if($LiteralPath -ieq $script:F325ExistingProgram){return [pscustomobject]@{PSIsContainer=$false;Attributes=0;FullName=$LiteralPath;Length=100}}
 Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath
}
function Get-F325PermissionFileSha256 {param($Path)
 if($Path -ieq $script:F325ExistingProgram){return $script:p.program_sha256}
 $sha=[Security.Cryptography.SHA256]::Create()
 try{return (-join($sha.ComputeHash([IO.File]::ReadAllBytes($Path)) | ForEach-Object{$_.ToString('x2')}))}finally{$sha.Dispose()}
}
function Get-NetFirewallRule {param($PolicyStore,$Name)
 Record 'read-rule'
 if($PolicyStore -cne 'ActiveStore' -or $Name -cne $script:F325ExistingRuleName){throw 'Wrong rule lookup'}
 if($script:missing){return}
 $r=[pscustomobject]@{Name=$script:F325ExistingRuleName;Enabled=$script:p.enabled;Direction=$script:p.direction;Action=$script:p.action;
 Profile=$script:p.profile;EnforcementStatus=$script:p.enforcement;EdgeTraversalPolicy=$script:p.edge;
 PolicyStoreSource=$script:p.policy_source;PolicyStoreSourceType=$script:p.policy_source_type;
 LocalOnlyMapping=$script:p.local_only_mapping;LooseSourceMapping=$script:p.loose_source_mapping;Platform=$script:p.platform}
 $r; if($script:duplicate){$r}
}
function Get-NetFirewallApplicationFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{Program=$script:p.program;Package=$script:p.package}}}
function Get-NetFirewallPortFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{Protocol=$script:p.protocol;LocalPort=$script:p.local_port;RemotePort=$script:p.remote_port;IcmpType=$script:p.icmp_type;DynamicTarget=$script:p.dynamic_target}}}
function Get-NetFirewallAddressFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{LocalAddress=$script:p.local_address;RemoteAddress=$script:p.remote_address}}}
function Get-NetFirewallInterfaceFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{InterfaceAlias=$script:p.interface_alias}}}
function Get-NetFirewallInterfaceTypeFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{InterfaceType=$script:p.interface_type}}}
function Get-NetFirewallServiceFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{Service=$script:p.service}}}
function Get-NetFirewallSecurityFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)process{[pscustomobject]@{Authentication=$script:p.authentication;Encryption=$script:p.encryption;OverrideBlockRules=$script:p.override_block_rules;LocalUser=$script:p.security_local_user;RemoteUser=$script:p.remote_user;RemoteMachine=$script:p.remote_machine}}}
function Get-NetConnectionProfile {param($InterfaceIndex)
 if($InterfaceIndex -ne 18){throw 'Wrong interface profile lookup'}
 [pscustomobject]@{InterfaceIndex=[int]$script:p.connection_interface_index;InterfaceAlias=$script:p.connection_interface_alias;NetworkCategory=$script:p.connection_profile}
}
function Get-NetFirewallProfile {param($PolicyStore,$Name)
 if($PolicyStore -cne 'ActiveStore' -or $Name -cne 'Public'){throw 'Wrong firewall profile lookup'}
 [pscustomobject]@{Name='Public';Enabled=$script:p.firewall_profile_enabled;DefaultInboundAction=$script:p.default_inbound;
 DefaultOutboundAction=$script:p.default_outbound;AllowInboundRules=$script:p.allow_inbound_rules;
 AllowLocalFirewallRules=$script:p.allow_local_rules;DisabledInterfaceAliases=$script:p.disabled_interfaces}
}
$script:missing=$false;$script:duplicate=$false
"""


def snapshot(mutation=""):
    return ps_file(existing_setup() + SNAPSHOT_MOCKS + mutation + r"""
$accepted=$false;$fingerprint='';$errorText=''
try{$value=Assert-F325ExistingPermission -Plan $script:plan;$fingerprint=$value.fingerprint_sha256;$accepted=$true}catch{$errorText=$_.Exception.Message}
@{accepted=$accepted;fingerprint=$fingerprint;error=$errorText;trace=@($script:trace)} | ConvertTo-Json -Compress
""")


def test_existing_permission_windows_and_python_fingerprint_match():
    assert permission.projection_fingerprint(binding()["projection"]) == permission.FINGERPRINT
    result = snapshot()
    assert result["fingerprint"] == permission.FINGERPRINT, result


@pytest.mark.parametrize("field,value", [
    ("enabled", "False"), ("direction", "Outbound"), ("action", "Block"), ("profile", "Private"),
    ("enforcement", "NotEnforced"), ("program", r"C:\Other\python.exe"), ("program_sha256", "a" * 64),
    ("protocol", "TCP"), ("local_port", "69"), ("remote_port", "69"),
    ("local_address", "192.168.1.49"), ("remote_address", "192.168.1.90"),
    ("connection_profile", "Private"), ("connection_interface_index", "17"),
    ("connection_interface_alias", "VirtualBox"), ("firewall_profile_enabled", "False"),
    ("allow_inbound_rules", "False"), ("allow_local_rules", "False"), ("default_inbound", "Allow"),
    ("edge", "Allow"), ("remote_user", "Other"), ("service", "Other"),
    ("package", "Other"), ("interface_type", "Wireless"), ("override_block_rules", "True"),
])
def test_existing_permission_any_definition_program_or_profile_drift_is_rejected(field, value):
    assert snapshot(f"$script:p.{field}={flow.quote(value)}\n")["accepted"] is False


@pytest.mark.parametrize("mutation", ["$script:missing=$true\n", "$script:duplicate=$true\n"])
def test_existing_permission_missing_or_duplicate_rule_is_rejected(mutation):
    assert snapshot(mutation)["accepted"] is False


PERMISSION_FLOW = r"""
$script:reads=0
function Test-F325EthernetAdministrator {Record 'FORBIDDEN-admin';throw 'No admin lookup in existing mode'}
function New-F325EthernetFirewallRule {Record 'FORBIDDEN-create';throw 'No rule creation in existing mode'}
function Remove-F325EthernetFirewallRule {Record 'FORBIDDEN-remove';throw 'No rule removal in existing mode'}
function Assert-F325ExistingPermission {
 param($Plan) Record 'permission-check';$script:reads++
 if($script:permissionFail -eq 'before'){throw 'Permission drift before hardware'}
 if($script:permissionFail -eq 'before-transfer' -and $script:reads -ge 3){throw 'Permission drift before transfer'}
 if($script:permissionFail -eq 'after' -and $script:trace.Contains('ui-promote')){throw 'Permission drift at cleanup'}
 return [pscustomobject]@{fingerprint_sha256=$script:F325ExistingFingerprint;firewall_mutation=$false;privilege_request=$false}
}
"""


def existing_cycle(tmp_path, *, fail="", permission_fail="", capture=False):
    code = existing_setup() + flow.CYCLE_MOCKS + PERMISSION_FLOW
    code += f"$script:fail={flow.quote(fail)}\n$script:permissionFail={flow.quote(permission_fail)}\n"
    code += f"""
try{{[void](Invoke-F325EthernetPhysicalCycle -Plan $script:plan -RunDir {flow.quote(tmp_path)} -ExecutorReview 'C:\offline-review.json' -ExecutorReviewSha256 ('c'*64){' -CaptureAndRestore' if capture else ''})}}catch{{Record 'caught'}}
ConvertTo-Json -InputObject @($script:trace) -Compress
"""
    trace = ps_file(code)
    report = json.loads((tmp_path / "result.json").read_text(encoding="utf-8-sig"))
    return trace, report


def test_existing_permission_cycle_never_requests_admin_or_mutates_rules(tmp_path):
    trace, report = existing_cycle(tmp_path, capture=True)
    assert report["status"] == "PASS_DIAGNOSTIC_COMPLETED_F321_RESTORED"
    assert not any(value.startswith("FORBIDDEN") for value in trace)
    assert trace.count("lease") == trace.count("release") == trace.count("writer-rollback") == 1
    assert trace.index("permission-check") < trace.index("host") < trace.index("baseline") < trace.index("lease")
    assert report["existing_permission_unchanged"] and report["firewall_cleanup_verified"]
    assert report["firewall_changes"] is False and report["privilege_requested"] is False
    assert report["lease_released"] and not report["retain_lease_required"]


def test_existing_permission_drift_refuses_before_device_effects(tmp_path):
    trace, report = existing_cycle(tmp_path, permission_fail="before")
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY"
    assert trace == ["permission-check", "caught"]
    assert not report["writer_verified"] and not report["automatic_recovery_started"]


def test_existing_permission_cleanup_drift_blocks_success_and_release(tmp_path):
    trace, report = existing_cycle(tmp_path, permission_fail="after")
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY"
    assert report["retain_lease_required"] and not report["lease_released"]
    assert "release" not in trace and "writer-rollback" not in trace
    assert not any(value.startswith("FORBIDDEN") for value in trace)


def test_existing_permission_drift_before_transfer_never_calls_writer(tmp_path):
    trace, report = existing_cycle(tmp_path, permission_fail="before-transfer")
    assert "reboot-promote" in trace and "loader-promote" not in trace and "writer-promote" not in trace
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY" and not report["automatic_recovery_started"]


def test_existing_permission_postgate_failure_retains_same_permission_and_one_restore(tmp_path):
    trace, report = existing_cycle(tmp_path, fail="ui")
    assert report["status"] == "FAIL_F325_EXACT_F321_RESTORED"
    assert trace.count("lease") == trace.count("release") == trace.count("writer-rollback") == 1
    assert not any(value.startswith("FORBIDDEN") for value in trace)


def test_existing_permission_plan_propagates_exact_mode_and_probe(monkeypatch):
    monkeypatch.setattr(contract.base, "plan", lambda direction: {"direction": direction})
    monkeypatch.setattr(contract.base, "generic_preflight", lambda *_: {})
    value = contract.plan("promote", firewall_mode="existing-permission",
                          existing_permission_path=permission.PERMISSION, existing_permission_sha=permission.PERMISSION_SHA)
    assert value["network"]["firewall_mode"] == "existing-permission"
    assert value["network"]["existing_permission"]["transport_probe"]["sha256"] == permission.PROBE_SHA
    assert value["executor_review_verified"] is False


@pytest.mark.parametrize("kwargs", [
    {"firewall_mode": "skip-admin"}, {"firewall_mode": "existing-permission"},
    {"existing_permission_path": permission.PERMISSION, "existing_permission_sha": permission.PERMISSION_SHA},
    {"firewall_mode": "existing-permission", "existing_permission_path": permission.PERMISSION},
])
def test_existing_permission_cannot_be_implicit_or_fallback(kwargs):
    with pytest.raises(ValueError): contract.plan("promote", **kwargs)


def test_existing_permission_probe_failure_cannot_become_pass_after_rehash(tmp_path, monkeypatch):
    value = json.loads(permission.PROBE.read_text())
    value["client_returncode"] = 4294967295
    path = tmp_path / "probe.json"; path.write_text(json.dumps(value))
    monkeypatch.setattr(permission, "PROBE", path)
    monkeypatch.setattr(permission, "PROBE_SHA", hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError): permission.validate_transfer_probe()


def test_existing_permission_reader_has_no_mutation_or_elevation_path():
    source = (flow.ROOT / "tools/f325_existing_firewall.ps1").read_text()
    for name in ("New-NetFirewallRule", "Remove-NetFirewallRule", "Set-NetFirewall", "RunAs", "Start-Process"):
        assert name not in source
