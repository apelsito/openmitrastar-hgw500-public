"""PowerShell flow/cmdlet mocks only: no host network, firewall or device access."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "tools/f323_ethernet_runtime.ps1"
PNP = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
AUTH_SHA = "827f7d628cd89344e10fe8d7be39dd7b657f57291a35c45788b5e3f536bceaa4"
SHA323 = "9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11"
SHA321 = "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18"


def quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ps(code: str):
    encoded = base64.b64encode(("$ErrorActionPreference='Stop'\n" + code).encode("utf-16le")).decode()
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def plan(direction="promote"):
    f323 = dict(sha256=SHA323, bytes=5361664, version="lyoko-foundation-6.9.2-f323-browser-compat-f321-device",
                directory=r"C:\offline-f323", known_hosts="known_hosts.f323")
    f321 = dict(sha256=SHA321, bytes=5337088, version="lyoko-foundation-6.8.5-f321-classic-ui-f314-device",
                directory=r"C:\offline-f321", known_hosts="known_hosts.f321")
    image, current = (f323, f321) if direction == "promote" else (f321, f323)
    return dict(schema="openmitrastar.f323-ethernet-plan/v1", mode="dry-run", direction=direction,
                required_ack="OPENMITRASTAR_F323_MTD4_9D8DBD5B" if direction == "promote" else "OPENMITRASTAR_F323_RESTORE_F321_EB8E23AC",
                image=image, current=current, target_host="192.168.1.90", uart_pnp_device_id=PNP,
                transport="ethernet-tftp", write_target="mtd4/linux_live", offset="0x007e0000",
                erase_bytes=0x5e0000, slot_bytes=0x7a0000, executor_review_verified=True,
                network_authorization_verified=True, local_preflight_pass=True, radio_actions_authorized=False,
                network=dict(server_ipv4="192.168.1.249", client_ipv4="192.168.1.90", interface_index=15,
                             interface_alias="Ethernet", python_executable=sys.executable,
                             host_address_or_route_changes_allowed=False),
                network_authorization=dict(path=r"C:\offline-network-authorization.json", sha256=AUTH_SHA),
                preflight=dict(candidate_crc32="81cec636" if direction == "promote" else "bd1135df"),
                physical_lock=r"C:\offline-physical-lock", recovery_rehearsal="offline-rehearsal", environment={})


def setup():
    return f". {quote(RUNTIME)}\n" + f"$script:plan=ConvertFrom-Json {quote(json.dumps(plan()))}\n" + f"$script:rollback=ConvertFrom-Json {quote(json.dumps(plan('rollback')))}\n" + r"""
$script:trace=[Collections.Generic.List[string]]::new()
function Record([string]$Value){[void]$script:trace.Add($Value)}
function Invoke-F323EthernetPlanProcess {throw 'UNMOCKED PLAN PROCESS FORBIDDEN'}
function Invoke-F321Native {throw 'UNMOCKED NATIVE PROCESS FORBIDDEN'}
function Test-F323EthernetAdministrator {return $true}
"""


@pytest.mark.parametrize("mutation", [
    "$ack='wrong'", "$script:plan.required_ack='wrong';$ack='wrong'",
    "$script:plan.executor_review_verified=$false", "$script:plan.network_authorization_verified=$false",
    "$script:plan.local_preflight_pass=$false", "$script:plan.radio_actions_authorized=$true",
    "$script:plan.network.server_ipv4='192.168.1.248'", "$script:plan.network.interface_index=16",
    "$script:plan.offset='0x00040000'", "$script:plan.image.sha256='wrong'",
    "$script:plan.uart_pnp_device_id='OTHER-ADAPTER'", "$script:plan.network.python_executable='relative-python.exe'",
])
def test_ethernet_request_refuses_wrong_ack_review_authority_or_scope_before_effects(mutation):
    report = ps(setup() + "$ack=$script:plan.required_ack\n" + mutation + r"""
$accepted=$false
try{Assert-F323EthernetExecutionRequest -Plan $script:plan -Ack $ack;$accepted=$true}catch{}
@{accepted=$accepted;trace=@($script:trace)} | ConvertTo-Json -Compress
""")
    assert report == {"accepted": False, "trace": []}


@pytest.mark.parametrize("filename,direction", [("promote_f323_ethernet.ps1", "promote"), ("restore_f323_ethernet.ps1", "rollback")])
def test_ethernet_default_entrypoint_has_no_network_firewall_or_hardware_job(filename, direction):
    source = (ROOT / "tools" / filename).read_text()
    source = source.replace(". (Join-Path $PSScriptRoot 'f323_ethernet_runtime.ps1')", "")
    code = setup() + r"""
