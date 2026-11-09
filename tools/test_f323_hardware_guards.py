"""Offline F323 ownership/SSH tests; device and lease checks are mocked.

PowerShell loads only function ASTs. No UART, SSH executable, CIM query, physical
lock, firmware builder or writer is invoked. The byte-transport test launches a
local Python stdin receiver in place of SSH.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "tools/f323_hardware_context.ps1"
SSH = ROOT / "tools/f323_ssh_guard.ps1"
F319 = ROOT / "tools/f319_uart_guard.ps1"
F323_SHA = "9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11"
F321_SHA = "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18"
F314_SHA = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
CONTEXT_SHELLS = ("powershell.exe", "pwsh.exe")


def quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def load_functions(path: Path, name: str = "") -> str:
    return f"""
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile({quote(path)},[ref]$tokens,[ref]$errors)
if($errors.Count) {{ throw 'PowerShell source did not parse' }}
foreach($function in $ast.FindAll({{param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}},$true)) {{
    if({quote(name)} -eq '' -or $function.Name -ceq {quote(name)}) {{
        . ([scriptblock]::Create($function.Extent.Text))
    }}
}}
"""


def ps(code: str, *, shell: str = "powershell.exe") -> dict:
    command = "$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n" + code
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


MOCKS = r"""
$script:trace=[Collections.Generic.List[string]]::new()
$script:failPnp=$false; $script:failLease=$false
$script:pnp='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
$script:guard=[pscustomobject]@{
    OwnerPid=$PID;OwnerStartTicks=123456789L;LeaseToken=('a'*32)
    PhysicalLockDir='C:\offline-f323-fixture';Port='COM3';PnpDeviceId=$script:pnp
    LeaseStream=[IO.MemoryStream]::new()
}
$script:proof=[pscustomobject]@{
    OwnerPid=$PID;OwnerStartTicks=$script:guard.OwnerStartTicks;LeaseToken=$script:guard.LeaseToken
    Binding=[pscustomobject]@{NonceObserved=$true;Port='COM3';PnpDeviceId=$script:pnp
        RouterHost='192.168.1.90';ExpectedVersion='lyoko-foundation-6.8.5-f321-classic-ui-f314-device'}
}
function Get-F319SerialDevice {
    param($Port,$ExpectedPnpDeviceId)
    [void]$script:trace.Add('pnp')
    if($script:failPnp -or $Port -cne 'COM3' -or $ExpectedPnpDeviceId -cne $script:pnp){throw 'Mock adapter mismatch'}
}
function Assert-F319HardwareLease {
    param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId)
    [void]$script:trace.Add('lease')
    if($script:failLease -or $PhysicalLockDir -cne $script:guard.PhysicalLockDir -or
       $OwnerPid -ne $script:guard.OwnerPid -or $OwnerStartTicks -ne $script:guard.OwnerStartTicks -or
       $LeaseToken -cne $script:guard.LeaseToken -or $Port -cne 'COM3' -or $ExpectedPnpDeviceId -cne $script:pnp){
        throw 'Mock lease rejected'
    }
}
function Test-InheritedContext {
    param([string]$Sha,[string]$Direction='promote')
    $accepted=$false
    try{[void](Assert-F323InheritedPhysicalContext -CandidateSha256 $Sha -Direction $Direction);$accepted=$true}catch{}
    @{accepted=$accepted;trace=@($script:trace)} | ConvertTo-Json -Compress
}
"""


def context_setup(direction: str = "promote", sha: str = F323_SHA) -> str:
    return load_functions(CONTEXT) + MOCKS + f"""
$encoded=Create-F323PhysicalContext -Guard $script:guard -BindingProof $script:proof -CandidateSha256 '{sha}' -Direction '{direction}'
$context=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json
$script:trace.Clear()
"""


@pytest.fixture(scope="module")
def production_contexts() -> dict[str, dict]:
    """Produce actual production JSON in each engine, with only hardware mocked.

    Context strings stay inside subprocess capture and the test process. These
    carry synthetic lease tokens, never a real hardware lease or serial handle.
    """
    values = {}
    for shell, major in zip(CONTEXT_SHELLS, (5, 7)):
        report = ps(load_functions(CONTEXT) + MOCKS + f"""
