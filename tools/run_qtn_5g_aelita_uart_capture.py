#!/usr/bin/env python3
"""Wrap the RAM-only 5 GHz one-shot with an independent COM3 capture.

The UART listener starts before qdrv staging and remains alive after the
one-shot exits, so TXPATH printk evidence survives loss of 192.168.1.90.
Dry-run is the default.  This wrapper contains no flash or boot-environment
write path and does not itself reboot the target.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_5G_UART_CAPTURE_RAM_ONLY"
ONE_SHOT = ROOT / "tools/run_qtn_5g_aelita_one_shot.py"
ONE_SHOT_SHA256 = "741f7088442dd343ecfdcef05adfdd4442b3018b8aaf1813e86fbf07fa250991"
QTN_RUNNER = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"
QTN_RUNNER_SHA256 = "a2e3e7dc7973124313292a3a12048ae0e495ec3102d029d5293e3b6bc6803d81"
UART_CAPTURE = ROOT / "tools/capture_topaz_uart_resilient.ps1"
UART_CAPTURE_SHA256 = "7a9da4a416dd4583aeca1299e94768f230cf49dde41d1fa3c3b146c0b4954df2"
EVALUATOR = ROOT / "tools/evaluate_qtn_5g_uart_txpath.py"
EVALUATOR_SHA256 = "22ed32145c6f019bcf6e4b13e691eb88c06d2fa6e4c17ce4787671d9baf62dab"
EXPECTED_UART_PNP_ID = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
V6_QDRV_SHA256 = "5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


txpath_evaluator = load_module("qtn_uart_txpath_evaluator", EVALUATOR)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_local() -> None:
    for path, expected in (
        (ONE_SHOT, ONE_SHOT_SHA256),
        (QTN_RUNNER, QTN_RUNNER_SHA256),
        (UART_CAPTURE, UART_CAPTURE_SHA256),
        (EVALUATOR, EVALUATOR_SHA256),
    ):
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"pinned input mismatch: {path}")


def wait_capture_ready(process: subprocess.Popen[str], status_path: Path, stderr_path: Path,
                       seconds: int = 15) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = stderr_path.read_text(errors="replace") if stderr_path.exists() else ""
            raise RuntimeError(f"UART capture exited before ready: {detail[-500:]}")
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                status = {}
            if status.get("ready") and status.get("state") in {"ready", "capturing", "reconnected"}:
                return status
        time.sleep(0.1)
    raise RuntimeError("UART capture did not report ready")


def append_event(path: Path, run_id: str, stage: str, **fields: object) -> None:
    event = {
        "schema": "openmitrastar.qtn-5g-orchestrator-event/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "stage": stage,
        **fields,
    }
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def probe_post_recovery(host: str) -> dict[str, object]:
    command = r'''set +e
management_ok=1
recovery_clean=1
loglevel_original_present=0
loglevel_matches_original=0
hostapd2g_ok=0
radio5_stopped=1
test -e /sys/class/net/br0/brif/eth0 || management_ok=0
test -e /sys/class/net/br0/brif/wlan0 || management_ok=0
if [ -s /run/openmitrastar/radio2g/hostapd-open.pid ]; then
  pid=$(cat /run/openmitrastar/radio2g/hostapd-open.pid 2>/dev/null)
  kill -0 "$pid" 2>/dev/null && hostapd2g_ok=1
fi
[ "$hostapd2g_ok" = 1 ] || ps w 2>/dev/null | grep -F '/usr/sbin/hostapd' | grep -Fq '/run/openmitrastar/radio2g/host' && hostapd2g_ok=1
[ "$hostapd2g_ok" = 1 ] || management_ok=0
test ! -e /sys/class/net/br0/brif/wifi0 || recovery_clean=0
if ifconfig wifi0 2>/dev/null | grep -q 'UP'; then recovery_clean=0; radio5_stopped=0; fi
if ps w 2>/dev/null | grep -F 'hostapd-qtn' | grep -v grep >/dev/null; then recovery_clean=0; radio5_stopped=0; fi
if [ -r /sys/module/qdrv/parameters/openmitrastar_rf_enable ]; then
  rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null)
  [ "$rf" = 0 ] || recovery_clean=0
fi
gate=/run/openmitrastar/w3-tx7-client-gate
if [ -r "$gate/console-loglevel.original" ]; then
  loglevel_original_present=1
  original=$(cat "$gate/console-loglevel.original")
  current=$(cut -d' ' -f1 /proc/sys/kernel/printk)
  [ "$current" = "$original" ] && loglevel_matches_original=1
fi
echo OMPOSTRECOVERY management_ok=$management_ok recovery_clean=$recovery_clean radio5_stopped=$radio5_stopped hostapd2g_ok=$hostapd2g_ok loglevel_original_present=$loglevel_original_present loglevel_matches_original=$loglevel_matches_original
'''
    process = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", command, "--host", host, "--timeout", "10"],
        cwd=ROOT, text=True, capture_output=True, timeout=25, check=False,
    )
    match = re.search(
        r"OMPOSTRECOVERY management_ok=([01]) recovery_clean=([01]) "
        r"radio5_stopped=([01]) hostapd2g_ok=([01]) "
        r"loglevel_original_present=([01]) loglevel_matches_original=([01])",
        process.stdout,
    )
    return {
        "attempted": True,
        "ssh_returncode": process.returncode,
        "management_ok": bool(match and match.group(1) == "1"),
        "recovery_clean": bool(match and match.group(2) == "1"),
        "radio5_stopped": bool(match and match.group(3) == "1"),
        "hostapd2g_ok": bool(match and match.group(4) == "1"),
        "loglevel_original_present": bool(match and match.group(5) == "1"),
        "loglevel_matches_original": bool(match and match.group(6) == "1"),
        "error": None if process.returncode == 0 else (process.stderr or process.stdout)[-500:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--post-seconds", type=int, default=420)
    parser.add_argument("--capture-seconds", type=int, default=0)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/uart-live/qtn-5g-txpath-oob",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"COM[0-9]{1,3}", args.port):
        raise SystemExit("--port must be a COM port such as COM3")
    if not 60 <= args.seconds <= 900:
        raise SystemExit("--seconds must be 60..900")
    if not 30 <= args.post_seconds <= 900:
        raise SystemExit("--post-seconds must be 30..900")
    one_shot_max_seconds = args.seconds + 900
    required_capture_seconds = one_shot_max_seconds + args.post_seconds + 30
    capture_seconds = args.capture_seconds or required_capture_seconds
    if not required_capture_seconds <= capture_seconds <= 3600:
        raise SystemExit(
            f"--capture-seconds must be {required_capture_seconds}..3600 "
            "to cover one-shot maximum + post window + 30 s margin"
        )
    verify_local()

    exact = (
        "python tools/run_qtn_5g_aelita_uart_capture.py --execute "
        f"--ack {ACK} --port COM3 --router-host 192.168.1.90 "
        "--seconds 120 --post-seconds 420 --capture-seconds 1470"
    )
    if not args.execute:
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-txpath-oob-plan/v1",
            "mode": "dry-run",
            "capture_starts_before_qdrv": True,
            "capture_survives_management_loss": True,
            "capture_extends_through_rollback_recovery": True,
            "one_shot_trace_profile": "v6-scheduler-diag",
            "qdrv_sha256": V6_QDRV_SHA256,
            "one_shot": str(ONE_SHOT.relative_to(ROOT)).replace("\\", "/"),
            "port": args.port,
            "seconds": args.seconds,
            "post_seconds": args.post_seconds,
            "capture_seconds": capture_seconds,
            "required_capture_seconds": required_capture_seconds,
            "expected_pnp_device_id": EXPECTED_UART_PNP_ID,
            "exact_command": exact,
            "flash": False,
            "bootenv": False,
            "reboot_by_wrapper": False,
            "network_changed_now": False,
        }, indent=2, sort_keys=True))
        print("OMQTN5G_TXPATH_OOB_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"txpath-oob-{stamp}"
    run_dir = args.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    capture_stdout = run_dir / "capture-process.stdout.log"
    capture_stderr = run_dir / "capture-process.stderr.log"
    one_shot_stdout = run_dir / "one-shot.stdout.log"
    one_shot_stderr = run_dir / "one-shot.stderr.log"
    uart_log = run_dir / "uart.log"
    uart_events = run_dir / "uart-events.jsonl"
    capture_status = run_dir / "capture-status.json"
    orchestrator_events = run_dir / "orchestrator-events.jsonl"
    txpath_evaluation = run_dir / "txpath-evaluation.json"
    post_recovery_json = run_dir / "post-recovery.json"
    capture_out = capture_stdout.open("w", encoding="utf-8", newline="\n")
    capture_err = capture_stderr.open("w", encoding="utf-8", newline="\n")
    capture: subprocess.Popen[str] | None = None
    one_shot_rc = 125
    capture_died_early = False
    try:
        append_event(orchestrator_events, run_id, "capture-launch")
        capture = subprocess.Popen(
            [
                "pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(UART_CAPTURE), "-Port", args.port,
                "-Seconds", str(capture_seconds),
                "-OutputDirectory", str(run_dir),
                "-RunId", run_id,
                "-ExpectedPnpDeviceId", EXPECTED_UART_PNP_ID,
            ],
            cwd=ROOT, text=True, stdout=capture_out, stderr=capture_err,
        )
        capture_snapshot = wait_capture_ready(capture, capture_status, capture_stderr)
        append_event(
            orchestrator_events, run_id, "capture-ready",
            port=capture_snapshot.get("current_port"),
            pnp_device_id=capture_snapshot.get("pinned_pnp_device_id"),
        )
        one_shot_command = [
            sys.executable, str(ONE_SHOT), "--execute", "--v6-scheduler-diag",
            "--ack", "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY",
            "--stable-2g-ack", "OPENMITRASTAR_2G_STABLE_FOR_QTN5G",
            "--router-host", args.router_host,
            "--oracle-host", "192.168.1.63", "--oracle-user", "AELITA",
            "--controller-ip", "192.168.1.43",
            "--restore-ssid", "MOVISTAR-WIFI6-A348",
            "--seconds", str(args.seconds),
            "--run-id", run_id,
        ]
        append_event(orchestrator_events, run_id, "one-shot-begin")
        with one_shot_stdout.open("w", encoding="utf-8", newline="\n") as out, one_shot_stderr.open("w", encoding="utf-8", newline="\n") as err:
            one_shot = subprocess.Popen(
                one_shot_command, cwd=ROOT, text=True, stdout=out, stderr=err,
            )
            one_shot_deadline = time.monotonic() + args.seconds + 900
            while one_shot.poll() is None:
                if capture.poll() is not None:
                    capture_died_early = True
                    append_event(
                        orchestrator_events, run_id, "capture-dead",
                        capture_returncode=capture.returncode,
                    )
                    one_shot.terminate()
                    try:
                        one_shot.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        one_shot.kill()
                        one_shot.wait(timeout=5)
                    one_shot_rc = 126
                    break
                if time.monotonic() >= one_shot_deadline:
                    append_event(orchestrator_events, run_id, "one-shot-timeout")
                    one_shot.terminate()
                    try:
                        one_shot.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        one_shot.kill()
                        one_shot.wait(timeout=5)
                    one_shot_rc = 124
                    break
                time.sleep(0.25)
            else:
                one_shot_rc = one_shot.returncode
            if one_shot_rc == 125:
                one_shot_rc = one_shot.returncode
        append_event(orchestrator_events, run_id, "one-shot-end", returncode=one_shot_rc)

        deadline = time.monotonic() + args.post_seconds
        post_recovery: dict[str, object] = {
            "attempted": False,
            "management_ok": False,
            "recovery_clean": False,
            "loglevel_original_present": False,
            "loglevel_matches_original": False,
        }
        next_probe = 0.0
        while time.monotonic() < deadline:
            if capture.poll() is not None:
                capture_died_early = True
                append_event(
                    orchestrator_events, run_id, "capture-dead-post-run",
                    capture_returncode=capture.returncode,
                )
                break
            text = uart_log.read_text(errors="replace") if uart_log.exists() else ""
            events = txpath_evaluator.load_capture_events(uart_events)
            now = time.monotonic()
            if now >= next_probe:
                post_recovery = probe_post_recovery(args.router_host)
                post_recovery_json.write_text(
                    json.dumps(post_recovery, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                next_probe = now + 5
            parsed = txpath_evaluator.evaluate(
                text, run_id, events, one_shot_rc, post_recovery,
            )
            if parsed["terminal_state"] in {
                "PASS_COMMITTED", "FAIL_ROLLED_BACK", "FAIL_RECOVERED_AFTER_REBOOT",
            }:
                break
            time.sleep(1)
    finally:
        if capture and capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait(timeout=5)
        capture_out.close()
        capture_err.close()

    uart_text = uart_log.read_text(errors="replace") if uart_log.exists() else ""
    capture_event_data = txpath_evaluator.load_capture_events(uart_events)
    if not post_recovery_json.exists():
        post_recovery = probe_post_recovery(args.router_host)
        post_recovery_json.write_text(
            json.dumps(post_recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        post_recovery = json.loads(post_recovery_json.read_text(encoding="utf-8-sig"))
    evaluation = txpath_evaluator.evaluate(
        uart_text, run_id, capture_event_data, one_shot_rc, post_recovery,
    )
    if capture_died_early:
        evaluation["capture"]["valid"] = False
        evaluation["capture"]["process_died_early"] = True
        evaluation["terminal_state"] = "CAPTURE_INVALID"
    txpath_evaluation.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    append_event(
        orchestrator_events, run_id, "complete",
        terminal_state=evaluation["terminal_state"], one_shot_rc=one_shot_rc,
    )
    result = {
        "schema": "openmitrastar.qtn-5g-txpath-oob-result/v1",
        "one_shot_rc": one_shot_rc,
        "run_id": run_id,
        "terminal_state": evaluation["terminal_state"],
        "txpath": evaluation["txpath"],
        "uart_log": str(uart_log),
        "uart_events": str(uart_events),
        "capture_status": str(capture_status),
        "orchestrator_events": str(orchestrator_events),
        "txpath_evaluation": str(txpath_evaluation),
        "post_recovery": str(post_recovery_json),
        "capture_stdout": str(capture_stdout),
        "capture_stderr": str(capture_stderr),
        "one_shot_stdout": str(one_shot_stdout),
        "one_shot_stderr": str(one_shot_stderr),
        "hashes": {
            "one_shot": ONE_SHOT_SHA256,
            "qdrv_v6_scheduler_diag": V6_QDRV_SHA256,
            "qtn_runner": QTN_RUNNER_SHA256,
            "uart_capture": UART_CAPTURE_SHA256,
            "evaluator": EVALUATOR_SHA256,
        },
        "flash": False,
        "bootenv": False,
        "reboot_by_wrapper": False,
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"OMQTN5G_TXPATH_OOB_COMPLETE=1 result={result_path} one_shot_rc={one_shot_rc}")
    return 0 if evaluation["terminal_state"] == "PASS_COMMITTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
