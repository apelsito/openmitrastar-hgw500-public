"""Offline executor gates. No serial, SSH, HTTP, TFTP or flash calls are made."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import f321_execution_contract as contract
import post_flash_f321_ui_gate as ui
import f321_uart_ymodem_load as uart
import f321_mtd4_one_shot as writer


ROOT = contract.ROOT
COMMON = ROOT / "tools/f321_mtd4_runtime.ps1"
BACKEND = ROOT / "tools/f321_mtd4_bootbase_flash.ps1"


def ps(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", code],
                          cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)


def quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def backend_functions() -> str:
    return f"""$ErrorActionPreference='Stop'; $tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile({quote(BACKEND)},[ref]$tokens,[ref]$errors)
if($errors.Count) {{ throw 'backend parser errors' }}
foreach($node in $ast.FindAll({{param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]}},$true)) {{
    . ([scriptblock]::Create($node.Extent.Text))
}}
"""


@pytest.mark.parametrize("text,allowed", [
    ("Total of 5337088 bytes were the same", True),
    ("Total of 0 bytes were the same", False),
    ("Total of 5337087 bytes were the same", False),
    ("Total of 5337088 words were the same", False),
    ("topaz>", False),
])
def test_compare_requires_exact_nonzero_byte_count(text, allowed):
    code = backend_functions() + f"try {{ Assert-F321CompareResponse -Text '{text}' -Bytes 5337088; 'PASS' }} catch {{ 'REFUSED' }}"
    result = ps(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("PASS" if allowed else "REFUSED")


@pytest.mark.parametrize("text", ["spi_flash erase error`ntopaz>", "ERROR: flash busy`ntopaz>", "data abort`ntopaz>"])
def test_error_beats_successful_prompt(text):
    code = backend_functions() + f'$script:tail="{text}"; function Read-Uart {{}}; try {{ [void](Wait-Uart "topaz>" test 1); "BAD" }} catch {{ "REFUSED" }}'
    result = ps(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REFUSED"


@pytest.mark.parametrize("text,allowed", [
    ("Erase: flash=0x7e0000 size=6160384", True),
    ("Erase: flash=0x7e0000 size=0", False),
    ("Erase: flash=0x40000 size=6160384", False),
    ("Erase: flash=0x7e0000 size=6160384`nerror`ntopaz>", False),
    ("topaz>", False),
])
def test_erase_acknowledgement_is_exact(text, allowed):
    result = ps(backend_functions() + f'try {{ Assert-F321EraseResponse -Text "{text}"; "PASS" }} catch {{ "REFUSED" }}')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("PASS" if allowed else "REFUSED")


def test_missing_marker_times_out_without_a_pass():
    result = ps(backend_functions() + '$script:tail=""; function Read-Uart {}; try { [void](Wait-Uart "topaz>" test 0); "BAD" } catch { "REFUSED" }')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REFUSED"


LINUX_BANNER = "Linux version 5.10.260-openmitrastar-radiohw\n"
NETWORK_READY = "OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192.168.1.90\n"
SSH_READY = "OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled\n"
PRODUCT_READY = "OMPRODUCT_READY state=ready\n"
PCI_ALLOCATION_WARNING = "pci 0000:00:00.0: BAR 0: failed to assign [io size 0x0100]\n"


def replay_linux_boot(chunks: list[str], require_product: bool = True) -> list[str]:
    """Run the production boot sequence with queued UART text and short waits."""
    payload = json.dumps(chunks).replace("'", "''")
    code = backend_functions() + f"""