$encoded=Create-F323PhysicalContext -Guard $script:guard -BindingProof $script:proof -CandidateSha256 '{F323_SHA}' -Direction promote
@{{encoded=$encoded;major=$PSVersionTable.PSVersion.Major;version=[string]$PSVersionTable.PSVersion;trace=@($script:trace)}} | ConvertTo-Json -Compress
""", shell=shell)
        assert report["major"] == major
        assert report["trace"] == ["pnp", "lease"]
        data = json.loads(base64.b64decode(report["encoded"]).decode("utf-8"))
        assert isinstance(data["created_at_utc"], str)
        assert isinstance(data["expires_at_utc"], str)
        values[shell] = {"encoded": report["encoded"], "data": data, "version": report["version"]}
    return values


def consume_production_context(context: dict, *, shell: str, encoded: str | None = None) -> dict:
    # The consumer mock expects the producer's PID/start values. It deliberately
    # replaces real lease/process checks; no process or mutex is inspected.
    wire = context["encoded"] if encoded is None else encoded
    return ps(load_functions(CONTEXT) + MOCKS + f"""
$script:guard.OwnerPid={int(context['data']['owner_pid'])}
$script:guard.OwnerStartTicks={int(context['data']['owner_start_ticks'])}L
$env:OM_F323_PHYSICAL_CONTEXT={quote(wire)}
$accepted=$false; $createdString=$false; $expiresString=$false; $createdValue=$null; $expiresValue=$null
try {{
    $validated=Assert-F323InheritedPhysicalContext -CandidateSha256 '{F323_SHA}' -Direction promote
    $createdString=$validated.created_at_utc -is [string]
    $expiresString=$validated.expires_at_utc -is [string]
    $createdValue=$validated.created_at_utc; $expiresValue=$validated.expires_at_utc
    $accepted=$true
}} catch {{}}
@{{accepted=$accepted;trace=@($script:trace);major=$PSVersionTable.PSVersion.Major;
   created_string=$createdString;expires_string=$expiresString;created_value=$createdValue;expires_value=$expiresValue}} | ConvertTo-Json -Compress
""", shell=shell)


def encode_context_dates(context: dict, **dates: str) -> str:
    data = dict(context["data"])
    data.update(dates)
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("ascii")


def net_roundtrip_date(value: datetime) -> str:
    # Preserve .NET's exact seven fractional digits and explicit UTC/offset.
    text = value.isoformat(timespec="microseconds")
    return text[:-6] + "0" + text[-6:]


def assert_cross_shell_roundtrip(contexts: dict, producer: str, consumer: str) -> None:
    context = contexts[producer]
    report = consume_production_context(context, shell=consumer)
    assert report == {
        "accepted": True, "trace": ["pnp", "lease"],
        "major": 5 if consumer == "powershell.exe" else 7,
        "created_string": True, "expires_string": True,
        "created_value": context["data"]["created_at_utc"],
        "expires_value": context["data"]["expires_at_utc"],
    }


def test_f323_context_ps5_to_pwsh7_roundtrip(production_contexts) -> None:
    assert_cross_shell_roundtrip(production_contexts, "powershell.exe", "pwsh.exe")


def test_f323_context_pwsh7_to_ps5_roundtrip(production_contexts) -> None:
    assert_cross_shell_roundtrip(production_contexts, "pwsh.exe", "powershell.exe")


def test_f323_context_malformed_dates_rejected_in_both_shells(production_contexts) -> None:
    for consumer, producer in (("powershell.exe", "pwsh.exe"), ("pwsh.exe", "powershell.exe")):
        context = production_contexts[producer]
        for field in ("created_at_utc", "expires_at_utc"):
            original = context["data"][field]
            # The six-digit form can be parsed as a DateTime, but must not be
            # normalized into the stricter production round-trip contract.
            for malformed in ("not-a-date", original[:-7] + original[-6:]):
                wire = encode_context_dates(context, **{field: malformed})
                report = consume_production_context(context, shell=consumer, encoded=wire)
                assert report["accepted"] is False, (consumer, field)
                assert report["trace"] == [], (consumer, field)


def test_f323_context_expired_dates_rejected_in_both_shells(production_contexts) -> None:
    issued = datetime.now(timezone.utc) - timedelta(minutes=91)
    for consumer, producer in (("powershell.exe", "pwsh.exe"), ("pwsh.exe", "powershell.exe")):
        context = production_contexts[producer]
        wire = encode_context_dates(context, created_at_utc=net_roundtrip_date(issued),
                                    expires_at_utc=net_roundtrip_date(issued + timedelta(minutes=90)))
        report = consume_production_context(context, shell=consumer, encoded=wire)
        assert report["accepted"] is False, consumer
        assert report["trace"] == [], consumer


def test_f323_context_non_utc_dates_rejected_in_both_shells(production_contexts) -> None:
    for consumer, producer in (("powershell.exe", "pwsh.exe"), ("pwsh.exe", "powershell.exe")):
        context = production_contexts[producer]
        non_utc = timezone(timedelta(hours=2))
        dates = {field: net_roundtrip_date(datetime.fromisoformat(context["data"][field]).astimezone(non_utc))
                 for field in ("created_at_utc", "expires_at_utc")}
        # Same live instants and ninety-minute duration; only the UTC offset is
        # invalid. The consumer must not normalize it away before validation.
        report = consume_production_context(context, shell=consumer,
                                            encoded=encode_context_dates(context, **dates))
        assert report["accepted"] is False, consumer
        assert report["trace"] == [], consumer


@pytest.mark.parametrize("direction,sha", [("promote", F323_SHA), ("rollback", F321_SHA), ("fallback", F314_SHA)])
def test_valid_context_rechecks_adapter_and_live_lease(direction: str, sha: str) -> None:
    report = ps(context_setup(direction, sha) + f"""
