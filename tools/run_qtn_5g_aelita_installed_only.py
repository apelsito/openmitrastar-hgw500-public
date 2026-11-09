#!/usr/bin/env python3
"""Run a 5 GHz AELITA gate using only the firmware-installed router scripts.

This deliberately avoids the older RAM overlay path.  The router-side mutation
is limited to a bounded `/usr/sbin/om-radio5-start` and the matching
`/usr/sbin/om-radio5-stop`, with `wifi0` isolated from `br0`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import run_qtn_5g_aelita_one_shot as aelita_gate  # noqa: E402
import run_qtn_w3_tx7_client_traffic as qtn_runner  # noqa: E402
import evaluate_qtn_5g_isolated_l3 as evaluator  # noqa: E402


ACK = "OPENMITRASTAR_QTN_5G_AELITA_INSTALLED_ONLY"
STABLE_ACK = "OPENMITRASTAR_F75_2G_5G_DRYRUN_RF_SMOKE_PASS"
ROUTER_MONITOR = ROOT / "tools/q3_client_stream_single_session.py"


def router_start_installed(host: str, run_id: str) -> str:
    command = rf'''set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
echo OMQTN5G_INSTALLED_START_BEGIN run_id={run_id}
test -x /usr/sbin/om-qtn-cal-readonly
test -x /usr/sbin/om-qtn-mac-prepare
test -x /usr/sbin/om-radio5-start
test -x /usr/sbin/om-radio5-stop
/usr/sbin/om-qtn-cal-readonly
/usr/sbin/om-qtn-mac-prepare
/usr/sbin/om-radio5-start
echo SECTION_TOPOLOGY_AFTER_START
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
ifconfig wifi0 2>/dev/null || true
echo OMQTN5G_INSTALLED_START_END run_id={run_id}
'''
    result = qtn_runner.ssh(host, command, 180)
    if "OMRADIO5_READY" not in result.stdout:
        raise RuntimeError("om-radio5-start did not emit OMRADIO5_READY")
    if "\nwifi0\n" in result.stdout:
        raise RuntimeError("wifi0 appeared in br0 after om-radio5-start")
    return result.stdout


def router_stop_installed(host: str, reason: str) -> str:
    command = rf'''set +e
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
echo OMQTN5G_INSTALLED_STOP_BEGIN reason={reason}
if [ -x /usr/sbin/om-radio5-stop ]; then
  /usr/sbin/om-radio5-stop {reason}
fi
echo SECTION_TOPOLOGY_AFTER_STOP
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo OMQTN5G_INSTALLED_STOP_END reason={reason}
'''
    return qtn_runner.ssh(host, command, 90, check=False).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--stable-ack", default="")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--oracle-user", default="AELITA")
    parser.add_argument("--restore-ssid", default="MOVISTAR-WIFI6-A348")
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "outputs/postflash/qtn-5g-aelita-installed-only")
    args = parser.parse_args()
    if not 60 <= args.seconds <= 900:
        raise SystemExit("--seconds must be 60..900")
    if args.oracle_host != aelita_gate.ORACLE_HOST or args.oracle_user != aelita_gate.ORACLE_USER:
        raise SystemExit("this gate is pinned to AELITA@192.168.1.63")

    if not args.execute:
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-aelita-installed-only-plan/v1",
            "mode": "dry-run",
            "router": args.router_host,
            "oracle": f"{args.oracle_user}@{args.oracle_host}",
            "router_side": "installed /usr/sbin/om-radio5-start then /usr/sbin/om-radio5-stop",
            "router_overlay": False,
            "flash": False,
            "expected_topology": "wifi0=192.168.77.1/24 outside br0",
            "duration_seconds": args.seconds,
        }, indent=2, sort_keys=True))
        print("OMQTN5G_AELITA_INSTALLED_ONLY_DRY_RUN_PASS=1 execute=0 router_overlay=0 flash=0")
        return 0
    if args.ack != ACK or args.stable_ack != STABLE_ACK:
        raise SystemExit(f"require --ack {ACK} and --stable-ack {STABLE_ACK}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"installed-{stamp}"
    start_log = args.output_dir / f"router-start-{stamp}.log"
    stop_log = args.output_dir / f"router-stop-{stamp}.log"
    router_log = args.output_dir / f"router-monitor-{stamp}.log"
    windows_json = args.output_dir / f"windows-{stamp}.json"
    result_json = args.output_dir / f"evaluation-{stamp}.json"
    oracle_started = False
    try:
        start_log.write_text(router_start_installed(args.router_host, run_id), encoding="utf-8", newline="\n")
        aelita_gate.stage_oracle(args.oracle_host, args.oracle_user)
        aelita_gate.start_oracle_task(
            args.oracle_host,
            args.oracle_user,
            seconds=args.seconds,
            restore_ssid=args.restore_ssid,
            expected_bssid="",
        )
        oracle_started = True
        monitor_seconds = min(args.seconds + 90, 900)
        monitor = subprocess.run(
            [
                sys.executable, str(ROUTER_MONITOR),
                "--host", args.router_host,
                "--seconds", str(monitor_seconds),
                "--interval", "1",
                "--require-client-traffic",
                "--isolated-l3",
                "--output", str(router_log),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=monitor_seconds + 90,
            check=False,
        )
        windows = aelita_gate.wait_oracle_result(
            args.oracle_host,
            args.oracle_user,
            args.seconds + 660,
        )
        windows_json.write_text(json.dumps(windows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        router_summary = router_log.with_suffix(router_log.suffix + ".json")
        router = json.loads(router_summary.read_text(encoding="utf-8"))
        result = evaluator.evaluate(windows, router, duration_min=args.seconds)
        result["schema"] = "openmitrastar.qtn-5g-aelita-installed-only-evaluation/v1"
        result["oracle"] = f"{args.oracle_user}@{args.oracle_host}"
        result["router_monitor_rc"] = monitor.returncode
        result["router_start_log"] = str(start_log)
        result["router_stop_log"] = str(stop_log)
        result["windows_result"] = str(windows_json)
        result["router_result"] = str(router_summary)
        result["router_overlay"] = False
        result["flash"] = False
        result_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if monitor.returncode or result["status"] != "PASS":
            raise RuntimeError(f"installed-only AELITA gate failed: {result['failures']}")
        print(f"OMQTN5G_AELITA_INSTALLED_ONLY_PASS=1 result={result_json} flash=0 router_overlay=0")
        return 0
    except Exception as exc:
        failure = {
            "schema": "openmitrastar.qtn-5g-aelita-installed-only-failure/v1",
            "error": f"{type(exc).__name__}: {exc}",
            "oracle_started": oracle_started,
            "start_log": str(start_log),
            "stop_log": str(stop_log),
            "router_log": str(router_log),
            "windows_result": str(windows_json),
            "flash": False,
            "router_overlay": False,
        }
        (args.output_dir / f"failure-{stamp}.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        try:
            stop_log.write_text(
                router_stop_installed(args.router_host, "aelita-installed-only-finally"),
                encoding="utf-8",
                newline="\n",
            )
        except Exception as exc:
            with stop_log.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"\nOMQTN5G_INSTALLED_STOP_ERROR {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