function Get-F323EthernetPlan {param($Direction) if($Direction -eq 'rollback'){return $script:rollback};return $script:plan}
function Invoke-F323EthernetPhysicalCycle {throw 'DEFAULT MUST NOT ENTER A PHYSICAL CYCLE'}
""" + f". ([scriptblock]::Create({quote(source)}))"
    result = ps(code)
    assert result["mode"] == "dry-run" and result["direction"] == direction


HOST_MOCKS = r"""
function Get-NetAdapter {param([switch]$IncludeHidden) Record 'adapter'; [pscustomobject]@{ifIndex=15;Name='Ethernet';Status='Up';MediaType='802.3'}}
function Get-NetIPAddress {param($InterfaceIndex,$AddressFamily) Record 'address'; [pscustomobject]@{IPAddress='192.168.1.249';PrefixLength=24;AddressState='Preferred';SkipAsSource=$false}}
function Find-NetRoute {
 param($RemoteIPAddress) Record 'route'
 [pscustomobject]@{IPAddress=if($script:bad -eq 'source'){'192.168.1.248'}else{'192.168.1.249'};InterfaceIndex=15}
 [pscustomobject]@{DestinationPrefix='192.168.1.0/24';InterfaceIndex=if($script:bad -eq 'interface'){16}else{15};NextHop=if($script:bad -eq 'gateway'){'192.168.1.1'}else{'0.0.0.0'}}
}
function Get-NetUDPEndpoint {Record 'udp';if($script:bad -eq 'occupied'){[pscustomobject]@{LocalPort=69;LocalAddress='0.0.0.0'}}}
function Get-NetRoute {param($AddressFamily) Record 'default-route';[pscustomobject]@{InterfaceIndex=15;DestinationPrefix='0.0.0.0/0'}}
"""


@pytest.mark.parametrize("bad", ["", "source", "interface", "gateway", "occupied"])
def test_fresh_host_scope_requires_exact_source_direct_route_and_empty_udp69(bad):
    result = ps(setup() + HOST_MOCKS + f"$script:bad={quote(bad)}\n" + r"""
$accepted=$false; $shared=$false
try{$value=Assert-F323EthernetHostNetwork -Plan $script:plan;$accepted=$true;$shared=$value.shared_default_route}catch{}
@{accepted=$accepted;shared=$shared;trace=@($script:trace)} | ConvertTo-Json -Compress
""")
    assert result["accepted"] is (not bad)
    assert result["shared"] is (not bad)
    assert all(value in {"adapter", "address", "route", "udp", "default-route"} for value in result["trace"])


def test_baseline_uses_pinned_read_only_ssh_without_console_nonce(tmp_path):
    (tmp_path / "known_hosts.fixture").write_text("synthetic pin\n", encoding="ascii")
    result = ps(setup() + f"$script:plan.current.directory={quote(tmp_path)}\n" + r"""
$script:plan.current.known_hosts='known_hosts.fixture'
function Invoke-F319SshScript {
 param($SshPath,$Arguments,$Script,$TimeoutSeconds)
 $script:baselineScript=$Script; $script:baselineArguments=$Arguments
 return [pscustomobject]@{ExitCode=0;Stdout='OMF323_ETHERNET_BASELINE_PASS';Stderr=''}
}
""" + f"Invoke-F323EthernetBaseline -Plan $script:plan -RunDir {quote(tmp_path)}\n" + r"""
@{no_console_write=($script:baselineScript -notmatch '/dev/console');pinned=($script:baselineArguments -contains 'StrictHostKeyChecking=yes');
 version_read=($script:baselineScript -match 'grep -Fqx.+/etc/openmitrastar/release')} | ConvertTo-Json -Compress
