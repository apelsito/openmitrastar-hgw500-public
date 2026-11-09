"""Bounded synthetic TFTP path check using existing Windows permission only.

Compiles an ARC client, optionally runs it in HGW RAM, and serves 4096 public
pattern bytes. No firewall changes, firmware, UART, reboot or radio changes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading

import f325_execution_contract as contract
import f325_scoped_tftp as tftp

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"/workspace/user-home\AppData\Local\Programs\Python\Python312\python.exe")
SOURCE = ROOT / "tools/probe_hgw_existing_tftp_path.c"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path: Path) -> str:
    p = path.resolve()
    return "/mnt/" + p.drive[0].lower() + p.as_posix()[2:]


def ssh(command: str, data: bytes | None = None, timeout: int = 15):
    known = Path(contract.F321["directory"]) / contract.F321["known_hosts"]
    args = [r"C:\Windows\System32\OpenSSH\ssh.exe", "-i", str(Path.home()/".ssh/id_ed25519"),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile="+str(known), "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=2",
            "-o", "LogLevel=ERROR", "root@192.168.1.90", command]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout, check=False)


def firewall_snapshot() -> dict:
    script = r'''
$ErrorActionPreference='Stop'
$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')+[IO.Path]::PathSeparator+$env:PSModulePath
$name='UDP Query User{B53A0DF9-DAAE-4615-9572-87C57A3EF67B}/workspace/user-home\appdata\local\programs\python\python312\python.exe'
$r=@(Get-NetFirewallRule -PolicyStore ActiveStore -Name $name)
if($r.Count -ne 1){throw 'One exact pre-existing rule required'}
$r=$r[0]
$a=$r|Get-NetFirewallApplicationFilter
$p=$r|Get-NetFirewallPortFilter
$s=$r|Get-NetFirewallAddressFilter
$n=Get-NetConnectionProfile -InterfaceIndex 18
$ips=@(Get-NetIPAddress -InterfaceIndex 18 -AddressFamily IPv4 | Where-Object {$_.IPAddress -eq '192.168.1.49' -and $_.PrefixLength -eq 24})
if([string]$r.Enabled -cne 'True' -or [string]$r.Action -cne 'Allow' -or [string]$r.Direction -cne 'Inbound' -or [string]$r.Profile -cne 'Public' -or [string]$r.EnforcementStatus -cne 'Enforced'){throw 'Existing permission is not active'}
if($a.Program -ine '/workspace/user-home\AppData\Local\Programs\Python\Python312\python.exe' -or [string]$p.Protocol -cne 'UDP' -or [string]$p.LocalPort -cne 'Any' -or [string]$p.RemotePort -cne 'Any' -or [string]$s.LocalAddress -cne 'Any' -or [string]$s.RemoteAddress -cne 'Any'){throw 'Existing permission filters differ'}
if([string]$n.NetworkCategory -cne 'Public' -or $n.InterfaceAlias -cne 'Ethernet' -or $ips.Count -ne 1){throw 'Current network differs'}
[ordered]@{name=$name;enabled=[string]$r.Enabled;action=[string]$r.Action;direction=[string]$r.Direction;profile=[string]$r.Profile;enforcement=[string]$r.EnforcementStatus;program=$a.Program;program_sha256=(Get-FileHash -LiteralPath $a.Program -Algorithm SHA256).Hash.ToLowerInvariant();protocol=[string]$p.Protocol;local_port=[string]$p.LocalPort;remote_port=[string]$p.RemotePort;local_address=[string]$s.LocalAddress;remote_address=[string]$s.RemoteAddress;interface_index=18;interface_alias='Ethernet';source_ipv4='192.168.1.49';category=[string]$n.NetworkCategory}|ConvertTo-Json -Compress
'''
    p = subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                        "-NoProfile", "-Command", script], capture_output=True, timeout=25)
    if p.returncode:
        raise ValueError("read-only existing permission check failed: "+p.stderr.decode(errors="replace")[-1000:])
    return json.loads(p.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if Path(sys.executable).resolve() != PYTHON.resolve():
        raise SystemExit("Use the exact Python312 covered by the existing permission")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "outputs/preflight" / ("f326-existing-tftp-probe-"+stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out/SOURCE.name).write_bytes(SOURCE.read_bytes())
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    binary = out / "hgw-tftp-path-probe"
    tc = ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-gcc"
    build = " ".join([shlex.quote(linux(tc)), "-std=c99 -Os -Wall -Wextra -Werror -static",
                      shlex.quote(linux(out/SOURCE.name)), "-o", shlex.quote(linux(binary))])
    proc = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", build],
                          capture_output=True, timeout=45)
    (out/"build.stdout").write_bytes(proc.stdout)
    (out/"build.stderr").write_bytes(proc.stderr)
    if proc.returncode:
        raise SystemExit("Probe build failed; no device or network access: "+str(out))
    report = {"schema": "openmitrastar.existing-permission-synthetic-tftp/v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "OFFLINE_BUILT",
              "directory": str(out), "client_sha256": sha(binary), "client_bytes": binary.stat().st_size,
              "server_sha256": sha(Path(tftp.__file__)), "python_sha256": sha(PYTHON),
              "firewall_changes": False, "firmware_transfer": False, "flash": False,
              "uart": False, "reboot": False, "radio_changes": False, "network_access": False}
    if not args.execute:
        (out/"result.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, indent=2)); return 0
    remote = "/tmp/om-path-probe-"+stamp
    uploaded = False
    worker = None
    server_result = []
    ready = threading.Event()
    try:
        before = firewall_snapshot()
        report["permission_before"] = before
        version = "grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION="+contract.F321["version"]+"' /etc/openmitrastar/release"
        p = ssh(version)
        if p.returncode or p.stderr.strip():
            raise ValueError("Pinned F321 baseline not confirmed")
        report["network_access"] = True
        uploaded = True
        p = ssh("umask 077; cat > "+remote+" && chmod 700 "+remote, binary.read_bytes())
        if p.returncode or p.stderr.strip():
            raise ValueError("RAM client upload failed")
        payload_path = out / "pattern.bin"
        payload_path.write_bytes(bytes(range(256))*16)
        payload = tftp.load_verified_file(payload_path, sha(payload_path), 4096)

        def record(event: dict):
            with (out/"tftp-events.jsonl").open("a") as stream:
                stream.write(json.dumps(event)+"\n")
            if event.get("event") == "ready":
                ready.set()

        def serve():
            server_result.append(tftp.serve_once(payload, bind="192.168.1.49", allow_client="192.168.1.90",
                allow_file="om-path-probe.bin", port=69, timeout=20, on_event=record))

        worker = threading.Thread(target=serve)
        worker.start()
        if not ready.wait(5):
            raise ValueError("Scoped synthetic server did not become ready")
        cmd = version+" && sha256sum "+remote+" | grep -q '^"+sha(binary)+" ' && "+remote
        p = ssh(cmd, timeout=18)
        report["client_returncode"] = p.returncode
        report["client_stdout"] = p.stdout.decode(errors="replace")
        report["client_stderr"] = p.stderr.decode(errors="replace")
        worker.join(22)
        if worker.is_alive():
            raise ValueError("Scoped server containment not confirmed")
        report["server_result"] = server_result[0] if server_result else None
        if (p.returncode or p.stderr.strip() or p.stdout != b"PASS_TFTP_SYNTHETIC bytes=4096 data_blocks=9\n"
                or not server_result or server_result[0].get("status") != "PASS_TFTP_SINGLE_TRANSFER"
                or server_result[0].get("sockets_closed") is not True):
            raise ValueError("Synthetic transfer not proved")
        report["status"] = "PASS_TFTP_WITH_EXISTING_PERMISSION"
    except Exception as exc:
        report["status"] = "FAIL_SYNTHETIC_PATH_PROBE"
        report["error"] = str(exc)
    finally:
        if worker is not None:
            worker.join(22)
            report["server_thread_exited"] = not worker.is_alive()
            if worker.is_alive():
                report["status"] = "FAIL_SERVER_CONTAINMENT"
        if uploaded:
            try:
                p = ssh("rm -f "+remote+"; test ! -e "+remote)
                report["ram_client_removed"] = p.returncode == 0 and not p.stderr.strip()
            except Exception:
                report["ram_client_removed"] = False
            if not report["ram_client_removed"]:
                report["status"] = "FAIL_RAM_CLIENT_CLEANUP"
        try:
            after = firewall_snapshot()
            report["permission_after"] = after
            report["permission_unchanged"] = after == report.get("permission_before")
        except Exception:
            report["permission_unchanged"] = False
        if not report["permission_unchanged"]:
            report["status"] = "FAIL_PERMISSION_NOT_CONFIRMED"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (out/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_TFTP_WITH_EXISTING_PERMISSION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
