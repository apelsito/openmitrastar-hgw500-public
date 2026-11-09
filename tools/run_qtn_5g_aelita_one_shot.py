#!/usr/bin/env python3
"""Coordinate the RAM-only 5 GHz gate with AELITA Windows oracle.

Dry-run is the default.  Execution starts the already-embedded Quantenna lane,
arms target-local rollback, starts a bounded controller speed server, launches
the hardened SYSTEM oracle task on AELITA, records router telemetry, evaluates
both evidence sources and leaves the independent Windows restore watchdog armed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))
sys.path.insert(0, str(ROOT / "tools"))

import paramiko  # noqa: E402


ACK = "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY"
STABLE_ACK = "OPENMITRASTAR_2G_STABLE_FOR_QTN5G"
ORACLE_HOST = "192.168.1.63"
ORACLE_USER = "AELITA"
ORACLE_KEY = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/oracle_rsa_unencrypted"
KNOWN_HOSTS = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
WINDOWS_RUNNER = ROOT / "tools/run_qtn_5g_windows_oracle.ps1"
WINDOWS_STARTER = ROOT / "tools/start_qtn_5g_windows_oracle_task.ps1"
WINDOWS_WATCHDOG = ROOT / "tools/restore_wifi_oracle_watchdog.ps1"
SPEED_SERVER = ROOT / "tools/openmitrastar_l2_speed_server.py"
ROUTER_MONITOR = ROOT / "tools/q3_client_stream_single_session.py"
HARDWARE_STATE = ROOT / "work/mission-state/HARDWARE_STATE.json"
MASTER_AUDIT = ROOT / "outputs/kernel-port/quantenna-5g-master-offline-20260823/audit.json"
TRACE_DIR = ROOT / "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823"
TRACE_MANIFEST = TRACE_DIR / "manifest.json"
TRACE_MANIFEST_SHA = "cb26ddc8533cecc4387b5fe132e5e912f2d67cc259758fd2ba30feda0b6ea8b7"
TRACE_QDRV = TRACE_DIR / "qdrv-tqe-rxalign-whcopy-txpath.ko"
TRACE_QDRV_SHA = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"
TRACE_START = TRACE_DIR / "om-radio5-start-tqe-rxalign-whcopy-txpath"
TRACE_START_SHA = "acf4ecc87cf05afe07f5e4b1e19af1a47adc857e18e797b9497bc5d951063031"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qtn_runner = load_module("qtn_tx7_gate", ROOT / "tools/run_qtn_w3_tx7_client_traffic.py")
evaluator = load_module("qtn_isolated_eval", ROOT / "tools/evaluate_qtn_5g_isolated_l3.py")
v62_contract = load_module("qtn_v62_scheduler_contract", ROOT / "tools/qtn_5g_v62_scheduler_contract.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure_tx_path_trace() -> None:
    if sha256(TRACE_MANIFEST) != TRACE_MANIFEST_SHA:
        raise SystemExit("TX path trace manifest does not match")
    manifest = json.loads(TRACE_MANIFEST.read_text(encoding="utf-8"))
    if (
        sha256(TRACE_QDRV) != TRACE_QDRV_SHA
        or sha256(TRACE_START) != TRACE_START_SHA
        or manifest["artifacts"]["qdrv"]["sha256"] != TRACE_QDRV_SHA
        or manifest["artifacts"]["start"]["sha256"] != TRACE_START_SHA
        or manifest["artifacts"]["stop"]["sha256"] != qtn_runner.SAFE_STOP[1]
    ):
        raise SystemExit("TX path trace artifacts do not match")
    qtn_runner.QDRV_SHA256 = TRACE_QDRV_SHA
    qtn_runner.SAFE_MODULES["qdrv.ko"] = (TRACE_QDRV, TRACE_QDRV_SHA)
    qtn_runner.SAFE_START = (TRACE_START, TRACE_START_SHA)


def configure_v6_scheduler_diag() -> dict[str, object]:
    return v62_contract.apply_to_runner(qtn_runner)


def verify_local() -> dict:
    required = (
        WINDOWS_RUNNER,
        WINDOWS_STARTER,
        WINDOWS_WATCHDOG,
        SPEED_SERVER,
        ROUTER_MONITOR,
        ORACLE_KEY,
        KNOWN_HOSTS,
        HARDWARE_STATE,
        MASTER_AUDIT,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing local inputs: " + ", ".join(missing))

    key = paramiko.RSAKey.from_private_key_file(str(ORACLE_KEY))
    hosts = paramiko.HostKeys()
    hosts.load(str(KNOWN_HOSTS))
    if ORACLE_HOST not in hosts:
        raise SystemExit("oracle host key is not pinned")

    state = json.loads(HARDWARE_STATE.read_text(encoding="utf-8"))
    audit = json.loads(MASTER_AUDIT.read_text(encoding="utf-8"))
    qtn_runner.verify_safe_modules()
    radio2 = state.get("radio_2_4_ghz", {})
    if state.get("current_observation", {}).get("kernel_release") != qtn_runner.RELEASE:
        raise SystemExit("hardware-state kernel release mismatch")
    radio2_state = radio2.get("state", "")
    stable_2g_from_hardware_state = "LOCAL_BIDIRECTIONAL_TRAFFIC_PASS" in radio2_state
    if audit.get("reentry_gate", {}).get("offline_contract_pass") is not True:
        raise SystemExit("Quantenna master offline audit is not PASS")
    return {
        "oracle_key_type": key.get_name(),
        "oracle_host_key_pinned": True,
        "hardware_state_updated_at": state.get("updated_at"),
        "hardware_boot_id": state.get("current_observation", {}).get("boot_id"),
        "radio2_state": radio2_state,
        "stable_2g_from_hardware_state": stable_2g_from_hardware_state,
        "stable_2g_current_gate": (
            "require run_qtn_5g_after_f38_ready.ps1 READY_2G_PASS before execute"
            if not stable_2g_from_hardware_state else "hardware-state-local-bidirectional-traffic-pass"
        ),
        "radio2_performance": radio2.get("performance_current_checkpoint"),
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
            for path in (
                WINDOWS_RUNNER, WINDOWS_STARTER, WINDOWS_WATCHDOG,
                SPEED_SERVER, ROUTER_MONITOR,
                *(item[0] for item in qtn_runner.SAFE_MODULES.values()),
                qtn_runner.SAFE_START[0], qtn_runner.SAFE_STOP[0],
                qtn_runner.SAFE_LOADER[0],
            )
        },
    }


def oracle_connect(host: str, user: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(ORACLE_KEY))
    client.connect(
        host,
        username=user,
        pkey=key,
        look_for_keys=False,
        allow_agent=False,
        timeout=8,
        banner_timeout=10,
        auth_timeout=10,
    )
    return client


def powershell_encoded(command: str) -> str:
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    return (
        "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encoded}"
    )


def oracle_ps(host: str, user: str, command: str, timeout: int = 60) -> str:
    client = oracle_connect(host, user)
    try:
        _, stdout, stderr = client.exec_command(powershell_encoded(command), timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc:
            raise RuntimeError(f"oracle PowerShell rc={rc}: {err[:500]}")
        return out
    finally:
        client.close()


def cleanup_restore_tasks(host: str, user: str, *, include_qtn: bool = True) -> dict:
    names = [
        "OpenMitraStar-2G-WPA2-Restore",
        "OpenMitraStar-QTN5G-AssocOnly-Restore",
        "OpenMitraStar-WiFiOracle-Restore",
    ]
    if include_qtn:
        names.append("OpenMitraStar-QTN5G-Restore")
    quoted = ",".join("'" + name.replace("'", "''") + "'" for name in names)
    command = rf'''
$ProgressPreference = 'SilentlyContinue'
$removed = @()
foreach ($name in @({quoted})) {{
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {{
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
        $removed += $name
    }}
}}
[ordered]@{{ removed = @($removed); remaining = @(
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object {{ $_.TaskName -like 'OpenMitraStar*Restore*' }} |
        Select-Object -ExpandProperty TaskName
) }} | ConvertTo-Json -Depth 4 -Compress
'''
    raw = oracle_ps(host, user, command, 60)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


def stage_oracle(host: str, user: str) -> dict[str, str]:
    client = oracle_connect(host, user)
    remote_dir = ".openmitrastar-qtn5g"
    files = (WINDOWS_RUNNER, WINDOWS_STARTER, WINDOWS_WATCHDOG)
    try:
        sftp = client.open_sftp()
        try:
            try:
                sftp.mkdir(remote_dir)
            except OSError:
                pass
            for source in files:
                sftp.put(str(source), f"{remote_dir}/{source.name}")
        finally:
            sftp.close()
    finally:
        client.close()

    expected = {path.name: sha256(path) for path in files}
    expected_json = json.dumps(expected, separators=(",", ":"))
    command = rf'''
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:USERPROFILE '.openmitrastar-qtn5g'
$expected = ConvertFrom-Json @'
{expected_json}
'@
$actual = [ordered]@{{}}
foreach ($name in $expected.PSObject.Properties.Name) {{
  $path = Join-Path $dir $name
  $item = Get-Item -LiteralPath $path -ErrorAction Stop
  if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {{ throw "unsafe staged file: $name" }}
  $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($hash -ne $expected.$name) {{ throw "hash mismatch: $name" }}
  $actual[$name] = $hash
}}
[ordered]@{{schema='openmitrastar.qtn-5g-aelita-stage/v1';user=$env:USERNAME;files=$actual}} | ConvertTo-Json -Depth 5
'''
    oracle_ps(host, user, command, 60)
    return expected


def start_oracle_task(host: str, user: str, *, seconds: int,
                      restore_ssid: str, expected_bssid: str,
                      test_ssid: str = "OpenMitraStar-5G-DIAG",
                      isolated_l3: bool = True,
                      mtu_probe: bool = False, skip_throughput: bool = False,
                      upload_mib: int = 32, transfer_timeout_seconds: int = 180,
                      ping_stress_count: int = 0,
                      ping_stress_payload_bytes: int = 1400) -> str:
    bssid_arg = (
        f" -ExpectedBssid '{expected_bssid.replace("'", "''")}'"
        if expected_bssid else ""
    )
    topology_arg = " -IsolatedL3" if isolated_l3 else ""
    mtu_arg = " -MtuProbe" if mtu_probe else ""
    throughput_arg = " -SkipThroughput" if skip_throughput else ""
    stress_arg = (
        f" -PingStressCount {ping_stress_count} "
        f"-PingStressPayloadBytes {ping_stress_payload_bytes}"
        if ping_stress_count else ""
    )
    command = rf'''
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:USERPROFILE '.openmitrastar-qtn5g'
& (Join-Path $dir 'start_qtn_5g_windows_oracle_task.ps1') `
  -Execute -Ack OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_TASK_RAM_ONLY `
  -SourceScript (Join-Path $dir 'run_qtn_5g_windows_oracle.ps1') `
  -WatchdogSourceScript (Join-Path $dir 'restore_wifi_oracle_watchdog.ps1') `
  -TestSsid '{test_ssid.replace("'", "''")}' -RestoreSsid '{restore_ssid.replace("'", "''")}' `
  -WifiInterface 'Wi-Fi' -RouterIp '192.168.1.90' -ControllerIp '192.168.1.43' `
  -ControllerPort 8081 -UploadMiB {upload_mib} -TransferTimeoutSeconds {transfer_timeout_seconds} `
  -SoakSeconds {seconds}{bssid_arg}{topology_arg}{mtu_arg}{throughput_arg}{stress_arg} `
  -RestoreWatchdogMinutes 8
'''
    return oracle_ps(host, user, command, 90)


def wait_oracle_result(host: str, user: str, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    command = r'''
$path = 'C:\ProgramData\OpenMitraStar\oracle\qtn-5g-result.json'
if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Raw } else { exit 44 }
'''
    last_error = "result-not-seen"
    while time.monotonic() < deadline:
        try:
            raw = oracle_ps(host, user, command, 30)
            return json.loads(raw.lstrip("\ufeff"))
        except Exception as exc:  # network is expected to move during the test
            last_error = str(exc)
            time.sleep(5)
    raise RuntimeError(f"oracle result timeout: {last_error[:300]}")


def start_server(bind: str, port: int, mib: int = 32) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [sys.executable, str(SPEED_SERVER), "--bind", bind, "--port", str(port),
         "--mib", str(mib), "--max-upload-mib", str(max(64, mib * 2))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout
    ready = process.stdout.readline().strip()
    if "OML2_HTTP_READY" not in ready:
        process.terminate()
        raise RuntimeError(f"speed server did not start: {ready}")
    return process


def stop_server(process: subprocess.Popen[str] | None) -> None:
    if not process:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def prepare_remote_radio5_runtime(host: str) -> str:
    command = r'''set -eu
if [ -x /usr/sbin/om-qtn-mac-prepare ]; then
  /usr/sbin/om-qtn-mac-prepare
fi
if [ -x /usr/sbin/om-qtn-cal-readonly ]; then
  /usr/sbin/om-qtn-cal-readonly
fi
test -r /run/openmitrastar/calibration/ready
test -r /run/openmitrastar/secrets/qtn-mac0addr
grep -qx 'flash_writes=0' /run/openmitrastar/calibration/ready
echo OMQTN5G_RUNTIME_PREP_PASS flash=0
'''
    result = qtn_runner.ssh(host, command, 60)
    if "OMQTN5G_RUNTIME_PREP_PASS" not in result.stdout:
        raise RuntimeError("5 GHz runtime prep marker missing")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--tx-path-trace", action="store_true")
    parser.add_argument("--v6-scheduler-diag", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--stable-2g-ack")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--oracle-host", default=ORACLE_HOST)
    parser.add_argument("--oracle-user", default=ORACLE_USER)
    parser.add_argument("--controller-ip", default="192.168.1.43")
    parser.add_argument("--restore-ssid", default="MOVISTAR-WIFI6-A348")
    parser.add_argument("--expected-bssid", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "outputs/f3-certification/qtn-5g-aelita")
    args = parser.parse_args()
    if args.oracle_host != ORACLE_HOST or args.oracle_user != ORACLE_USER:
        raise SystemExit("this gate is pinned to AELITA@192.168.1.63")
    if not 60 <= args.seconds <= 900:
        raise SystemExit("--seconds must be 60..900")
    if args.run_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", args.run_id):
        raise SystemExit("--run-id contains unsafe characters")

    if args.tx_path_trace and args.v6_scheduler_diag:
        raise SystemExit("--tx-path-trace and --v6-scheduler-diag are mutually exclusive")

    v6_contract_manifest = None
    if args.v6_scheduler_diag:
        v6_contract_manifest = configure_v6_scheduler_diag()
    elif args.tx_path_trace:
        configure_tx_path_trace()
    local = verify_local()
    trace_flag = "--v6-scheduler-diag" if args.v6_scheduler_diag else "--tx-path-trace"
    command = (
        "python tools/run_qtn_5g_aelita_one_shot.py --execute "
        f"--ack {ACK} --stable-2g-ack {STABLE_ACK} "
        "--router-host 192.168.1.90 --oracle-host 192.168.1.63 "
        "--oracle-user AELITA --controller-ip 192.168.1.43 "
        f"--restore-ssid MOVISTAR-WIFI6-A348 --seconds 120 {trace_flag}"
    )
    if not args.execute:
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-aelita-one-shot-plan/v1",
            "mode": "dry-run",
            "oracle": f"{ORACLE_USER}@{ORACLE_HOST}",
            "router": args.router_host,
            "controller": args.controller_ip,
            "runtime_snapshot": local,
            "runtime_compatibility": "ISOLATED_L3_READY_AFTER_ROUTER_RECOVERY",
            "topology": "wifi0=192.168.77.1/24 outside br0; AELITA=192.168.77.2/24 temporary",
            "tx_path_trace": args.tx_path_trace,
            "v6_scheduler_diag": args.v6_scheduler_diag,
            "v6_contract": v6_contract_manifest,
            "watchdog": "restore_wifi_oracle_watchdog.ps1 preflight-first under SYSTEM",
            "exact_command": command,
            "flash": False,
            "reboot": False,
            "network_changed_now": False,
        }, indent=2, sort_keys=True))
        print("OMQTN5G_AELITA_ONE_SHOT_DRY_RUN_PASS=1 execute=0 oracle=192.168.1.63 watchdog=reinforced")
        return 0
    if args.ack != ACK or args.stable_2g_ack != STABLE_ACK:
        raise SystemExit(f"require --ack {ACK} and --stable-2g-ack {STABLE_ACK}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"txpath-{stamp}"
    router_log = args.output_dir / f"router-{stamp}.log"
    windows_json = args.output_dir / f"windows-{stamp}.json"
    result_json = args.output_dir / f"evaluation-{stamp}.json"
    module_map = router_log.with_suffix(router_log.suffix + ".module-map.txt")
    monitor_seconds = min(args.seconds + 300, 900)
    server: subprocess.Popen[str] | None = None
    radio_started = False
    overlay_staged = False
    try:
        prepare_remote_radio5_runtime(args.router_host)
        qtn_runner.preflight_remote(args.router_host)
        qtn_runner.stage_safe_overlay(args.router_host)
        overlay_staged = True
        qtn_runner.prepare_radio5_gate(args.router_host, run_id)
        qtn_runner.arm_rollback(args.router_host, 240, run_id)
        module_map.write_text(qtn_runner.start_radio5(args.router_host, run_id), encoding="utf-8", newline="\n")
        radio_started = True
        qtn_runner.arm_rollback(args.router_host, monitor_seconds + 300, run_id)
        server = start_server(args.controller_ip, 8081)
        stage_oracle(args.oracle_host, args.oracle_user)
        start_oracle_task(
            args.oracle_host, args.oracle_user, seconds=args.seconds,
            restore_ssid=args.restore_ssid, expected_bssid=args.expected_bssid,
        )
        monitor = subprocess.run(
            [sys.executable, str(ROUTER_MONITOR), "--host", args.router_host,
             "--seconds", str(monitor_seconds), "--interval", "1",
             "--require-client-traffic", "--isolated-l3", "--output", str(router_log)],
            cwd=ROOT, text=True, capture_output=True,
            timeout=monitor_seconds + 90, check=False,
        )
        windows = wait_oracle_result(args.oracle_host, args.oracle_user, args.seconds + 660)
        windows_json.write_text(json.dumps(windows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        router = json.loads(router_log.with_suffix(router_log.suffix + ".json").read_text(encoding="utf-8"))
        result = evaluator.evaluate(windows, router, duration_min=args.seconds)
        trace_path = args.output_dir / f"txpath-{stamp}.log"
        trace_read = qtn_runner.ssh(
            args.router_host,
            "dmesg | grep 'OMQDRVTXPATH stage=' | tail -n 128",
            30,
            check=False,
        )
        trace_path.write_text(trace_read.stdout, encoding="utf-8", newline="\n")
        stages = [
            stage for stage in ("enqueue", "hardstart", "desc-ready", "mailbox-enter", "mailbox-published", "txdone")
            if f"OMQDRVTXPATH stage={stage}" in trace_read.stdout
        ]
        result["tx_path_trace"] = {"enabled": args.tx_path_trace, "stages": stages, "evidence": str(trace_path)}
        result["oracle"] = f"{args.oracle_user}@{args.oracle_host}"
        result["router_monitor_rc"] = monitor.returncode
        result["module_map"] = str(module_map)
        result_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if monitor.returncode or result["status"] != "PASS":
            raise RuntimeError(f"combined gate failed: {result['failures']}")
        qtn_runner.commit(args.router_host, run_id)
        print(f"OMQTN5G_AELITA_ONE_SHOT_PASS=1 result={result_json} flash=0")
        return 0
    except Exception:
        if overlay_staged:
            failure_log = args.output_dir / f"radio5-failure-{stamp}.txt"
            qtn_runner.collect_radio5_failure_snapshot(args.router_host, failure_log, run_id)
            qtn_runner.stop_radio5(args.router_host, "aelita-one-shot-failed")
        qtn_runner.cleanup_safe_overlay(args.router_host)
        raise
    finally:
        stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