""")
    assert result == {"no_console_write": True, "pinned": True, "version_read": True}
    assert json.loads((tmp_path / "ssh-baseline.json").read_text())["console_nonce_emitted"] is False


FIREWALL_MOCKS = r"""
$script:store=@{'user-rule'=[pscustomobject]@{Name='user-rule';Description='must survive'}}
$script:removed=[Collections.Generic.List[string]]::new()
$script:guard=[pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=12345L;LeaseToken='offline-token'}
function Get-NetFirewallRule {
 [CmdletBinding()]param($PolicyStore,$Name)
 if($script:store.ContainsKey($Name)){return $script:store[$Name]}
}
function New-NetFirewallRule {
 [CmdletBinding()]param($PolicyStore,$Name,$DisplayName,$Description,$Direction,$Action,$Enabled,$Profile,$EdgeTraversalPolicy,$Protocol,$LocalPort,$RemotePort,$LocalAddress,$RemoteAddress,$InterfaceAlias,$Program)
 Record 'create-rule'
 if($LocalPort -ne 69 -or $RemoteAddress -cne '192.168.1.90' -or $LocalAddress -cne '192.168.1.249' -or $InterfaceAlias -cne 'Ethernet' -or $Program -cne $script:plan.network.python_executable -or $EdgeTraversalPolicy -cne 'Block'){throw 'TEST DETECTED WIDENED FIREWALL SCOPE'}
 $script:store[$Name]=[pscustomobject]@{Name=$Name;Description=$Description;Direction=$Direction;Action=$Action;Enabled=$Enabled;Profile=$Profile;
 EdgeTraversalPolicy=$EdgeTraversalPolicy;Protocol=$Protocol;LocalPort=$LocalPort;RemotePort=$RemotePort;LocalAddress=$LocalAddress;RemoteAddress=$RemoteAddress;InterfaceAlias=$InterfaceAlias;Program=$Program}
 if($script:bad -eq 'creation-error'){throw 'synthetic partial creation failure'}
 return $script:store[$Name]
}
function Get-NetFirewallPortFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject) process{[pscustomobject]@{Protocol=$InputObject.Protocol;LocalPort=$InputObject.LocalPort;RemotePort=$InputObject.RemotePort}}}
function Get-NetFirewallAddressFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject) process{[pscustomobject]@{LocalAddress=$InputObject.LocalAddress;RemoteAddress=if($script:bad -eq 'bad-filter'){'Any'}else{$InputObject.RemoteAddress}}}}
function Get-NetFirewallApplicationFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject) process{[pscustomobject]@{Program=$InputObject.Program}}}
function Get-NetFirewallInterfaceFilter {[CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject) process{[pscustomobject]@{InterfaceAlias=$InputObject.InterfaceAlias}}}
function Remove-NetFirewallRule {[CmdletBinding()]param($PolicyStore,$Name) [void]$script:removed.Add($Name);if($script:bad -ne 'remove-error'){$script:store.Remove($Name)}}
"""


@pytest.mark.parametrize("bad", ["", "creation-error", "bad-filter", "remove-error"])
def test_firewall_is_exact_owned_rule_with_readback_and_scoped_cleanup(tmp_path, bad):
    result = ps(setup() + FIREWALL_MOCKS + f"$script:bad={quote(bad)}\n" + f"""
