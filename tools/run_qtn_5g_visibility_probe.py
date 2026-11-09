#!/usr/bin/env python3
"""Probe Quantenna 5 GHz beacon visibility with an automatic hostapd restore.

This runner is intentionally limited to live hostapd configuration.  It does
not flash, reboot, load modules, unload modules, or touch MTD.  The goal is to
separate a Windows/AELITA association problem from a lower qdrv/beacon/RF
problem by briefly switching the already-running wifi0 AP to an open diagnostic
SSID, scanning from AELITA, and restoring the original hostapd config.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTER_KEY = Path.home() / ".ssh/id_ed25519"
ROUTER_KNOWN_HOSTS = Path("NUL")
AELITA_KEY = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/oracle_rsa_unencrypted"
AELITA_KNOWN_HOSTS = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
OPEN_DIAG_SCRIPT = ROOT / "tools/qtn_5g_isolated_open_diag_live.sh"
ACK = "OPENMITRASTAR_QTN5G_VISIBILITY_PROBE_LIVE"


ROUTER_READONLY = r"""
echo SECTION_TIME
date
echo SECTION_STATE
cat /run/openmitrastar/radio5g/state 2>/dev/null || true
echo SECTION_IFCONFIG_WIFI0
ifconfig wifi0 2>&1 || true
echo SECTION_HOSTAPD
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>&1 || true
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 get_config 2>&1 || true
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta 2>&1 || true
echo SECTION_NETDEV
cat /proc/net/dev | grep -E 'eth0|br0|wlan0|wifi0' || true
echo SECTION_QDRV_PARAMS
for f in /sys/module/qdrv/parameters/*; do
  [ -f "$f" ] || continue
  printf '%s=' "$f"
  cat "$f"
done 2>/dev/null | sed -n '1,80p'
echo SECTION_DMESG
dmesg | grep -Ei 'OMQDRV|qdrv|wifi0|hostapd|beacon|MuC|AuC|QMAC|assoc|auth' | tail -n 120
echo SECTION_DONE
"""


RESTORE_SECURE_HOSTAPD = r"""
set -e
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
state=/run/openmitrastar/radio5g
control=/var/run/hostapd
conf=$state/hostapd-secure-restore.conf
fail() {
  printf 'OMQTN5G_RESTORE_SECURE_FAIL reason=%s\n' "$1" >/dev/console 2>/dev/null || true
  printf 'OMQTN5G_RESTORE_SECURE_FAIL reason=%s\n' "$1"
  exit 1
}
[ -s "$conf" ] || fail missing-restore-conf
[ -e /sys/class/net/wifi0 ] || fail wifi0-missing
if [ -s "$state/hostapd.pid" ]; then
  old_pid=$(sed -n '1{s/\r$//;p;}' "$state/hostapd.pid")
  case "$old_pid" in ''|*[!0-9]*) fail old-pid-format ;; esac
  kill "$old_pid" >/dev/null 2>&1 || true
  i=0
  while kill -0 "$old_pid" >/dev/null 2>&1 && [ "$i" -lt 20 ]; do
    i=$((i + 1))
    sleep 1
  done
  kill -0 "$old_pid" >/dev/null 2>&1 && fail old-hostapd-still-live
fi
mkdir -p "$state" "$control"
rm -f "$control/wifi0" "$state/hostapd.pid" "$state/hostapd.status" "$state/hostapd.get_config"
if [ -e /sys/class/net/br0/brif/wifi0 ]; then
  brctl delif br0 wifi0 >/dev/null 2>&1 || true
fi
/usr/sbin/iwpriv-qtn wifi0 region 21317 >/dev/null 2>&1 || fail region-set
/usr/sbin/iwpriv-qtn wifi0 mode 11ac80Edge+ >/dev/null 2>&1 || fail mode-set
/usr/sbin/iwconfig-qtn wifi0 essid MOVISTAR_PLUS_55CB >/dev/null 2>&1 || fail ssid-set
/usr/sbin/iwconfig-qtn wifi0 channel 36 >/dev/null 2>&1 || fail channel-set
ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1 || true
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || fail isolated-l3-address
(
  trap '' HUP
  exec /usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf"
) >/dev/null 2>&1 &
pid=$!
case "$pid" in ''|*[!0-9]*) fail new-pid ;; esac
printf '%s\n' "$pid" >"$state/hostapd.pid"
chmod 0600 "$state/hostapd.pid"
ready=0
i=0
while [ "$i" -lt 30 ]; do
  i=$((i + 1))
  if kill -0 "$pid" >/dev/null 2>&1 &&
    /usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 ping >"$state/hostapd.status" 2>&1 &&
    grep -qx PONG "$state/hostapd.status"; then
    /usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 get_config >"$state/hostapd.get_config" 2>&1 || true
    if grep -Fqx 'ssid=MOVISTAR_PLUS_55CB' "$state/hostapd.get_config" &&
      grep -Eq '^key_mgmt=.*WPA-PSK' "$state/hostapd.get_config" &&
      grep -Eq '^(group_cipher|rsn_pairwise_cipher)=CCMP' "$state/hostapd.get_config"; then
      ready=1
      break
    fi
  fi
  sleep 1
done
[ "$ready" = 1 ] || fail hostapd-secure-not-ready
/usr/sbin/iwpriv-qtn wifi0 pm 0 >/dev/null 2>&1 || fail pm0-set
pm_readback=$(/usr/sbin/iwpriv-qtn wifi0 get_pm 2>/dev/null) || fail pm0-get
printf '%s\n' "$pm_readback" | grep -q 'get_pm:0' || fail pm0-readback
printf 'ready\n' >"$state/state"
printf 'OMQTN5G_RESTORE_SECURE_READY ssid=MOVISTAR_PLUS_55CB flash=0\n'
"""


PREPARE_SECURE_RESTORE_HOSTAPD = r"""
set -e
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
state=/run/openmitrastar/radio5g
control=/var/run/hostapd
psk_file=/run/openmitrastar/secrets/wpa2.psk
conf=$state/hostapd-secure-restore.conf
current=$state/hostapd.current.get_config
fail() {
  printf 'OMQTN5G_PREPARE_RESTORE_FAIL reason=%s\n' "$1" >/dev/console 2>/dev/null || true
  printf 'OMQTN5G_PREPARE_RESTORE_FAIL reason=%s\n' "$1"
  exit 1
}
mkdir -p "$state"
chmod 0700 "$state"
/usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 ping >/tmp/omqtn5g-ping.$$ 2>&1 || fail hostapd-ping
grep -qx PONG /tmp/omqtn5g-ping.$$ || fail hostapd-pong
rm -f /tmp/omqtn5g-ping.$$
/usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 get_config >"$current" 2>&1 || fail get-config
chmod 0600 "$current"
ssid=$(sed -n 's/^ssid=//p' "$current" | sed -n '1{s/\r$//;p;}')
case "$ssid" in ''|*[!A-Za-z0-9_.-]*) fail ssid ;; esac
[ "$ssid" = MOVISTAR_PLUS_55CB ] || fail unexpected-ssid
grep -Eq '^key_mgmt=.*WPA-PSK' "$current" || fail key-mgmt
grep -Eq '^(group_cipher|rsn_pairwise_cipher)=CCMP' "$current" || fail ccmp
[ -r "$psk_file" ] || fail psk-file
[ "$(awk 'END { print NR }' "$psk_file" 2>/dev/null)" = 1 ] || fail psk-lines
IFS= read -r psk <"$psk_file" || fail psk-read
case "$psk" in ''|*[!A-Za-z0-9_.-]*) unset psk; fail psk-characters ;; esac
[ "${#psk}" -ge 8 ] && [ "${#psk}" -le 63 ] || { unset psk; fail psk-length; }
{
  printf '%s\n' 'driver=madwifi' 'interface=wifi0' 'hw_mode=a' 'channel=36'
  printf 'ssid=%s\n' "$ssid"
  printf '%s\n' 'wpa=2' 'wpa_key_mgmt=WPA-PSK' 'wpa_pairwise=CCMP'
  printf 'wpa_passphrase=%s\n' "$psk"
  printf '%s\n' 'auth_algs=1' 'wpa_group_rekey=0' 'wpa_strict_rekey=0' 'wpa_gmk_rekey=0'
  printf '%s\n' 'ctrl_interface=/var/run/hostapd'
  printf '%s\n' 'logger_syslog=-1' 'logger_syslog_level=3' 'logger_stdout=-1' 'logger_stdout_level=3'
} >"$conf"
unset psk
chmod 0600 "$conf"
printf 'OMQTN5G_PREPARE_RESTORE_READY ssid=%s conf=%s secrets=redacted flash=0\n' "$ssid" "$conf"
"""


def run_cmd(args: list[str], *, input_text: str | None = None, timeout: int = 60) -> dict[str, Any]:
    started = time.time()
    input_bytes = input_text.encode("utf-8") if input_text is not None else None
    proc = subprocess.run(
        args,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return {
        "args": args,
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", errors="replace"),
        "stderr": proc.stderr.decode("utf-8", errors="replace"),
        "duration_s": round(time.time() - started, 3),
    }


def ssh_args(host: str, user: str, key: Path, known_hosts: Path, command: str) -> list[str]:
    known_hosts_text = str(known_hosts)
    strict_host_key = "StrictHostKeyChecking=no" if known_hosts_text.upper() == "NUL" else "StrictHostKeyChecking=accept-new"
    return [
        "ssh",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        strict_host_key,
        "-o",
        f"UserKnownHostsFile={known_hosts_text}",
        "-o",
        "HostKeyAlgorithms=+ssh-rsa",
        "-o",
        "PubkeyAcceptedAlgorithms=+ssh-rsa",
        "-o",
        "LogLevel=ERROR",
        f"{user}@{host}",
        command,
    ]


def router(command: str, *, input_text: str | None = None, timeout: int = 60) -> dict[str, Any]:
    return run_cmd(
        ssh_args("192.168.1.90", "root", ROUTER_KEY, ROUTER_KNOWN_HOSTS, command),
        input_text=input_text,
        timeout=timeout,
    )


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def router_script(script_text: str, remote_path: str, script_args: list[str] | None = None, *, timeout: int = 60) -> dict[str, Any]:
    args = " ".join(sh_quote(arg) for arg in (script_args or []))
    command = (
        f"tmp={sh_quote(remote_path)}; "
        'cat >"$tmp" && chmod 0700 "$tmp" && /bin/ash "$tmp"'
        + (f" {args}" if args else "")
        + '; rc=$?; rm -f "$tmp"; exit "$rc"'
    )
    return router(command, input_text=script_text.replace("\r\n", "\n"), timeout=timeout)


def aelita(command: str, timeout: int = 60) -> dict[str, Any]:
    return run_cmd(
        ssh_args("192.168.1.63", "AELITA", AELITA_KEY, AELITA_KNOWN_HOSTS, command),
        timeout=timeout,
    )


def scan_aelita(*, start_wlansvc: bool = False) -> dict[str, Any]:
    service = "Start-Service wlansvc -ErrorAction SilentlyContinue; " if start_wlansvc else ""
    command = (
        "powershell.exe -NoProfile -NonInteractive -Command "
        f"\"{service}"
        "Write-Output '---SERVICE---'; Get-Service wlansvc | Format-List Name,Status,StartType; "
        "Write-Output '---ADAPTERS---'; Get-NetAdapter -Physical -ErrorAction SilentlyContinue | "
        "Format-Table -AutoSize Name,InterfaceDescription,Status,LinkSpeed; "
        "Write-Output '---NETWORKS---'; netsh wlan show networks mode=bssid; "
        "Write-Output '---INTERFACES---'; netsh wlan show interfaces\""
    )
    result = aelita(command, 90)
    text = result["stdout"]
    result["visible_target_ssids"] = {
        "OpenMitraStar-5G-DIAG": "OpenMitraStar-5G-DIAG" in text,
        "MOVISTAR_PLUS_55CB": "MOVISTAR_PLUS_55CB" in text,
    }
    return result


def redacted(result: dict[str, Any]) -> dict[str, Any]:
    clean = dict(result)
    clean.pop("args", None)
    for key in ("stdout", "stderr"):
        if isinstance(clean.get(key), str):
            clean[key] = re.sub(r"(?i)(passphrase|psk)([^\\n]*)", r"\1 [REDACTED]", clean[key])
    return clean


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--ssid", default="OpenMitraStar-5G-DIAG")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--start-wlansvc", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.ssid != "OpenMitraStar-5G-DIAG":
        raise SystemExit("SSID is pinned to OpenMitraStar-5G-DIAG for this probe")
    if not args.execute:
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-visibility-probe-plan/v1",
            "execute": False,
            "router": "root@192.168.1.90",
            "oracle": "AELITA@192.168.1.63",
            "ssid": args.ssid,
            "steps": (
                ["router-readonly", "aelita-scan"]
                if args.scan_only else
                ["router-readonly-before", "aelita-scan-before", "open-diag-live", "aelita-scan-open", "restore-secure-hostapd", "router-readonly-after"]
            ),
            "flash": False,
            "reboot": False,
            "module_loads": False,
            "mtd_writes": False,
            "router_mutations": False if args.scan_only else "hostapd-live-only",
            "aelita_start_wlansvc": args.start_wlansvc,
        }, indent=2, sort_keys=True))
        print("OMQTN5G_VISIBILITY_PROBE_DRY_RUN_PASS=1 execute=0")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"Require --ack {ACK}")
    for required in (ROUTER_KEY, AELITA_KEY, AELITA_KNOWN_HOSTS, OPEN_DIAG_SCRIPT):
        if not required.exists():
            raise SystemExit(f"missing required input: {required}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = args.output_dir or ROOT / f"outputs/f3-certification/qtn-5g-visibility/{stamp}"
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, Any] = {
        "schema": "openmitrastar.qtn-5g-visibility-probe/v1",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ssid": args.ssid,
        "flash": False,
        "reboot": False,
        "module_loads": False,
        "mtd_writes": False,
        "router_mutations": "hostapd-live-only",
        "aelita_start_wlansvc": args.start_wlansvc,
    }
    if args.scan_only:
        evidence["router_mutations"] = False
        evidence["router_readonly"] = redacted(router(ROUTER_READONLY, timeout=40))
        evidence["aelita_scan"] = redacted(scan_aelita(start_wlansvc=args.start_wlansvc))
        evidence["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        visible = evidence["aelita_scan"].get("visible_target_ssids", {}).get(args.ssid) is True
        evidence["status"] = "PASS_VISIBLE" if visible else "FAIL_NOT_VISIBLE"
        path = out_dir / "visibility-scan-only.json"
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-visibility-scan-only-summary/v1",
            "status": evidence["status"],
            "visible": visible,
            "visible_target_ssids": evidence["aelita_scan"].get("visible_target_ssids"),
            "aelita_rc": evidence["aelita_scan"].get("rc"),
            "router_rc": evidence["router_readonly"].get("rc"),
            "artifact": str(path),
            "flash": False,
            "reboot": False,
            "router_mutations": False,
        }, indent=2, sort_keys=True))
        print(f"OMQTN5G_VISIBILITY_SCAN_ONLY_RESULT={path}")
        return 0 if visible else 2
    rc = 1
    try:
        evidence["router_before"] = redacted(router(ROUTER_READONLY, timeout=40))
        evidence["aelita_scan_before"] = redacted(scan_aelita(start_wlansvc=args.start_wlansvc))
        evidence["prepare_restore"] = redacted(router_script(
            PREPARE_SECURE_RESTORE_HOSTAPD,
            "/tmp/openmitrastar-qtn5g-prepare-restore.sh",
            timeout=40,
        ))
        if evidence["prepare_restore"]["rc"] != 0:
            rc = 3
        else:
            open_script = OPEN_DIAG_SCRIPT.read_text(encoding="utf-8")
            evidence["open_diag"] = redacted(
                router_script(
                    open_script,
                    "/tmp/openmitrastar-qtn5g-open-diag-live.sh",
                    [args.ssid],
                    timeout=60,
                )
            )
            time.sleep(4)
            evidence["router_open"] = redacted(router(ROUTER_READONLY, timeout=40))
            evidence["aelita_scan_open"] = redacted(scan_aelita(start_wlansvc=args.start_wlansvc))
            rc = 0 if (
                evidence["open_diag"]["rc"] == 0
                and evidence["aelita_scan_open"].get("visible_target_ssids", {}).get(args.ssid) is True
            ) else 2
    finally:
        if evidence.get("prepare_restore", {}).get("rc") == 0 or "open_diag" in evidence:
            evidence["restore"] = redacted(router_script(
                RESTORE_SECURE_HOSTAPD,
                "/tmp/openmitrastar-qtn5g-restore-secure.sh",
                timeout=70,
            ))
        else:
            evidence["restore"] = {
                "rc": 0,
                "stdout": "OMQTN5G_RESTORE_SKIPPED reason=prepare-restore-failed-no-live-mutation\n",
                "stderr": "",
                "duration_s": 0,
            }
        time.sleep(3)
        evidence["router_after"] = redacted(router(ROUTER_READONLY, timeout=40))
        evidence["aelita_scan_after"] = redacted(scan_aelita(start_wlansvc=args.start_wlansvc))
        evidence["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        evidence["status"] = "PASS_VISIBLE" if rc == 0 else "FAIL_NOT_VISIBLE"
        evidence["restored"] = evidence["restore"]["rc"] == 0
        path = out_dir / "visibility-probe.json"
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-visibility-probe-summary/v1",
            "status": evidence["status"],
            "restored": evidence["restored"],
            "before_visible": evidence["aelita_scan_before"].get("visible_target_ssids"),
            "open_visible": evidence.get("aelita_scan_open", {}).get("visible_target_ssids"),
            "after_visible": evidence["aelita_scan_after"].get("visible_target_ssids"),
            "prepare_restore_rc": evidence.get("prepare_restore", {}).get("rc"),
            "open_diag_rc": evidence.get("open_diag", {}).get("rc"),
            "restore_rc": evidence["restore"]["rc"],
            "artifact": str(path),
            "flash": False,
            "reboot": False,
        }, indent=2, sort_keys=True))
        print(f"OMQTN5G_VISIBILITY_PROBE_RESULT={path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
