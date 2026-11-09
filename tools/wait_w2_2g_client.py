#!/usr/bin/env python3
"""Wait for a physical 2.4 GHz client on the live OpenMitraStar AP.

This helper is deliberately observe-only.  It polls hostapd over the existing
RAM SSH channel and writes a bounded JSON transcript so the TX7 traffic gate can
be armed only after a real station appears.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402
from ramssh_exec import load_private_key  # noqa: E402


LINE_RE = re.compile(
    r"^OM2G_WAIT seq=(?P<seq>\d+) uptime=(?P<uptime>\d+) "
    r"state=(?P<state>\w+) assoc=(?P<assoc>\d+) authorized=(?P<authorized>\d+) "
    r"kernel_sta=(?P<kernel_sta>\d+) "
    r"kernel_authenticated=(?P<kernel_authenticated>\d+) "
    r"kernel_associated=(?P<kernel_associated>\d+) "
    r"kernel_authorized=(?P<kernel_authorized>\d+) "
    r"carrier=(?P<carrier>[01]) ctrl=(?P<ctrl>\S+)$"
)


def remote_command(ctrl: str) -> str:
    ctrl_candidates = [ctrl] if ctrl != "auto" else [
        "/run/openmitrastar/radio2g/ctrl",
        "/run/openmitrastar/radio2g/ctrl-open",
    ]
    candidate_words = " ".join(shlex.quote(path) for path in ctrl_candidates)
    return rf'''set +e
status=
all_sta=
ctrl_used=none
for ctrl_try in {candidate_words}; do
  status=$(/usr/sbin/hostapd_cli -p "$ctrl_try" -i wlan0 status 2>/dev/null)
  if printf '%s\n' "$status" | grep -q '^state='; then
    ctrl_used=$ctrl_try
    all_sta=$(/usr/sbin/hostapd_cli -p "$ctrl_try" -i wlan0 all_sta 2>/dev/null)
    break
  fi
done
uptime=$(cut -d. -f1 /proc/uptime 2>/dev/null); [ -n "$uptime" ] || uptime=0
state=$(printf '%s\n' "$status" | sed -n 's/^state=//p'); [ -n "$state" ] || state=DOWN
assoc=$(printf '%s\n' "$status" | sed -n 's/^num_sta\[0\]=//p'); [ -n "$assoc" ] || assoc=0
authorized=$(printf '%s\n' "$all_sta" | grep -c 'AUTHORIZED'); [ -n "$authorized" ] || authorized=0
iw_sta=$(iw dev wlan0 station dump 2>/dev/null)
kernel_sta=$(printf '%s\n' "$iw_sta" | grep -c '^Station ')
kernel_authenticated=$(printf '%s\n' "$iw_sta" | grep -c 'authenticated:[[:space:]]*yes')
kernel_associated=$(printf '%s\n' "$iw_sta" | grep -c 'associated:[[:space:]]*yes')
kernel_authorized=$(printf '%s\n' "$iw_sta" | grep -c 'authorized:[[:space:]]*yes')
carrier=$(cat /sys/class/net/wlan0/carrier 2>/dev/null); [ "$carrier" = 1 ] || carrier=0
echo "OM2G_WAIT seq=0 uptime=$uptime state=$state assoc=$assoc authorized=$authorized kernel_sta=$kernel_sta kernel_authenticated=$kernel_authenticated kernel_associated=$kernel_associated kernel_authorized=$kernel_authorized carrier=$carrier ctrl=$ctrl_used"
'''


def parse_sample(text: str, seq: int) -> dict[str, int | str]:
    for line in text.splitlines():
        match = LINE_RE.fullmatch(line.strip())
        if not match:
            continue
        sample: dict[str, int | str] = {
            key: int(value)
            if key in {
                "seq",
                "uptime",
                "assoc",
                "authorized",
                "kernel_sta",
                "kernel_authenticated",
                "kernel_associated",
                "kernel_authorized",
                "carrier",
            }
            else value
            for key, value in match.groupdict().items()
        }
        sample["seq"] = seq
        return sample
    raise ValueError(f"missing OM2G_WAIT line in SSH output: {text!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--timeout", type=int, default=5)
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--interval", type=int, default=2)
    parser.add_argument("--ctrl", default="auto")
    parser.add_argument("--require-authorized", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not 1 <= args.interval <= 30:
        raise SystemExit("--interval must be 1..30")
    if not 1 <= args.wait_seconds <= 7200:
        raise SystemExit("--wait-seconds must be 1..7200")
    if args.ctrl != "auto" and not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.ctrl):
        raise SystemExit("--ctrl must be 'auto' or an absolute safe path")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    samples: list[dict[str, int | str]] = []
    errors: list[str] = []
    satisfied = False

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            args.host,
            port=args.port,
            username="root",
            pkey=load_private_key(),
            look_for_keys=False,
            allow_agent=False,
            timeout=args.timeout,
            banner_timeout=args.timeout,
            auth_timeout=args.timeout,
        )
        seq = 0
        while True:
            _, stdout, stderr = client.exec_command(remote_command(args.ctrl), timeout=args.timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if err.strip():
                errors.append(err.strip())
            sample = parse_sample(out, seq)
            samples.append(sample)
            print(
                "OM2G_WAIT seq={seq} uptime={uptime} state={state} assoc={assoc} "
                "authorized={authorized} kernel_sta={kernel_sta} "
                "kernel_authenticated={kernel_authenticated} "
                "kernel_associated={kernel_associated} "
                "kernel_authorized={kernel_authorized} carrier={carrier} "
                "ctrl={ctrl}".format(**sample),
                flush=True,
            )
            assoc_ok = int(sample["assoc"]) > 0
            auth_ok = int(sample["authorized"]) > 0
            satisfied = assoc_ok and (auth_ok or not args.require_authorized)
            if satisfied:
                break
            if time.monotonic() - started >= args.wait_seconds:
                break
            seq += 1
            time.sleep(args.interval)
    except Exception as exc:  # noqa: BLE001 - write bounded diagnostic into JSON.
        errors.append(str(exc))
    finally:
        client.close()

    last = samples[-1] if samples else {}
    kernel_sta_observed = any(int(row["kernel_sta"]) > 0 for row in samples)
    kernel_auth_observed = any(int(row["kernel_authenticated"]) > 0 for row in samples)
    kernel_assoc_observed = any(int(row["kernel_associated"]) > 0 for row in samples)
    if satisfied:
        status = "CLIENT_READY"
    elif kernel_assoc_observed:
        status = "KERNEL_ASSOC_NO_HOSTAPD_AUTHORIZED"
    elif kernel_auth_observed or kernel_sta_observed:
        status = "AUTH_ONLY_KERNEL"
    else:
        status = "NO_CLIENT"
    result = {
        "schema": "openmitrastar.w2-2g-client-wait/v1",
        "host": args.host,
        "wait_seconds": args.wait_seconds,
        "interval": args.interval,
        "require_authorized": args.require_authorized,
        "duration_observed_seconds": round(time.monotonic() - started, 3),
        "samples_observed": len(samples),
        "association_observed": any(int(row["assoc"]) > 0 for row in samples),
        "authorization_observed": any(int(row["authorized"]) > 0 for row in samples),
        "kernel_station_observed": kernel_sta_observed,
        "kernel_authentication_observed": kernel_auth_observed,
        "kernel_association_observed": kernel_assoc_observed,
        "ap_enabled_all_samples": bool(samples) and all(row["state"] == "ENABLED" for row in samples),
        "carrier_all_samples": bool(samples) and all(int(row["carrier"]) == 1 for row in samples),
        "last_sample": last or None,
        "status": status,
        "pass": satisfied,
        "errors": errors,
        "mutations": False,
        "flash": False,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if satisfied else 2


if __name__ == "__main__":
    raise SystemExit(main())