$env:OM_F323_PHYSICAL_CONTEXT=$encoded
Test-InheritedContext -Sha '{sha}' -Direction '{direction}'
""")
    assert report == {"accepted": True, "trace": ["pnp", "lease"]}


@pytest.mark.parametrize("raw", ["", "not-base64", "/w==", "ew==", "W10=", "bnVsbA=="])
def test_missing_or_invalid_context_is_rejected_without_hardware_queries(raw: str) -> None:
    report = ps(load_functions(CONTEXT) + MOCKS + f"""
$env:OM_F323_PHYSICAL_CONTEXT={quote(raw)}
Test-InheritedContext -Sha '{F323_SHA}'
""")
    assert report == {"accepted": False, "trace": []}


@pytest.mark.parametrize("mutation", [
    "$context.schema='other'",
    "$context.schema=@()",
    "$context.direction='rollback'",
    "$context.direction=@()",
    "$context.candidate_sha256='" + F321_SHA + "'",
    "$context.candidate_sha256=@()",
    "$context.owner_pid=0",
    "$context.owner_pid=[string]$PID",
    "$context.owner_start_ticks='123456789'",
    "$context.lease_token='invalid'",
    "$context.physical_lock_dir='relative.lock'",
    "$context.uart_port='COM4'",
    "$context.uart_port=@()",
    "$context.uart_pnp_device_id='OTHER_ADAPTER'",
    "$context.binding.NonceObserved=$false",
    "$context.binding.NonceObserved='true'",
    "$context.binding.RouterHost='192.168.1.1'",
    "$context.binding.RouterHost=@()",
    "$context.binding.Port='COM4'",
    "$context.binding.PnpDeviceId='OTHER_ADAPTER'",
    "$context.binding.PnpDeviceId=@()",
    "$context.binding.ExpectedVersion='lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device'",
    "$context.created_at_utc='invalid'",
    "$context.created_at_utc=[DateTimeOffset]::UtcNow.AddMinutes(-91).ToString('o');"
    "$context.expires_at_utc=([DateTimeOffset]::Parse($context.created_at_utc)).AddMinutes(90).ToString('o')",
    "$context.created_at_utc=[DateTimeOffset]::UtcNow.AddMinutes(1).ToString('o');"
    "$context.expires_at_utc=([DateTimeOffset]::Parse($context.created_at_utc)).AddMinutes(90).ToString('o')",
    "$context.expires_at_utc=([DateTimeOffset]::Parse($context.created_at_utc)).AddMinutes(91).ToString('o')",
])
def test_mismatched_context_is_rejected_before_adapter_or_lease(mutation: str) -> None:
    report = ps(context_setup() + mutation + f"""
$env:OM_F323_PHYSICAL_CONTEXT=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($context | ConvertTo-Json -Depth 6 -Compress)))
Test-InheritedContext -Sha '{F323_SHA}'
""")
    assert report == {"accepted": False, "trace": []}


@pytest.mark.parametrize("mutation,trace", [
    ("$script:failPnp=$true", ["pnp"]),
    ("$script:failLease=$true", ["pnp", "lease"]),
    ("$context.owner_pid+=1", ["pnp", "lease"]),
    ("$context.owner_start_ticks+=1", ["pnp", "lease"]),
    ("$context.lease_token=('b'*32)", ["pnp", "lease"]),
])
def test_live_adapter_and_lease_failures_propagate(mutation: str, trace: list[str]) -> None:
    report = ps(context_setup() + mutation + f"""
$env:OM_F323_PHYSICAL_CONTEXT=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($context | ConvertTo-Json -Depth 6 -Compress)))
Test-InheritedContext -Sha '{F323_SHA}'
""")
    assert report == {"accepted": False, "trace": trace}


@pytest.mark.parametrize("mutation", [
    "$script:proof.OwnerPid+=1",
    "$script:proof.OwnerStartTicks+=1",
    "$script:proof.LeaseToken=('b'*32)",
    "$script:guard.LeaseStream.Dispose()",
    "$script:proof.Binding.NonceObserved=$false",
    "$script:proof.Binding.ExpectedVersion='unrecognized-version'",
])
def test_context_creation_requires_original_in_process_proof(mutation: str) -> None:
    report = ps(load_functions(CONTEXT) + MOCKS + mutation + f"""
