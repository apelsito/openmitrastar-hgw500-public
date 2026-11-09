"""F325 executor qualification with mocked hardware and local-only dry runs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

import f325_execution_contract as contract
import f325_mtd4_one_shot as writer

ROOT = contract.ROOT
RUNTIME = ROOT / "tools/f325_mtd4_runtime.ps1"
BACKEND = ROOT / "tools/f325_mtd4_bootbase_flash.ps1"


def quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ps(code: str, shell: str = "powershell.exe"):
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", code],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def extract_functions(path: Path) -> str:
    return f"""$ErrorActionPreference='Stop'; $tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile({quote(path)},[ref]$tokens,[ref]$errors)
if($errors.Count){{throw 'parse failure'}}
foreach($node in $ast.EndBlock.Statements){{if($node -is [Management.Automation.Language.FunctionDefinitionAst]){{. ([scriptblock]::Create($node.Extent.Text))}}}}
"""


def fixture_plan(direction="promote") -> dict:
    image, current = contract.images(direction)
    return {"schema":"openmitrastar.f325-mtd4-plan/v1", "direction":direction,
        "required_ack":image["ack"],"executor_review_verified":True,"local_preflight_pass":True,
        "target_host":contract.HOST,"uart_pnp_device_id":contract.PNP,"write_target":"mtd4/linux_live",
        "transport":"uart-ymodem","offset":"0x007e0000","erase_bytes":contract.ERASE_BYTES,
        "slot_bytes":contract.SLOT_BYTES,"radio_actions_authorized":False,
        "image":image,"current":current,"physical_lock":"fixture-only","recovery_rehearsal":"fixture-only",
        "f321_acceptance":{"fixture":True}}


def cycle(tmp_path: Path, fail: str = "") -> tuple[list, dict]:
    setup = f". {quote(RUNTIME)}\n" + r"""