$accepted=$false;$clean=$false
try{{$rule=New-F323EthernetFirewallRule -Plan $script:plan -Guard $script:guard -RunDir {quote(tmp_path)};$accepted=$true;Remove-F323EthernetFirewallRule -Rule $rule -Guard $script:guard;$clean=$true}}catch{{}}
@{{accepted=$accepted;clean=$clean;names=@($script:store.Keys);removed=@($script:removed);uncertain=$script:F323EthernetUncertain}} | ConvertTo-Json -Compress
""")
    assert "user-rule" in result["names"]
    assert all(name.startswith("OpenMitraStar-F323-Ethernet-") for name in result["removed"])
    if not bad:
        assert result["accepted"] and result["clean"] and result["names"] == ["user-rule"]
    elif bad == "remove-error":
        assert result["accepted"] and not result["clean"] and len(result["names"]) == 2
    else:
        assert not result["accepted"] and result["names"] == ["user-rule"]


CYCLE_MOCKS = r"""
function Test-F323EthernetAdministrator {return ($script:fail -ne 'admin')}
function Assert-F323EthernetHostNetwork {Record 'host';if($script:fail -eq 'host'){throw 'host changed'};return @{direct_route=$true;udp69_empty=$true}}
function Get-F319VerifiedRecoveryRehearsal {Record 'rehearsal'}
function Invoke-F323EthernetBaseline {Record 'baseline';if($script:fail -eq 'baseline'){throw 'SSH baseline failed'}}
function Enter-F319HardwareGuard {Record 'lease';return [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=12345L;LeaseToken='offline-token';PhysicalLockDir='offline';Port='COM3';PnpDeviceId=$script:plan.uart_pnp_device_id;LeaseStream=[IO.MemoryStream]::new()}}
function Assert-F319HardwareLease {Record 'lease-check'}
function Exit-F319HardwareGuard {Record 'release';if($script:fail -eq 'release'){throw 'release failed'}}
function Assert-F319UartBinding {
 param($ExpectedVersion) Record 'binding'
 if($script:fail -eq 'binding'){throw 'binding failed'}
 if($script:fail -eq 'ssh'){$script:F323SshContainmentFailed=$true;throw 'SSH helper remains'}
 return [pscustomobject]@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId=$script:plan.uart_pnp_device_id;ExpectedVersion=$ExpectedVersion}
}
function Create-F323PhysicalContext {param($Direction) Record ('context-'+$Direction);return ('offline-context-'+$Direction)}
function New-F323EthernetFirewallRule {param($Plan,$Guard) Record 'firewall-create';if($script:fail -eq 'firewall'){throw 'firewall creation failed'};return [pscustomobject]@{Name=('OpenMitraStar-F323-Ethernet-'+('a'*32));OwnerPid=$PID;OwnerStartTicks=$Guard.OwnerStartTicks;LeaseToken=$Guard.LeaseToken}}
function Assert-F323EthernetFirewallRule {Record 'firewall-check'}
function Remove-F323EthernetFirewallRule {Record 'firewall-remove';if($script:fail -eq 'cleanup'){throw 'rule removal unproved'}}
function Invoke-F323Reboot {param($Plan) Record ('reboot-'+$Plan.direction)}
function Set-F321WriterEnvironment {Record 'writer-env-set';return @{}}
function Restore-F321WriterEnvironment {Record 'writer-env-restored'}
function Get-F323EthernetPlan {param($Direction) Record ('plan-'+$Direction);if($Direction -cne 'rollback'){throw 'unexpected new direction'};return $script:rollback}
function Invoke-F321PlatformGate {param($Plan) Record ('platform-'+$Plan.direction);if($script:fail -eq 'platform' -and $Plan.direction -eq 'promote'){throw 'postgate failed'}}
function Invoke-F323UiGate {param($Plan) Record ('ui-'+$Plan.direction);if($script:fail -in @('ui','rollback-writer') -and $Plan.direction -eq 'promote'){throw 'UI failed'}}
function Argument([object[]]$Arguments,[string]$Name){return $Arguments[[Array]::IndexOf($Arguments,$Name)+1]}
function Invoke-F321Native {
 param($Program,$Arguments,$LogPrefix,$TimeoutSeconds)
 if($Program -cne $script:plan.network.python_executable){throw 'Unpinned Python program'}
 $direction=Argument $Arguments '--direction'
 $selected=if($direction -ceq 'rollback'){$script:rollback}else{$script:plan}
 $tool=Split-Path -Leaf $Arguments[0]
 if($tool -ceq 'f323_ethernet_load_cli.py'){
   Record ('loader-'+$direction)
   if($script:fail -eq 'loader-job'){$script:F321ContainmentFailed=$true;throw 'Job descendants unproved'}
   $out=Argument $Arguments '--output-dir'
   if(Test-Path -LiteralPath $out){throw 'Loader evidence directory must be new'}
   [void][IO.Directory]::CreateDirectory($out)
   $value=@{schema='openmitrastar.f323-native-ethernet-load/v1';status='PASS_NATIVE_ETHERNET_RAM_LOAD';candidate_sha256=$selected.image.sha256;candidate_bytes=$selected.image.bytes;
      target_host='192.168.1.90';server_ipv4='192.168.1.249';ram_handoff_ready=$true;writer_ready=$false;native_cleanup_verified=$true;retain_lease_required=$false;
      flash_written=$false;rebooted=$false;host_network_or_firewall_changed=$false;loader_process_exit_observed_by_parent=$false;
      cleanup=@{server=$true;uart=$true;guard_helpers=$true};ram_result=@{status='PASS_ETHERNET_RAM_GATE';candidate_sha256=$selected.image.sha256;candidate_bytes=$selected.image.bytes;
      candidate_crc32=$selected.preflight.candidate_crc32;server_closed=$true;flash_writes=0}}
   if($script:fail -eq 'loader-status'){$value.status='UNKNOWN'}
   if($script:fail -eq 'loader-ready'){$value.writer_ready=$true}
   if($script:fail -eq 'loader-cleanup'){$value.native_cleanup_verified=$false;$value.retain_lease_required=$true}
   Write-F323EthernetJson -Path (Join-Path $out 'native-loader-result.json') -Value $value
   Record ('loader-job-closed-'+$direction)
   return ''
 }
 if($tool -ceq 'f323_ethernet_writer.py'){
   Record ('writer-'+$direction)
   if($TimeoutSeconds -ne ([int](Argument $Arguments '--timeout')+600)){throw 'Writer parent deadline lacks cleanup margin'}
   Record ('writer-parent-timeout-'+$TimeoutSeconds)
   $pre=$env:OM_F323_ETHERNET_PRELOADED | ConvertFrom-Json
   if($pre.schema -cne 'openmitrastar.f323-ethernet-preloaded/v1' -or $pre.loader_job_closed -ne $true -or $pre.direction -cne $direction -or $pre.candidate_sha256 -cne $selected.image.sha256){throw 'Invalid handoff proof'}
   if($pre.native_result_sha256 -cne (Get-F323EthernetBytesSha256 ([IO.File]::ReadAllBytes($pre.native_result_path)))){throw 'Native result hash differs'}
   if($pre.physical_context_sha256 -cne (Get-F323EthernetBytesSha256 ([Text.Encoding]::UTF8.GetBytes($env:OM_F323_PHYSICAL_CONTEXT)))){throw 'Context binding differs'}
   if($script:fail -eq 'writer' -or ($script:fail -eq 'rollback-writer' -and $direction -eq 'rollback')){throw 'Writer outcome ambiguous'}
   Record ('writer-job-closed-'+$direction)
   return ''
 }
 if($tool -ceq 'f323_ethernet_execution_contract.py'){
   Record ('verify-'+$direction)
   $status=if($script:fail -eq 'verify'){'UNKNOWN'}else{'PASS_VERIFIED_ETHERNET_WRITER'}
   return (@{status=$status;candidate_sha256_expected=$selected.image.sha256} | ConvertTo-Json -Compress)
 }
 throw 'UNMOCKED NATIVE TOOL FORBIDDEN'
}
"""


def cycle(tmp_path: Path, failure=""):
    code = setup() + CYCLE_MOCKS + f"$script:fail={quote(failure)}\n" + r"""