$RequireProductReady=${str(require_product).lower()}
$script:chunks=[Collections.Generic.Queue[string]]::new()
foreach($chunk in (ConvertFrom-Json '{payload}')) {{ $script:chunks.Enqueue($chunk) }}
function Read-Uart {{
    if($script:chunks.Count) {{
        $script:tail += $script:chunks.Dequeue()
        if($script:tail.Length -gt 16384) {{ $script:tail=$script:tail.Substring($script:tail.Length-16384) }}
    }}
}}
function Send-Uart([string]$Text) {{ if($Text -cne 'bootselect') {{ throw 'unexpected UART write' }} }}
$script:realWait=${{function:Wait-Uart}}
function Wait-Uart([string]$Pattern,[string]$Stage,[int]$Seconds,[switch]$LinuxBoot) {{
    & $script:realWait $Pattern $Stage 1 -LinuxBoot:$LinuxBoot
}}
try {{ Wait-F321FlashBoot; 'PASS' }} catch {{ 'REFUSED: '+$_.Exception.Message }}
"""
    result = ps(code)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()


@pytest.mark.parametrize("chunks", [
    [LINUX_BANNER + PCI_ALLOCATION_WARNING + NETWORK_READY + SSH_READY + PRODUCT_READY],
    [LINUX_BANNER, PCI_ALLOCATION_WARNING + NETWORK_READY, SSH_READY, PRODUCT_READY],
    [LINUX_BANNER, "x" * 17000 + "\n" + PCI_ALLOCATION_WARNING + NETWORK_READY, SSH_READY, PRODUCT_READY],
])
def test_linux_boot_tolerates_pci_warning_and_tail_rotation(chunks):
    assert replay_linux_boot(chunks) == ["PASS"]


@pytest.mark.parametrize("fatal", [
    "Kernel panic - not syncing: Attempted to kill init!",
    "Oops: Unaligned Access",
    "BUG: scheduling while atomic",
    "VFS: Unable to mount root fs on unknown-block(31,3)",
    "MuC: unhandled exception",
    "MuC has halted",
    "EV_ProtV exception",
])
def test_linux_fatal_beats_readiness_markers(fatal):
    result = replay_linux_boot([LINUX_BANNER + fatal + "\n" + NETWORK_READY + SSH_READY + PRODUCT_READY])
    assert result[-1].startswith("REFUSED: Linux boot failure"), result


def test_bootselect_error_before_linux_banner_remains_fatal():
    result = replay_linux_boot(["ERROR: bad image\n" + LINUX_BANNER + NETWORK_READY + SSH_READY + PRODUCT_READY])
    assert result[-1].startswith("REFUSED: Bootbase failure"), result


@pytest.mark.parametrize("missing,stage", [
    (LINUX_BANNER, "Linux 5.10"),
    (NETWORK_READY, "network ready"),
    (SSH_READY, "ssh ready"),
    (PRODUCT_READY, "product ready"),
])
def test_linux_boot_requires_each_readiness_marker(missing, stage):
    transcript = LINUX_BANNER + NETWORK_READY + SSH_READY + PRODUCT_READY
    result = replay_linux_boot([transcript.replace(missing, "")])
    assert result[-1] == "REFUSED: UART timeout during flash boot " + stage, result


def test_optional_product_readiness_does_not_swallow_linux_fatal():
    result = replay_linux_boot([LINUX_BANNER, NETWORK_READY, SSH_READY, "Kernel panic - not syncing\n"], require_product=False)
    assert result[-1].startswith("REFUSED: Linux boot failure"), result
    assert not any("OPTIONAL_TIMEOUT" in line for line in result)


def test_optional_product_timeout_still_requires_network_and_ssh():
    result = replay_linux_boot([LINUX_BANNER + NETWORK_READY + SSH_READY], require_product=False)
    assert result[-1] == "PASS"
    assert len(result) == 2 and "OPTIONAL_TIMEOUT=1 ssh_ready=1 network_ready=1" in result[0]


def test_dry_run_does_not_open_hardware():
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(ROOT / "tools/promote_f321_mtd4_direct.ps1")],
                            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["mode"] == "dry-run"
    assert report["hardware_actions_performed"] is False
    assert report["physical_ready"] is False
    assert report["executor_review_verified"] is False
    assert report["write_target"] == "mtd4/linux_live"
    assert report["transport"] == "uart-ymodem"


def test_wrong_ack_stops_before_hardware():
    result = ps(f". {quote(COMMON)}; $p=[pscustomobject]@{{required_ack='EXPECTED'}}; try {{ Assert-F321ExecutionRequest -Plan $p -Ack 'WRONG'; 'BAD' }} catch {{ 'REFUSED' }}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REFUSED"


def mock_cycle(tmp_path: Path, failing: str) -> list[str]:
    code = f". {quote(COMMON)}\n" + r'''
$script:trace = [Collections.Generic.List[string]]::new()
function Record([string]$value) { [void]$script:trace.Add($value) }
function Get-F319VerifiedRecoveryRehearsal { Record 'rehearsal' }
function Enter-F319HardwareGuard { Record 'lease'; return [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=1;LeaseToken='fake';PhysicalLockDir='fake'} }
function Exit-F319HardwareGuard { Record 'release' }
function Assert-F319HardwareLease { Record 'lease-check' }
function Assert-F319UartBinding { param($ExpectedVersion) Record ('binding-'+$ExpectedVersion); return [pscustomobject]@{NonceObserved=$true} }
function Assert-F319BorrowedRecoveryGuard { Record 'borrowed-live-lease' }
function Invoke-F321Native { throw 'TEST BLOCKED AN UNMOCKED NATIVE CALL' }
function Invoke-F321Reboot { Record 'reboot' }
function Invoke-F321Writer { param($Plan) Record ('writer-'+$Plan.direction); if($script:fail -eq 'writer' -and $Plan.direction -eq 'promote'){ throw 'writer outcome ambiguous' }; return [pscustomobject]@{status='PASS_VERIFIED_WRITER'} }
function Invoke-F321PlatformGate { param($Plan) Record ('platform-'+$Plan.direction) }
function Invoke-F321UiGate { Record 'ui'; if($script:fail -eq 'containment'){$script:F321ContainmentFailed=$true;throw 'descendant termination unproven'}; if($script:fail -eq 'ui'){throw 'UI hash mismatch'} }
$script:promote=[pscustomobject]@{direction='promote';required_ack='PROMOTE';executor_review_verified=$true;local_preflight_pass=$true;write_target='mtd4/linux_live';transport='uart-ymodem';erase_bytes=0x5e0000;uart_pnp_device_id='PNP';recovery_rehearsal='fake';physical_lock='fake';image=[pscustomobject]@{sha256='new';version='f321';directory='fake';known_hosts='known'};current=[pscustomobject]@{version='f314';directory='fake';known_hosts='known'} }
$script:rollback=[pscustomobject]@{direction='rollback';required_ack='ROLLBACK';executor_review_verified=$true;local_preflight_pass=$true;write_target='mtd4/linux_live';transport='uart-ymodem';erase_bytes=0x5e0000;uart_pnp_device_id='PNP';recovery_rehearsal='fake';physical_lock='fake';image=[pscustomobject]@{sha256='old';version='f314';directory='fake';known_hosts='known'};current=[pscustomobject]@{version='f321';directory='fake';known_hosts='known'} }
function Get-F321Plan { return $script:rollback }
'''
    code += f"$script:fail='{failing}'; try {{ [void](Invoke-F321PhysicalCycle -Plan $script:promote -RunDir {quote(tmp_path)}) }} catch {{ Record 'caught' }}; ConvertTo-Json -InputObject @($script:trace) -Compress"
    result = ps(code)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_ambiguous_writer_never_rolls_back(tmp_path):
    trace = mock_cycle(tmp_path, "writer")
    assert trace == ["rehearsal", "lease", "binding-f314", "lease-check", "reboot", "writer-promote", "release", "caught"]


def test_postgate_failure_restores_exact_f314(tmp_path):
    trace = mock_cycle(tmp_path, "ui")
    assert trace.index("binding-f314") < trace.index("reboot") < trace.index("writer-promote")
    assert trace.index("writer-promote") < trace.index("ui") < trace.index("borrowed-live-lease") < trace.index("writer-rollback")
    assert trace[-4:] == ["platform-rollback", "binding-f314", "release", "caught"]
    assert trace.count("lease") == 1 and trace.count("release") == 1


def test_success_verifies_ui_without_spi_or_radio_mutation(tmp_path):
    trace = mock_cycle(tmp_path, "")
    assert trace == ["rehearsal", "lease", "binding-f314", "lease-check", "reboot", "writer-promote", "platform-promote", "binding-f321", "ui", "release"]


def test_postgate_containment_failure_retains_lease_and_never_rolls_back(tmp_path):
    trace = mock_cycle(tmp_path, "containment")
    assert trace == ["rehearsal", "lease", "binding-f314", "lease-check", "reboot", "writer-promote", "platform-promote", "binding-f321", "ui", "caught"]
    assert "release" not in trace and "writer-rollback" not in trace


def writer_evidence(tmp_path: Path, count=None, marker=True):
    image, current = contract.F321, contract.F314
    backend = "\n".join(("MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=old current_live_crc=" + current["full_slot_crc32"],
        "PROTECTED_PARTITION_CRC_PASS=1", "MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=" + image["full_slot_crc32"] + " prefix=identical",
        "MTD4_FLASH_AND_READBACK_PASS=1 candidate=" + image["sha256"], "candidate_transport=uart-ymodem",
        "OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e")) if marker else ""
    data = {"bootbase-flash-uart.log": f"Total of {image['bytes'] if count is None else count} bytes were the same\n",
            "backend.log": backend, "uart-ymodem.log": "mock", "uart-ymodem-status.json": "{}", "uart-ymodem-console.log": "mock"}
    for name, value in data.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    report = {"status": "PASS", "candidate_sha256": image["sha256"],
              "physical_write": {"offset": 0x7E0000, "erase_size": contract.ERASE_BYTES, "candidate_size": image["bytes"], "slot_size": contract.SLOT_BYTES, "partition": "mtd4/linux_live"},
              "readback": {"full_slot_crc32": image["full_slot_crc32"], "candidate_prefix_compare": "PASS"},
              "protected_partitions": {"status": "PASS"},
              "evidence": [{"path": str(tmp_path / name), "sha256": contract.digest(tmp_path / name)} for name in data]}
    (tmp_path / "result.json").write_text(json.dumps(report), encoding="utf-8")


@pytest.mark.parametrize("count,marker", [(0, True), (5337087, True), (None, False)])
def test_writer_fake_pass_is_rejected(tmp_path, count, marker):
    writer_evidence(tmp_path, count, marker)
    with pytest.raises(ValueError):
        contract.verify_writer_result(tmp_path, contract.F321, contract.F314)


def test_writer_sha_is_expected_not_claimed_observed(tmp_path):
    writer_evidence(tmp_path)
    result = contract.verify_writer_result(tmp_path, contract.F321, contract.F314)
    assert result["full_slot_sha256_observed"] is None
    assert result["full_slot_crc32_observed"] == "6ed8e483"


def test_ui_hash_or_bundle_drift_fails():
    files = {"/www/a.js": "a" * 64}
    bundle = {"build_id": "exact"}
    api = {"schema": "lyoko.api.frontend/v1", "asset_layout": "split-v1", "bundle": bundle}
    text = "OMF321_FILES_BEGIN\n" + "a" * 64 + "  /www/a.js\nOMF321_FILES_END\nOMF321_FRONTEND_BEGIN\n" + json.dumps(api) + "\nOMF321_FRONTEND_END\n"
    assert ui.verify_ssh(text, files, bundle)["installed_hashes"]
    with pytest.raises(ValueError):
        ui.verify_ssh(text.replace("a" * 64, "b" * 64), files, bundle)
    with pytest.raises(ValueError):
        ui.verify_ssh(text, files, {"build_id": "different"})


def test_public_dashboard_or_api_bypass_fails():
    bundle = {"assets": []}
    def fetch(path):
        return (302, b"", {"Location": "/index.cgi"}) if path == "/dashboard.cgi" else (404 if path == "/dashboard.html" else 401, b"", {})
    assert all(ui.verify_http(bundle, fetch).values())
    with pytest.raises(ValueError):
        ui.verify_http(bundle, lambda _: (200, b"protected bytes leaked", {}))


@pytest.mark.parametrize("content_type,allowed", [
    ("text/javascript", True),
    ("application/javascript", True),
    ("application/x-javascript", True),
    ("Application/X-JavaScript; charset=utf-8", True),
    ("text/plain", False),
    ("text/html", False),
    ("application/json", False),
    ("", False),
])
def test_javascript_mime_allowlist_keeps_http_boundaries(content_type, allowed):
    data = b"window.offlineFixture = true;\n"
    asset = {"url": "/assets/exact.js", "bytes": len(data), "sha256": ui.hashlib.sha256(data).hexdigest()}

    def fetch(path):
        if path == asset["url"]:
            return 200, data, {"Content-Type": content_type}
        if path == "/dashboard.cgi":
            return 302, b"", {"Location": "/index.cgi"}
        return (404 if path == "/dashboard.html" else 401), b"", {}

    if allowed:
        assert all(ui.verify_http({"assets": [asset]}, fetch).values())
    else:
        with pytest.raises(ValueError, match="exact.js:mime"):
            ui.verify_http({"assets": [asset]}, fetch)


def test_legacy_javascript_mime_never_accepts_changed_bytes():
    expected = b"expected"
    asset = {"url": "/assets/exact.js", "bytes": len(expected), "sha256": ui.hashlib.sha256(expected).hexdigest()}

    def fetch(path):
        if path == asset["url"]:
            return 200, b"tampered", {"Content-Type": "application/x-javascript"}
        if path == "/dashboard.cgi":
            return 302, b"", {"Location": "/index.cgi"}
        return (404 if path == "/dashboard.html" else 401), b"", {}

    with pytest.raises(ValueError, match="/assets/exact.js"):
        ui.verify_http({"assets": [asset]}, fetch)


def test_ui_hash_allowlist_rejects_shell_syntax():
    with pytest.raises(ValueError):
        ui.ssh_script({"/www/a;reboot": "a" * 64})


def test_ssh_stdin_uses_lf_bytes_and_structured_argv():
    calls = []
    def fake(argv, **options):
        calls.append((argv, options))
        return subprocess.CompletedProcess(argv, 0, b"ok\n", b"")
    ui.run_ssh(["ssh", "root@192.168.1.90", "sh", "-s"], "set -eu\r\necho ok\r\n", fake)
    argv, options = calls[0]
    assert argv[-2:] == ["sh", "-s"]
    assert options["input"] == b"set -eu\necho ok\n"
    assert "text" not in options


def test_windows_powershell_guard_writes_no_bom_and_preserves_posix_quotes(tmp_path):
    receiver = tmp_path / "read stdin bytes.py"
    receiver.write_text("import json,sys\nprint(json.dumps(list(sys.stdin.buffer.read())))\n", encoding="ascii")
    code = f". {quote(COMMON)}; $r=Invoke-F319SshScript -SshPath {quote(Path(sys.executable))} -Arguments @({quote(receiver)}) -Script \"grep 'exact value' /tmp/file`r`necho done\"; $r | ConvertTo-Json -Compress"
    result = ps(code)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["ExitCode"] == 0, observed
    assert bytes(json.loads(observed["Stdout"])) == b"grep 'exact value' /tmp/file\necho done\n"


def test_timeout_contains_and_terminates_native_descendants(tmp_path):
    child = tmp_path / "child.py"
    pidfile = tmp_path / "child.pid"
    child.write_text("import subprocess,sys,time\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])\nopen(sys.argv[1],'w').write(str(p.pid))\ntime.sleep(90)\n", encoding="ascii")
    code = f". {quote(COMMON)}; try {{ [void](Invoke-F321Native -Program 'python' -Arguments @({quote(child)},{quote(pidfile)}) -TimeoutSeconds 3); 'BAD' }} catch {{ 'REFUSED' }}; if(Test-Path -LiteralPath {quote(pidfile)}) {{ $childPid=[int](Get-Content -LiteralPath {quote(pidfile)}); if(Get-Process -Id $childPid -ErrorAction SilentlyContinue){{'CHILD_ALIVE'}}else{{'CHILD_DEAD'}} }}else{{'NO_CHILD_STARTED'}}"
    result = ps(code)
    assert result.returncode == 0, result.stderr
    assert "REFUSED" in result.stdout and "CHILD_DEAD" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("exits", [False, True])
def test_empty_job_does_not_hide_a_live_unjoined_launcher(exits):
    value = "$true" if exits else "$false"
    code = f". {quote(COMMON)}; " + "$p=[pscustomobject]@{HasExited=$false}; $j=[pscustomobject]@{ActiveProcesses=0}; "
    code += "$p | Add-Member ScriptMethod Kill {}; "
    code += f"$p | Add-Member ScriptMethod WaitForExit {{ return {value} }}; "
    code += "try { Complete-F321NativeContainment -Process $p -Job $j -Started $true; 'PASS' } catch { 'REFUSED' }; [string]$script:F321ContainmentFailed"
    result = ps(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == (["PASS", "False"] if exits else ["REFUSED", "True"])


def test_sealed_flags_require_separate_exact_review(tmp_path):
    report = {"schema": "openmitrastar.f321-executor-review/v1", "candidate_sha256": contract.F321["sha256"], "physical_authorization": True}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(report), encoding="ascii")
    with pytest.raises(ValueError):
        contract.validate_executor_review(path, contract.digest(path))


def test_native_environment_is_pinned_to_f321_backend():
    env = contract.environment(contract.F321, contract.F314)
    assert env["OM_Q3_FLASH_POWERSHELL_BACKEND"].endswith("f321_mtd4_bootbase_flash.ps1")
    assert env["OM_Q3_FLASH_ACK"] == "OPENMITRASTAR_F321_MTD4_EB8E23AC"
    assert contract.environment(contract.F314, contract.F321)["OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32"] == "6ed8e483"


class FakeUartClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeUartSerial:
    def __init__(self, clock, queue=0, returned=None, write_seconds=0):
        self.clock, self.queue = clock, queue
        self.returned, self.write_seconds = returned, write_seconds
        self.write_timeout = 5
        self.writes = []
        self.cancelled = self.cleared = False

    def write(self, payload):
        self.writes.append(payload)
        self.clock.sleep(self.write_seconds)
        return len(payload) if self.returned is None else self.returned

    @property
    def out_waiting(self):
        return self.queue

    def flush(self):
        raise AssertionError("unbounded vendored flush must never be called")

    def cancel_write(self):
        self.cancelled = True

    def reset_output_buffer(self):
        self.cleared = True


def test_uart_tx_queue_timeout_is_bounded(monkeypatch):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    session = uart.UartSession.__new__(uart.UartSession)
    session.serial = FakeUartSerial(clock, queue=2)
    with pytest.raises(TimeoutError, match="queue"):
        session.write(b"\x15\r", timeout=0.05)
    assert clock.now == pytest.approx(0.05)
    assert session.serial.writes == [b"\x15\r"]
    assert session.serial.cancelled and session.serial.cleared
    assert session.serial.write_timeout == 5


@pytest.mark.parametrize("returned,write_seconds", [(1, 0), (None, 0.2)])
def test_uart_partial_or_expired_write_never_retries(monkeypatch, returned, write_seconds):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    session = uart.UartSession.__new__(uart.UartSession)
    session.serial = FakeUartSerial(clock, returned=returned, write_seconds=write_seconds)
    with pytest.raises(TimeoutError):
        session.write(b"ab", timeout=0.1)
    assert session.serial.writes == [b"ab"]
    assert session.serial.cancelled and session.serial.cleared


def test_uart_drained_write_returns_without_unbounded_flush(monkeypatch):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    session = uart.UartSession.__new__(uart.UartSession)
    session.serial = FakeUartSerial(clock)
    assert session.write(b"ab") == 2
    assert not session.serial.cancelled


class FakePromptSession:
    def __init__(self, clock, prompt_after=None, first_write_seconds=0):
        self.clock, self.prompt_after = clock, prompt_after
        self.first_write_seconds = first_write_seconds
        self.tail = bytearray()
        self.writes = []
        self.serial = SimpleNamespace(reset_input_buffer=lambda: None)

    def write(self, payload, timeout=5):
        self.writes.append((payload, timeout))
        if len(self.writes) == 1:
            self.clock.sleep(self.first_write_seconds)
        return len(payload)

    def read(self, timeout):
        self.clock.sleep(timeout)
        if self.prompt_after is not None and len(self.writes) >= self.prompt_after:
            self.tail.extend(b"\r\ntopaz> ")


def test_uart_prompt_retry_stops_at_prompt(monkeypatch):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    session = FakePromptSession(clock, prompt_after=2)
    uart.acquire_topaz(session, False, 3)
    assert [payload for payload, _ in session.writes] == [b"\x15\r", b"\r"]
    assert clock.now < 3


def test_uart_prompt_deadline_includes_first_tx(monkeypatch):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    session = FakePromptSession(clock, first_write_seconds=0.75)
    with pytest.raises(TimeoutError, match="RAM load not started"):
        uart.acquire_topaz(session, False, 2)
    assert session.writes[0][1] == 2
    assert clock.now == pytest.approx(2)
    assert all(payload in (b"\x15\r", b"\r") for payload, _ in session.writes)


def test_uart_missing_prompt_never_starts_loady_or_modem(monkeypatch, tmp_path):
    clock = FakeUartClock()
    monkeypatch.setattr(uart, "time", clock)
    commands = []

    class Session(FakePromptSession):
        def __init__(self, *_):
            super().__init__(clock)

        def line(self, command):
            commands.append(command)
            raise AssertionError("no RAM command without prompt")

        def close(self):
            commands.append("closed")

    class Modem:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("no YMODEM without prompt")

    monkeypatch.setattr(uart, "UartSession", Session)
    monkeypatch.setattr(uart.original, "ModemSocket", Modem)
    candidate = tmp_path / "candidate.bin"
    candidate.write_bytes(b"offline fixture")
    status = tmp_path / "status.json"
    monkeypatch.setattr(sys, "argv", ["loader", "--attach-topaz", "--prompt-timeout", "1", "--file", str(candidate),
        "--expected-size", str(candidate.stat().st_size), "--expected-sha256", contract.digest(candidate),
        "--expected-crc32", f"{contract.zlib.crc32(candidate.read_bytes()) & 0xffffffff:08x}",
        "--log", str(tmp_path / "uart.log"), "--status", str(status)])
    with pytest.raises(TimeoutError):
        uart.main()
    assert commands == ["closed"]
    assert not status.exists()
    progress = [json.loads(line) for line in (tmp_path / "uart-ymodem-progress.jsonl").read_text().splitlines()]
    assert [row["phase"] for row in progress] == ["starting", "failed"]


def test_uart_progress_records_real_callback(tmp_path):
    path = tmp_path / "progress.jsonl"
    reporter = uart.ProgressReporter(path, 2048)
    received = []
    callback = reporter.callback(lambda *args: received.append(args))
    callback(0, "private-name-not-logged.bin", 2048, 1024)
    first = json.loads(path.read_text())
    callback(0, "private-name-not-logged.bin", 2048, 2048)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert first == records[0]
    assert [record["acked_bytes"] for record in records] == [1024, 2048]
    assert all(record["phase"] == "transfer" and record["flash_writes"] == 0 for record in records)
    assert records[0]["monotonic_seconds"] <= records[1]["monotonic_seconds"]
    assert "private-name" not in path.read_text()
    assert len(received) == 2


def test_uart_modem_propagates_tx_timeout_without_retry(tmp_path):
    candidate = tmp_path / "offline.bin"
    candidate.write_bytes(b"fixture")
    writes = []

    def timeout_write(payload, timeout):
        writes.append(payload)
        raise TimeoutError("mock UART TX queue deadline")

    modem = uart.F321ModemSocket(lambda *_: b"C", timeout_write)
    with pytest.raises(TimeoutError, match="TX queue"):
        modem.send([str(candidate)])
    assert len(writes) == 1


def test_f321_writer_uses_isolated_loader_and_restores_import(monkeypatch):
    previous = writer.original.UART_LOADER
    monkeypatch.setattr(sys, "argv", ["writer", "--execute", "--skip-reboot", "--uart-attach-topaz"])
    observed = []
    monkeypatch.setattr(writer.original, "main", lambda: observed.append(writer.original.UART_LOADER) or 0)
    assert writer.main() == 0
    assert observed == [writer.UART_LOADER]
    assert writer.original.UART_LOADER == previous
    assert contract.WRITER.name == "f321_mtd4_one_shot.py"
    assert all(f"tools/{name}" in contract.EXECUTOR_FILES for name in ("f321_mtd4_one_shot.py", "f321_uart_ymodem_load.py"))


@pytest.mark.parametrize("arguments", [
    ["--execute"], ["--execute", "--skip-reboot"], ["--execute", "--uart-attach-topaz"],
    ["--transport", "tftp"], ["--uart-receiver-ready"], ["--exec"],
])
def test_f321_wrapper_rejects_other_entry_paths_before_runner(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["writer", *arguments])
    monkeypatch.setattr(writer.original, "main", lambda: pytest.fail("original runner must not be called"))
    with pytest.raises(SystemExit):
        writer.main()