$script:trace=[Collections.Generic.List[string]]::new()
function Record([string]$Text){$script:trace.Add($Text)}
function Invoke-F321Native {throw 'UNMOCKED NATIVE OPERATION BLOCKED BY TEST'}
function Get-F319VerifiedRecoveryRehearsal {Record 'rehearsal'}
function Enter-F319HardwareGuard {
 Record 'lease'; if($script:fail -eq 'busy'){throw 'shared lock occupied'}
 return [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=1;LeaseToken='fixture';PhysicalLockDir='fixture';LeaseStream=[IO.MemoryStream]::new()}
}
function Exit-F319HardwareGuard {Record 'release'}
function Assert-F319HardwareLease {Record 'lease-check'; if($script:fail -eq 'lease'){throw 'lease lost'}}
function Assert-F319UartBinding {
 param($ExpectedVersion)
 Record 'binding'
 if($script:fail -eq 'binding'){throw 'wrong board'}
 if($script:fail -eq 'ssh'){$script:F325SshContainmentFailed=$true;throw 'SSH termination uncertain'}
 return [pscustomobject]@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion=$ExpectedVersion}
}
function Create-F325PhysicalContext {param($Direction) Record ('context-'+$Direction);return 'fixture-context'}
function Invoke-F325Reboot {Record 'reboot'}
function Invoke-F325Writer {
 param($Plan)
 Record ('writer-'+$Plan.direction)
 if($script:fail -eq 'writer' -and $Plan.direction -eq 'promote'){throw 'ambiguous writer'}
 if($script:fail -eq 'unknown' -and $Plan.direction -eq 'promote'){return [pscustomobject]@{status='UNKNOWN'}}
 if($script:fail -eq 'rollback' -and $Plan.direction -eq 'rollback'){throw 'rollback uncertain'}
 return [pscustomobject]@{status='PASS_VERIFIED_WRITER'}
}
function Invoke-F321PlatformGate {param($Plan) Record ('platform-'+$Plan.direction);if($script:fail -eq 'platform' -and $Plan.direction -eq 'promote'){throw 'platform failed'}}
function Invoke-F325UiGate {
 param($Plan) Record ('ui-'+$Plan.direction)
 if($script:fail -eq 'containment'){$script:F321ContainmentFailed=$true;throw 'job not terminated'}
 if($script:fail -in @('ui','rollback') -and $Plan.direction -eq 'promote'){throw 'UI failed'}
}
function Get-F325Plan {param($Direction) Record ('plan-'+$Direction);return $script:rollback}
"""
    # Avoid PowerShell single-quoted fixture backslash doubling: JSON below is
    # the only source of the actual PNP binding used by the borrowed guard.
    setup = setup.replace("FTDIBUS\\VID_0403+PID_6001+AG41W2BLA\\0000", contract.PNP)
    setup += f"$script:promote=ConvertFrom-Json {quote(json.dumps(fixture_plan()))}\n"
    setup += f"$script:rollback=ConvertFrom-Json {quote(json.dumps(fixture_plan('rollback')))}\n"
    setup += f"$script:fail={quote(fail)}; $env:OM_F325_PHYSICAL_CONTEXT='previous-fixture'\n"
    setup += "if($script:fail -eq 'prior-ssh'){$script:F325SshContainmentFailed=$true};if($script:fail -eq 'prior-job'){$script:F321ContainmentFailed=$true}\n"
    setup += f"try{{[void](Invoke-F325PhysicalCycle -Plan $script:promote -RunDir {quote(tmp_path)})}}catch{{Record 'caught'}}\n"
    setup += "if($env:OM_F325_PHYSICAL_CONTEXT -cne 'previous-fixture'){throw 'context not restored'}; ConvertTo-Json -InputObject @($script:trace) -Compress"
    trace = json.loads(ps(setup))
    report = json.loads((tmp_path / "result.json").read_text(encoding="utf-8-sig"))
    return trace, report


def test_f325_dry_run_never_opens_hardware():
    result = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-File",
        str(ROOT / "tools/promote_f325_mtd4_direct.ps1")],cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["mode"] == "dry-run" and value["hardware_actions_performed"] is False
    assert value["executor_review_verified"] is False and value["physical_authorization"] is False


@pytest.mark.parametrize("ack", ["", "wrong", "OPENMITRASTAR_F321_MTD4_EB8E23AC"])
def test_f325_wrong_ack_stops_before_hardware(ack):
    value = quote(json.dumps(fixture_plan()))
    code = f". {quote(RUNTIME)}; $p=ConvertFrom-Json {value}; try{{Assert-F325ExecutionRequest -Plan $p -Ack {quote(ack)} -Port COM3 -ExpectedPnpDeviceId {quote(contract.PNP)} -RouterHost 192.168.1.90;'BAD'}}catch{{'REFUSED'}}"
    assert ps(code) == "REFUSED"


@pytest.mark.parametrize("field,value", [("executor_review_verified",False),("executor_review_verified","true"),
    ("radio_actions_authorized",True),("erase_bytes",0x7a0000),("target_host","192.168.1.1")])
def test_f325_wrong_review_or_scope_is_refused(field, value):
    p=fixture_plan();p[field]=value
    code=f". {quote(RUNTIME)}; $p=ConvertFrom-Json {quote(json.dumps(p))}; try{{Assert-F325ExecutionRequest -Plan $p -Ack $p.required_ack -Port COM3 -ExpectedPnpDeviceId {quote(contract.PNP)} -RouterHost 192.168.1.90;'BAD'}}catch{{'REFUSED'}}"
    assert ps(code)=="REFUSED"


@pytest.mark.parametrize("failure",["busy","binding","lease"])
def test_f325_binding_and_lease_precede_first_transmission(tmp_path,failure):
    trace,_=cycle(tmp_path,failure)
    assert "reboot" not in trace and "writer-promote" not in trace


@pytest.mark.parametrize("failure",["writer","unknown"])
def test_f325_ambiguous_writer_never_restores(tmp_path,failure):
    trace,report=cycle(tmp_path,failure)
    assert "writer-rollback" not in trace and "plan-rollback" not in trace
    assert report["status"]=="STOP_NO_AUTOMATIC_RETRY"


@pytest.mark.parametrize("failure",["ui","platform"])
def test_f325_postgate_failure_restores_exact_f321(tmp_path,failure):
    trace,report=cycle(tmp_path,failure)
    assert trace.count("lease")==1 and trace.count("release")==1
    assert trace.index("binding")<trace.index("reboot")<trace.index("writer-promote")<trace.index("writer-rollback")
    assert trace.count("writer-rollback")==1 and "plan-fallback" not in trace
    assert report["status"]=="FAIL_F325_EXACT_F321_RESTORED"


def test_f325_containment_failure_retains_lease(tmp_path):
    trace,report=cycle(tmp_path,"containment")
    assert "release" not in trace and "writer-rollback" not in trace
    assert report["helper_containment_verified"] is False


def test_f325_ssh_uncertainty_retains_lease(tmp_path):
    trace,report=cycle(tmp_path,"ssh")
    assert "release" not in trace and "reboot" not in trace and "writer-rollback" not in trace
    assert report["helper_containment_verified"] is False


def test_f325_failed_restore_never_chains_f314(tmp_path):
    trace,report=cycle(tmp_path,"rollback")
    assert trace.count("writer-rollback")==1 and "plan-fallback" not in trace
    assert report["status"]=="STOP_NO_AUTOMATIC_RETRY"


def test_f325_success_preserves_goal_boundary(tmp_path):
    trace,report=cycle(tmp_path)
    assert trace.count("writer-promote")==1 and "writer-rollback" not in trace
    assert report["status"]=="PASS_F325_BOOT_PLATFORM_HTTP" and report["release_eligible"] is False


def test_f325_adapter_changes_only_image_pins():
    original=(ROOT / "tools/f321_mtd4_bootbase_flash.ps1").read_text(encoding="utf-8")
    transformed=ps(extract_functions(BACKEND)+f"Get-F325BackendSource -SourcePath {quote(ROOT / 'tools/f321_mtd4_bootbase_flash.ps1')}")
    pattern=r"(?ms)^\$allowed = @\{\n.*?^\}\n"
    normalize = lambda text: re.sub(r"(?m)^\$Root = .*?$", "WORKSPACE", re.sub(pattern,"TABLE\n",text)).strip()
    old_filesize = '"(?im)^filesize={0}\\r?$"'
    new_filesize = '"(?im)^filesize=(?:0x)?{0}\\r?$"'
    assert original.count(old_filesize) == 1 and new_filesize not in original
    assert transformed.count(new_filesize) == 1 and old_filesize not in transformed
    assert normalize(original.replace(old_filesize, new_filesize)) == normalize(transformed)
    assert f"$Root = {quote(ROOT)}" in transformed
    assert "$PSScriptRoot" not in transformed
    for image in (contract.F325,contract.F321,contract.F314):
        assert image["sha256"] in transformed and image["ack"] in transformed


@pytest.fixture(scope="module", params=["powershell.exe", "pwsh.exe"])
def backend_filesize_check(request):
    # Extract only the real transformed string check. Never execute the backend
    # body, open UART, or invoke its command/flash helpers in these tests.
    source = ps(extract_functions(BACKEND) +
                f"Get-F325BackendSource -SourcePath {quote(ROOT / 'tools/f321_mtd4_bootbase_flash.ps1')}", request.param)
    checks = re.findall(r'(?m)^        if \(\$filesize -notmatch [^\n]+\n'
                        r'            throw "preloaded candidate filesize mismatch expected=0x\$expectedHex"\n'
                        r'        \}', source)
    assert len(checks) == 1
    return request.param, checks[0]


@pytest.mark.parametrize("image", [contract.F325, contract.F321], ids=["f325", "f321"])
@pytest.mark.parametrize("prefix", ["", "0x"], ids=["hex", "prefixed-hex"])
def test_f325_backend_filesize_accepts_both_exact_documented_formats(backend_filesize_check, image, prefix):
    shell, check = backend_filesize_check
    response = f"printenv filesize\r\nfilesize={prefix}{image['bytes']:x}\r\ntopaz>"
    code = f"$ErrorActionPreference='Stop';$ExpectedBytes={image['bytes']};$expectedHex=('{{0:x}}' -f $ExpectedBytes);"
    code += f"$filesize={quote(response)};try{{{check};'ACCEPTED'}}catch{{'REFUSED'}}"
    assert ps(code, shell) == "ACCEPTED"


@pytest.mark.parametrize("kind", ["wrong-hex", "wrong-prefixed", "negative", "negative-prefixed",
                                  "trailing-text", "leading-text", "hybrid", "missing-value"])
def test_f325_backend_filesize_rejects_wrong_value_or_extra_text(backend_filesize_check, kind):
    shell, check = backend_filesize_check
    size = contract.F325["bytes"]
    values = {"wrong-hex": f"filesize={size + 1:x}", "wrong-prefixed": f"filesize=0x{size + 1:x}",
              "negative": f"filesize=-{size:x}", "negative-prefixed": f"filesize=-0x{size:x}",
              "trailing-text": f"filesize=0x{size:x} extra", "leading-text": f"extra filesize=0x{size:x}",
              "hybrid": f"filesize=0x{size:x} hex", "missing-value": "filesize=0x"}
    response = "printenv filesize\r\n" + values[kind] + "\r\ntopaz>"
    code = f"$ErrorActionPreference='Stop';$ExpectedBytes={size};$expectedHex=('{{0:x}}' -f $ExpectedBytes);"
    code += f"$filesize={quote(response)};try{{{check};'ACCEPTED'}}catch{{'REFUSED'}}"
    assert ps(code, shell) == "REFUSED"


@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
def test_f325_backend_requires_live_context(shell):
    p=fixture_plan();image=p["image"]
    args={"Candidate":"fixture.bin","ExpectedSha256":image["sha256"],"ExpectedBytes":image["bytes"],"Transcript":"fixture.log",
        "RollbackSha256":"a"*64,"ProtectedMtd0Sha256":"a"*64,"ProtectedMtd1Sha256":"a"*64,"ProtectedMtd2Sha256":"a"*64,"ProtectedMtd5Sha256":"a"*64,
        "ProtectedMtd0Crc32":"00000000","ProtectedMtd1Crc32":"00000000","ProtectedMtd2Crc32":"00000000","ProtectedMtd5Crc32":"00000000",
        "RollbackCrc32":"00000000","CurrentLiveCrc32":"6ed8e483","ExpectedCandidateCrc32":"00000000",
        "ExpectedFullSlotSha256":image["full_slot_sha256"],"ExpectedFullSlotCrc32":image["full_slot_crc32"]}
    pairs=" ".join("-"+key+" "+quote(value) for key,value in args.items())
    code=f"$ErrorActionPreference='Stop';$env:OM_F325_PHYSICAL_CONTEXT=$null;$env:OM_Q3_FLASH_EXPECTED_SHA256={quote(image['sha256'])};$env:OM_Q3_FLASH_EXPECTED_BYTES={quote(image['bytes'])};$env:OM_Q3_FLASH_ACK={quote(image['ack'])};try{{& {quote(BACKEND)} -Execute -Ack {quote(image['ack'])} {pairs};'BAD'}}catch{{if($_.Exception.Message -notmatch 'Missing or oversized'){{throw}};'REFUSED_BEFORE_UART'}}"
    assert ps(code, shell)=="REFUSED_BEFORE_UART"


@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
def test_f325_adapter_real_dry_run_uses_correct_workspace(shell):
    image=contract.F325
    args={"Candidate":str(contract.image_path(image)),"ExpectedSha256":image["sha256"],"ExpectedBytes":image["bytes"],"Transcript":"unused-dry-run.log",
        "RollbackSha256":"a"*64,"ProtectedMtd0Sha256":"a"*64,"ProtectedMtd1Sha256":"a"*64,"ProtectedMtd2Sha256":"a"*64,"ProtectedMtd5Sha256":"a"*64,
        "ProtectedMtd0Crc32":"347cf8db","ProtectedMtd1Crc32":"05624c17","ProtectedMtd2Crc32":"13b7c1f7","ProtectedMtd5Crc32":"1165e46d",
        "RollbackCrc32":"f7d14d3d","CurrentLiveCrc32":"6ed8e483","ExpectedCandidateCrc32":"00000000",
        "ExpectedFullSlotSha256":image["full_slot_sha256"],"ExpectedFullSlotCrc32":image["full_slot_crc32"],"EraseBytes":contract.ERASE_BYTES}
    pairs=" ".join("-"+key+" "+quote(value) for key,value in args.items())
    code=f"$ErrorActionPreference='Stop';$env:OM_F325_PHYSICAL_CONTEXT=$null;$env:OM_Q3_FLASH_EXPECTED_SHA256={quote(image['sha256'])};$env:OM_Q3_FLASH_EXPECTED_BYTES={quote(image['bytes'])};$env:OM_Q3_FLASH_ACK={quote(image['ack'])}; & {quote(BACKEND)} {pairs} -SkipReboot -SkipNetworkTransfer"
    output=ps(code, shell)
    assert "DRY_RUN_PASS=1" in output and "flash=0" in output


@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
def test_f325_serial_api_constructs_without_opening_port(shell):
    code="""$ErrorActionPreference='Stop'