$env:OM_F323_PHYSICAL_CONTEXT='prior-context';$env:OM_F323_ETHERNET_PRELOADED='prior-preloaded'
if($script:fail -eq 'prior'){$script:F323EthernetUncertain=$true}
if($script:fail -eq 'internal-noauth'){$script:plan.network_authorization_verified=$false}
""" + f"""
try{{[void](Invoke-F323EthernetPhysicalCycle -Plan $script:plan -RunDir {quote(tmp_path)} -ExecutorReview 'C:\\offline-review.json' -ExecutorReviewSha256 ('c'*64))}}catch{{Record 'caught'}}
if($env:OM_F323_PHYSICAL_CONTEXT -cne 'prior-context' -or $env:OM_F323_ETHERNET_PRELOADED -cne 'prior-preloaded'){{throw 'Phase environment was not restored'}}
ConvertTo-Json -InputObject @($script:trace) -Compress
"""
    trace = ps(code)
    report = json.loads((tmp_path / "result.json").read_text(encoding="utf-8-sig"))
    return trace, report


def test_cycle_orders_host_baseline_lease_binding_firewall_reboot_job_and_writer(tmp_path):
    trace, report = cycle(tmp_path)
    ordered = ["host", "baseline", "lease", "binding", "firewall-create", "context-promote", "reboot-promote",
               "loader-promote", "loader-job-closed-promote", "writer-promote", "writer-job-closed-promote",
               "verify-promote", "platform-promote", "ui-promote", "firewall-remove", "release"]
    assert [trace.index(value) for value in ordered] == sorted(trace.index(value) for value in ordered)
    assert report["status"] == "PASS_F323_ETHERNET_BOOT_PLATFORM_HTTP"
    assert report["writer_verified"] and report["lease_released"] and report["firewall_cleanup_verified"]
    assert not report["automatic_recovery_started"] and not report["release_eligible"]


@pytest.mark.parametrize("failure", ["admin", "prior", "internal-noauth", "host", "baseline", "binding", "ssh", "firewall"])
def test_early_failure_never_reboots_or_starts_loader(tmp_path, failure):
    trace, report = cycle(tmp_path, failure)
    assert not any(value.startswith(("reboot-", "loader-", "writer-promote")) for value in trace)
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY" and not report["automatic_recovery_started"]
    if failure in {"admin", "prior", "internal-noauth"}:
        assert "host" not in trace and "lease" not in trace
    if failure == "ssh":
        assert "release" not in trace and report["retain_lease_required"]
    assert report["failed_stage"] is not None


def test_writer_parent_timeout_includes_cleanup_margin(tmp_path):
    trace, report = cycle(tmp_path)
    assert "writer-parent-timeout-2400" in trace
    assert report["status"] == "PASS_F323_ETHERNET_BOOT_PLATFORM_HTTP"


@pytest.mark.parametrize("missing", ["all", "BorrowedHardwareGuard", "RecoveryBindingProof", "BorrowedFirewallRule", "nonobjects"])
def test_unborrowed_rollback_is_rejected_before_admin_host_or_device_effects(tmp_path, missing):
    code = setup() + CYCLE_MOCKS + r"""