$accepted=$false
try{{[void](Create-F323PhysicalContext -Guard $script:guard -BindingProof $script:proof -CandidateSha256 '{F323_SHA}' -Direction promote);$accepted=$true}}catch{{}}
@{{accepted=$accepted;trace=@($script:trace)}} | ConvertTo-Json -Compress
""")
    assert report == {"accepted": False, "trace": []}


def test_f323_binding_is_allowed_for_separately_prepared_recovery_context() -> None:
    report = ps(load_functions(CONTEXT) + MOCKS + f"""
$script:proof.Binding.ExpectedVersion='lyoko-foundation-6.9.2-f323-browser-compat-f321-device'
$env:OM_F323_PHYSICAL_CONTEXT=Create-F323PhysicalContext -Guard $script:guard -BindingProof $script:proof -CandidateSha256 '{F321_SHA}' -Direction rollback
$script:trace.Clear()
Test-InheritedContext -Sha '{F321_SHA}' -Direction rollback
""")
    assert report == {"accepted": True, "trace": ["pnp", "lease"]}


def test_exact_candidate_must_match_action_even_when_context_agrees() -> None:
    report = ps(context_setup() + f"""
$context.candidate_sha256='{F321_SHA}'
$env:OM_F323_PHYSICAL_CONTEXT=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($context | ConvertTo-Json -Depth 6 -Compress)))
Test-InheritedContext -Sha '{F321_SHA}' -Direction promote
""")
    assert report == {"accepted": False, "trace": []}


@pytest.mark.parametrize("mode,accepted,sticky", [
    ("kill-fails", False, True),
    ("wait-false", False, True),
    ("wait-throws", False, True),
    ("exit-unproven", False, True),
    ("stopped", True, False),
    ("already-exited", True, False),
])
def test_ssh_stop_proves_exit_or_sets_sticky_failure(mode: str, accepted: bool, sticky: bool) -> None:
    report = ps(load_functions(SSH) + f"$script:mode='{mode}'\n" + r"""
$script:F323SshContainmentFailed=$false
$fake=[pscustomobject]@{HasExited=($script:mode -eq 'already-exited')}
$fake | Add-Member ScriptMethod Kill {if($script:mode -eq 'kill-fails'){throw 'mock kill failure'}}
$fake | Add-Member ScriptMethod WaitForExit {
    param($milliseconds)
    if($script:mode -eq 'wait-throws'){throw 'mock wait failure'}
    if($script:mode -eq 'wait-false'){return $false}
    if($script:mode -ne 'exit-unproven'){$this.HasExited=$true}
    return $true
}
$accepted=$false
try{Stop-F323SshProcess -Process $fake -Started $true -TimeoutMilliseconds 1;$accepted=$true}catch{}
@{accepted=$accepted;sticky=$script:F323SshContainmentFailed} | ConvertTo-Json -Compress
""")
    assert report == {"accepted": accepted, "sticky": sticky}


def test_success_after_uncertain_stop_cannot_clear_sticky_failure() -> None:
    report = ps(load_functions(SSH) + r"""
$script:F323SshContainmentFailed=$false
$failed=[pscustomobject]@{HasExited=$false}
$failed | Add-Member ScriptMethod Kill {throw 'mock kill failure'}
try{Stop-F323SshProcess -Process $failed -Started $true}catch{}
$good=[pscustomobject]@{HasExited=$true}
Stop-F323SshProcess -Process $good -Started $true
Stop-F323SshProcess -Process $good -Started $false
@{sticky=$script:F323SshContainmentFailed} | ConvertTo-Json -Compress
""")
    assert report == {"sticky": True}


def test_stdin_transport_preserves_quotes_and_lf_without_bom_using_local_receiver() -> None:
    receiver = "import json,sys; print(json.dumps(list(sys.stdin.buffer.read())))"
    script = "grep 'exact value' /tmp/file\r\necho done"
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    report = ps(load_functions(F319, "ConvertTo-F319NativeArgument") + load_functions(SSH) + f"""
$script:F323SshContainmentFailed=$false
$payload=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{script_b64}'))
$result=Invoke-F319SshScript -SshPath {quote(sys.executable)} -Arguments @('-c',{quote(receiver)}) -Script $payload
[int[]]$receivedBytes=$result.Stdout | ConvertFrom-Json
@{{exit_code=$result.ExitCode;bytes=$receivedBytes;sticky=$script:F323SshContainmentFailed}} | ConvertTo-Json -Compress
""")
    assert report == {
        "exit_code": 0,
        "bytes": list((script.replace("\r\n", "\n") + "\n").encode("utf-8")),
        "sticky": False,
    }