$serial=[IO.Ports.SerialPort]::new('COM3',115200,'None',8,'One')
try {
 $serial.Handshake='None';$serial.DtrEnable=$false;$serial.RtsEnable=$false
 $serial.ReadTimeout=100;$serial.WriteTimeout=2000
 if($serial.IsOpen){throw 'offline probe must never open serial'}
 'SERIAL_API_AVAILABLE_NOT_OPEN'
} finally {$serial.Dispose()}
"""
    assert ps(code, shell)=="SERIAL_API_AVAILABLE_NOT_OPEN"


def test_f325_reboot_source_binds_guard_path_without_changing_behavior():
    path=ROOT/"tools/reboot_to_topaz_prompt_sysrq.ps1"
    original=path.read_text(encoding="utf-8")
    transformed=ps(extract_functions(ROOT/"tools/f325_reboot_to_topaz_prompt.ps1")+f"Get-F325RebootSource -SourcePath {quote(path)}")
    anchor="(Join-Path $PSScriptRoot 'f319_uart_guard.ps1')"
    assert original.count(anchor)==1
    assert transformed==original.replace(anchor,quote(ROOT/"tools/f319_uart_guard.ps1")).strip()
    assert "$PSScriptRoot" not in transformed


def test_f325_reboot_requires_live_context(tmp_path):
    code=f"$ErrorActionPreference='Stop';$env:OM_F325_PHYSICAL_CONTEXT=$null;try{{& {quote(ROOT/'tools/f325_reboot_to_topaz_prompt.ps1')} -CandidateSha256 {quote(contract.F325['sha256'])} -Direction promote -LogPath {quote(tmp_path/'never.log')};'BAD'}}catch{{if($_.Exception.Message -notmatch 'Missing or oversized'){{throw}};'REFUSED_BEFORE_UART'}}"
    assert ps(code)=="REFUSED_BEFORE_UART" and not (tmp_path/'never.log').exists()


def test_f325_writer_missing_context_stops_before_original(monkeypatch):
    monkeypatch.setattr(sys,"argv",["f325", "--execute"])
    monkeypatch.delenv("OM_F325_PHYSICAL_CONTEXT",raising=False)
    monkeypatch.setenv("OM_Q3_FLASH_EXPECTED_SHA256",contract.F325["sha256"])
    monkeypatch.setattr(writer.previous,"main",lambda:pytest.fail("original writer must not run"))
    with pytest.raises(SystemExit,match="inherited physical binding"):
        writer.main()


@pytest.mark.parametrize("failure", [False, True])
def test_f325_writer_selects_receiver_driven_loader_and_restores_it(monkeypatch, failure):
    saved = writer.previous.UART_LOADER
    seen = []
    monkeypatch.setattr(sys, "argv", ["f325"])
    def run():
        seen.append(writer.previous.UART_LOADER)
        if failure:
            raise RuntimeError("offline fixture")
        return 0
    monkeypatch.setattr(writer.previous, "main", run)
    if failure:
        with pytest.raises(RuntimeError, match="fixture"):
            writer.main()
    else:
        assert writer.main() == 0
    assert seen == [writer.UART_LOADER]
    assert writer.previous.UART_LOADER == saved


@pytest.mark.parametrize("arguments",[["--exe"],["--receiver-ready"],["--reboot-sysrq"]])
def test_f325_writer_disallows_alternate_entry_paths(monkeypatch,arguments):
    monkeypatch.setattr(sys,"argv",["f325",*arguments])
    monkeypatch.setattr(writer.previous,"main",lambda:pytest.fail("original writer must not run"))
    with pytest.raises(SystemExit,match="unsupported"):
        writer.main()


def test_f325_only_new_ack_names_are_available():
    assert contract.F325["ack"]=="OPENMITRASTAR_F334_MTD4_E18B221D"
    assert tuple(image["ack"] for image in (contract.F325,contract.F321,contract.F314)) == (
        "OPENMITRASTAR_F334_MTD4_E18B221D",
        "OPENMITRASTAR_F325_RESTORE_F321_EB8E23AC",
        "OPENMITRASTAR_F325_FALLBACK_F314_A0C7350A",
    )


@pytest.mark.parametrize("failure", ["prior-ssh", "prior-job"])
def test_f325_previous_uncertainty_prevents_a_new_cycle(tmp_path, failure):
    trace, report = cycle(tmp_path, failure)
    assert trace == ["caught"]
    assert report["helper_containment_verified"] is False


@pytest.mark.parametrize("bad", ["", "failure", "skipped", "missing"])
def test_f325_qualification_preserves_parameterized_behavior_gates(tmp_path, bad):
    required = sorted(contract.REQUIRED_BEHAVIOR_GATES)
    root = ET.Element("testsuites"); suite = ET.SubElement(root, "testsuite")
    for name in required + ["other_" + str(n) for n in range(12)]:
        case = ET.SubElement(suite, "testcase", name=("absent" if bad == "missing" and name == required[0] else name) + "[fixture]")
    if bad in {"failure", "skipped"}:
        ET.SubElement(case, bad)
    path = tmp_path / "qualification.xml"; ET.ElementTree(root).write(path)
    if bad:
        with pytest.raises(ValueError, match="qualification"):
            contract.qualify_report(path)
    else:
        assert contract.qualify_report(path) == len(required) + 12