$script:fail=''
function Test-F323EthernetAdministrator {Record 'admin';return $true}
$borrowed=@{BorrowedHardwareGuard=[pscustomobject]@{fixture=$true};
    RecoveryBindingProof=[pscustomobject]@{fixture=$true};BorrowedFirewallRule=[pscustomobject]@{fixture=$true}}
""" + f"$missing={quote(missing)}\n" + r"""
if($missing -eq 'all'){$borrowed.Clear()}
elseif($missing -eq 'nonobjects'){$borrowed.BorrowedHardwareGuard=$false;$borrowed.RecoveryBindingProof=$false;$borrowed.BorrowedFirewallRule=$false}
else{$borrowed.Remove($missing)}
$refused=$false
""" + f"""
try{{[void](Invoke-F323EthernetPhysicalCycle -Plan $script:rollback -RunDir {quote(tmp_path)} @borrowed -ExecutorReview 'C:\\offline-review.json' -ExecutorReviewSha256 ('c'*64))}}catch{{$refused=$true}}
@{{refused=$refused;trace=@($script:trace)}} | ConvertTo-Json -Compress
"""
    result = ps(code)
    assert result == {"refused": True, "trace": []}
    report = json.loads((tmp_path / "result.json").read_text())
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY"
    assert report["failed_stage"] == "conditional-rollback"
    assert report["automatic_recovery_started"] is False and report["writer_verified"] is False


@pytest.mark.parametrize("failure", ["loader-status", "loader-ready", "loader-cleanup", "loader-job", "writer", "verify"])
def test_ambiguous_loader_or_writer_never_starts_automatic_recovery(tmp_path, failure):
    trace, report = cycle(tmp_path, failure)
    assert "plan-rollback" not in trace and "writer-rollback" not in trace
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY" and not report["writer_verified"]
    if failure.startswith("loader"):
        assert "writer-promote" not in trace
    if failure in {"loader-cleanup", "loader-job"}:
        assert "release" not in trace and report["retain_lease_required"]


@pytest.mark.parametrize("failure", ["platform", "ui"])
def test_postgate_failure_restores_once_with_same_lease_and_firewall(tmp_path, failure):
    trace, report = cycle(tmp_path, failure)
    assert trace.count("writer-rollback") == 1 and trace.count("plan-rollback") == 1
    assert trace.count("lease") == trace.count("baseline") == trace.count("firewall-create") == 1
    assert trace.count("release") == trace.count("firewall-remove") == 1
    assert "plan-fallback" not in trace and report["status"] == "FAIL_F323_EXACT_F321_RESTORED"
    restored = json.loads((tmp_path / "automatic-exact-f321-rollback/result.json").read_text())
    assert restored["status"] == "PASS_EXACT_F321_RESTORED" and restored["firewall_cleanup_deferred_to_owner"]


def test_failed_f321_restore_never_chains_another_attempt_or_f314(tmp_path):
    trace, report = cycle(tmp_path, "rollback-writer")
    assert trace.count("writer-rollback") == 1 and trace.count("plan-rollback") == 1
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY" and "plan-fallback" not in trace


@pytest.mark.parametrize("failure", ["cleanup", "release"])
def test_cleanup_uncertainty_is_reported_and_blocks_lease_release_or_next_cycle(tmp_path, failure):
    trace, report = cycle(tmp_path, failure)
    assert report["status"] == "STOP_NO_AUTOMATIC_RETRY" and report["retain_lease_required"]
    assert report["helper_containment_verified"] is False and report["lease_released"] is False
    if failure == "cleanup": assert "release" not in trace
