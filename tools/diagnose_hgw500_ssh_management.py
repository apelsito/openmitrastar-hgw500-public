#!/usr/bin/env python3
"""Read-only HGW-500BNA-QCv2 SSH/management discriminator.

This script does not reboot, write RAM, write MTD, change bootenv, or mutate the
default OpenSSH known_hosts file. It separates liveness from SSH auth problems
so a failed SSH login does not get misread as a dead router.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "outputs/recovery/ssh-management"
DEFAULT_KEY = Path.home() / ".ssh/id_ed25519"
EXPECTED_MODEL = "MitraStar HGW-500BNA-QCv2"
EXPECTED_FIRMWARE = "product-rootfs-v1"


def tcp_probe(host: str, port: int, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {
                "port": port,
                "open": True,
                "error": None,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
    except OSError as exc:
        return {
            "port": port,
            "open": False,
            "error": f"{exc.__class__.__name__}: {exc}",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }


def ping_probe(host: str, timeout: int) -> dict[str, Any]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "2", "-w", str(max(1000, timeout * 1000)), host]
    else:
        cmd = ["ping", "-c", "2", "-W", str(max(1, timeout)), host]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=max(3, timeout * 3),
            check=False,
        )
        text = proc.stdout or ""
        ok = proc.returncode == 0 and re.search(r"\bTTL=|\bttl=", text) is not None
        return {"ok": ok, "exit": proc.returncode, "stdout_tail": tail(text)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "exit": None, "stdout_tail": f"{exc.__class__.__name__}: {exc}"}


def getinfo_probe(host: str, timeout: int) -> dict[str, Any]:
    try:
        conn = http.client.HTTPConnection(host, 16667, timeout=timeout)
        conn.request("GET", "/getinfo.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(8192).decode("utf-8", errors="replace")
        payload = json.loads(body)
        data = payload.get("resultData", {}) if isinstance(payload, dict) else {}
        identity_ok = (
            response.status == 200
            and data.get("model") == EXPECTED_MODEL
            and data.get("firmware") == EXPECTED_FIRMWARE
        )
        return {
            "ok": response.status == 200,
            "identity_ok": identity_ok,
            "status": response.status,
            "model": data.get("model"),
            "vendor": data.get("vendor"),
            "firmware": data.get("firmware"),
            "mode": data.get("mode"),
            "raw_body": body if len(body) <= 1000 else body[:1000],
        }
    except (OSError, json.JSONDecodeError, http.client.HTTPException) as exc:
        return {
            "ok": False,
            "identity_ok": False,
            "status": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
        except Exception:
            pass


def tail(text: str, limit: int = 2400) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_ssh_probe(
    host: str,
    user: str,
    key: Path,
    timeout: int,
    isolated_known_hosts: bool,
) -> dict[str, Any]:
    command = "echo OMSSH_DIAG_OK; uname -a"
    temp_path: Path | None = None
    options = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "IdentitiesOnly=yes",
    ]
    if isolated_known_hosts:
        handle = tempfile.NamedTemporaryFile(prefix="om-hgw500-known-hosts-", delete=False)
        handle.close()
        temp_path = Path(handle.name)
        options += [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"UserKnownHostsFile={temp_path}",
        ]
    else:
        options += ["-o", "StrictHostKeyChecking=yes"]
    if key:
        options += ["-i", str(key)]
    options += [f"{user}@{host}", command]
    try:
        proc = subprocess.run(
            options,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout + 8,
            check=False,
        )
        output = proc.stdout or ""
        return {
            "exit": proc.returncode,
            "ok": proc.returncode == 0 and "OMSSH_DIAG_OK" in output,
            "classification": classify_ssh_output(proc.returncode, output),
            "stdout_tail": tail(output),
            "isolated_known_hosts": isolated_known_hosts,
            "known_hosts_mutated": isolated_known_hosts,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "exit": None,
            "ok": False,
            "classification": "SSH_CLIENT_ERROR",
            "stdout_tail": f"{exc.__class__.__name__}: {exc}",
            "isolated_known_hosts": isolated_known_hosts,
            "known_hosts_mutated": isolated_known_hosts,
        }
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def classify_ssh_output(exit_code: int | None, output: str) -> str:
    lower = output.lower()
    if exit_code == 0 and "OMSSH_DIAG_OK" in output:
        return "SSH_AUTH_OK"
    if "remote host identification has changed" in lower or "host key verification failed" in lower:
        return "SSH_HOSTKEY_PROBLEM"
    if "permission denied" in lower and "publickey" in lower:
        return "SSH_AUTH_REJECTED_PUBLICKEY"
    if "connection timed out" in lower or "operation timed out" in lower:
        return "SSH_CONNECT_TIMEOUT"
    if "connection refused" in lower:
        return "SSH_CONNECTION_REFUSED"
    if "no route to host" in lower or "network is unreachable" in lower:
        return "SSH_NETWORK_UNREACHABLE"
    return "SSH_UNKNOWN_FAILURE"


def decide(report: dict[str, Any]) -> tuple[str, str]:
    ping_ok = bool(report["ping"]["ok"])
    ssh_open = bool(report["tcp"]["22"]["open"])
    http_open = bool(report["tcp"]["80"]["open"])
    getinfo_ok = bool(report["getinfo"]["ok"])
    identity_ok = bool(report["getinfo"]["identity_ok"])
    default_class = report["ssh_default_known_hosts"]["classification"]
    isolated = report["ssh_isolated_known_hosts"]
    isolated_class = isolated["classification"]
    isolated_ok = bool(isolated["ok"])

    management_alive = http_open or getinfo_ok or identity_ok
    if isolated_ok:
        if default_class == "SSH_HOSTKEY_PROBLEM":
            return (
                "SSH_OK_DEFAULT_KNOWN_HOSTS_STALE",
                "No physical reboot. Clean or refresh the local known_hosts entry; isolated SSH auth works.",
            )
        return ("SSH_OK", "No physical reboot. SSH auth and management path are usable.")
    if ssh_open and isolated_class == "SSH_AUTH_REJECTED_PUBLICKEY":
        if management_alive:
            return (
                "SSH_AUTH_REJECTED_MANAGEMENT_OK",
                "No physical reboot indicated. Router management is alive; fix key provisioning or booted rootfs authorized_keys.",
            )
        return (
            "SSH_AUTH_REJECTED_HTTP_DOWN",
            "SSH service is alive but key is rejected. Treat as credential/rootfs auth issue before power-cycling.",
        )
    if default_class == "SSH_HOSTKEY_PROBLEM" and isolated_class == "SSH_AUTH_REJECTED_PUBLICKEY":
        return (
            "SSH_HOSTKEY_STALE_AND_AUTH_REJECTED",
            "No physical reboot indicated while management is alive. Fix local known_hosts and authorized_keys/rootfs key provisioning.",
        )
    if not ssh_open and management_alive:
        return (
            "SSH_SERVICE_DOWN_MANAGEMENT_OK",
            "Management plane is alive but SSH is not listening. Diagnose Dropbear/startup policy; physical reboot is a fallback only.",
        )
    if not ssh_open and not management_alive and not ping_ok:
        return (
            "MANAGEMENT_UNREACHABLE_PHYSICAL_RECOVERY_CANDIDATE",
            "Network management is not proven. Physical power-cycle or UART recovery may be needed after checking cabling/IP.",
        )
    if ping_ok and not management_alive and not ssh_open:
        return (
            "IP_ALIVE_SERVICES_DOWN",
            "Host answers ICMP but management services are down. Prefer UART/log recovery over blind flash.",
        )
    return (
        "SSH_MANAGEMENT_INDETERMINATE",
        "Evidence is mixed. Preserve logs and use UART/read-only recovery verifier before disruptive action.",
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    key = Path(args.key).expanduser() if args.key else DEFAULT_KEY
    report: dict[str, Any] = {
        "schema": "openmitrastar.hgw500-ssh-management-diagnostic/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "user": args.user,
        "key": str(key),
        "read_only": True,
        "mutations": {
            "router_ram_writes": False,
            "router_flash_writes": False,
            "router_reboot": False,
            "bootenv": False,
            "default_known_hosts": False,
        },
    }
    report["ping"] = ping_probe(args.host, args.timeout)
    report["tcp"] = {
        "22": tcp_probe(args.host, 22, args.timeout),
        "80": tcp_probe(args.host, 80, args.timeout),
        "16667": tcp_probe(args.host, 16667, args.timeout),
    }
    report["getinfo"] = getinfo_probe(args.host, args.timeout)
    report["ssh_default_known_hosts"] = run_ssh_probe(
        args.host,
        args.user,
        key,
        args.timeout,
        isolated_known_hosts=False,
    )
    report["ssh_isolated_known_hosts"] = run_ssh_probe(
        args.host,
        args.user,
        key,
        args.timeout,
        isolated_known_hosts=True,
    )
    status, action = decide(report)
    report["status"] = status
    report["recommended_action"] = action
    report["physical_reboot_indicated"] = status == "MANAGEMENT_UNREACHABLE_PHYSICAL_RECOVERY_CANDIDATE"
    report["ssh_problem_is_auth_or_client_side"] = status in {
        "SSH_AUTH_REJECTED_MANAGEMENT_OK",
        "SSH_AUTH_REJECTED_HTTP_DOWN",
        "SSH_HOSTKEY_STALE_AND_AUTH_REJECTED",
        "SSH_OK_DEFAULT_KNOWN_HOSTS_STALE",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--user", default="root")
    parser.add_argument("--key", default=str(DEFAULT_KEY))
    parser.add_argument("--timeout", type=int, default=5)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()

    report = build_report(args)
    output_path = None
    if not args.no_write_report:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_root = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / f"{stamp}-READONLY"
        output_root = output_root.resolve()
        allowed = DEFAULT_OUTPUT_ROOT.resolve()
        if output_root != allowed and allowed not in output_root.parents:
            raise SystemExit(f"output-dir must stay under {allowed}")
        output_root.mkdir(parents=True, exist_ok=True)
        output_path = output_root / "ssh-management-diagnostic.json"
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["evidence_path"] = str(output_path)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        "OMHGW500_SSH_MGMT_DIAG_PASS=1 "
        f"status={report['status']} "
        f"physical_reboot={int(report['physical_reboot_indicated'])} "
        f"ssh_auth_or_client={int(report['ssh_problem_is_auth_or_client_side'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
