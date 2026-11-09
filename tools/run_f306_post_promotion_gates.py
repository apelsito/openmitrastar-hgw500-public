#!/usr/bin/env python3
"""Run F306 multicast, store and VLAN gates sequentially after promotion."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import f306_post_promotion_common as common


ROOT = common.ROOT
ACK = "OPENMITRASTAR_F306_POST_PROMOTION_GATES"
PLAN_SCHEMA = "openmitrastar.f306-post-promotion-gates-plan/v1"
RESULT_SCHEMA = "openmitrastar.f306-post-promotion-gates/v1"
GATES = ("multicast-igmp", "store-protection", "vlan4090")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def candidate_path() -> Path:
    manifest = common.read_json(common.MANIFEST)
    artifact = manifest.get("artifacts", {}).get("webformat", {})
    if not isinstance(artifact, dict):
        raise RuntimeError("F306 manifest webformat entry is invalid")
    return common.BUILD / str(artifact.get("file") or "")


def local_preflight() -> dict[str, Any]:
    manifest = common.read_json(common.MANIFEST)
    artifact = manifest.get("artifacts", {}).get("webformat", {})
    candidate = candidate_path()
    scripts = {
        "multicast-igmp": ROOT / "tools/run_f306_multicast_igmp_physical.py",
        "store-protection": ROOT / "tools/f306_store_protection_probe.ps1",
        "vlan4090": ROOT / "tools/f306_vlan_gate.py",
    }
    checks = {
        "manifest_schema": manifest.get("schema") == "openmitrastar.f306-unified-product-candidate/v1",
        "candidate_present": candidate.is_file(),
        "candidate_sha256": candidate.is_file() and sha256_file(candidate) == common.EXPECTED_SHA256,
        "manifest_sha256": isinstance(artifact, dict) and artifact.get("sha256") == common.EXPECTED_SHA256,
        "known_hosts_f306": common.KNOWN_HOSTS.is_file(),
        "aelita_known_hosts": common.AELITA_KNOWN_HOSTS.is_file(),
        **{f"script_{name}": path.is_file() for name, path in scripts.items()},
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "candidate_file": candidate.name,
        "candidate_sha256": sha256_file(candidate) if candidate.is_file() else "",
        "scripts": {name: str(path.relative_to(ROOT)) for name, path in scripts.items()},
    }


def child_command(name: str, args: argparse.Namespace, output_dir: Path, execute: bool) -> list[str]:
    if name == "multicast-igmp":
        command = [
            sys.executable,
            str(ROOT / "tools/run_f306_multicast_igmp_physical.py"),
            "--router-host", args.router_host,
            "--oracle-host", args.oracle_host,
            "--oracle-user", args.oracle_user,
            "--controller-ip", args.controller_ip,
            "--aelita-known-hosts", str(common.AELITA_KNOWN_HOSTS),
            "--aelita-host-key-mode", "pinned",
            "--output-dir", str(output_dir),
        ]
        if execute:
            command.extend(("--execute", "--ack", "OPENMITRASTAR_F306_MULTICAST_IGMP_PHYSICAL"))
        return command
    if name == "store-protection":
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "tools/f306_store_protection_probe.ps1"),
            "-RouterHost", args.router_host,
            "-Port", args.port,
            "-OutputDir", str(output_dir),
        ]
        if execute:
            command.extend(("-Execute", "-Ack", "OPENMITRASTAR_F306_STORE_PROTECTION_READONLY_2F00A2DB"))
        return command
    if name == "vlan4090":
        command = [
            sys.executable,
            str(ROOT / "tools/f306_vlan_gate.py"),
            "--router-host", args.router_host,
            "--oracle-host", args.oracle_host,
            "--oracle-user", args.oracle_user,
            "--aelita-known-hosts", str(common.AELITA_KNOWN_HOSTS),
            "--aelita-host-key-mode", "pinned",
            "--output-dir", str(output_dir),
        ]
        if args.controller_interface:
            command.extend(("--controller-interface", args.controller_interface))
        if execute:
            command.extend(("--execute", "--ack", "OPENMITRASTAR_F306_VLAN4090_PHYSICAL"))
        return command
    raise ValueError(f"unknown gate: {name}")


def run_child(name: str, command: list[str], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    started = utcnow()
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1800,
        check=False,
    )
    (output_dir / "coordinator.log").write_text(proc.stdout, encoding="utf-8")
    result_path = output_dir / "result.json"
    payload: dict[str, Any] = {}
    if result_path.is_file():
        try:
            payload = common.read_json(result_path)
        except Exception as exc:
            payload = {"status": "INVALID", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "name": name,
        "started_at": started.isoformat(),
        "finished_at": utcnow().isoformat(),
        "returncode": proc.returncode,
        "status": payload.get("status", "PASS" if proc.returncode == 0 else "FAIL"),
        "evidence_dir": str(output_dir),
        "result_file": str(result_path) if result_path.is_file() else "",
        "pass": proc.returncode == 0 and (not payload or payload.get("status") == "PASS"),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--ack", default="")
    result.add_argument("--router-host", default="192.168.1.90")
    result.add_argument("--oracle-host", default="192.168.1.63")
    result.add_argument("--oracle-user", default="AELITA")
    result.add_argument("--controller-ip", default="192.168.1.43")
    result.add_argument("--controller-interface", default="")
    result.add_argument("--port", default="COM3")
    result.add_argument("--output-dir", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.output_dir is None:
        prefix = "certification" if args.execute else "preflight"
        args.output_dir = ROOT / f"outputs/{prefix}/f306-post-promotion-{utcnow():%Y%m%dT%H%M%SZ}"
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("refusing to overwrite existing F306 post-promotion evidence")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    preflight = local_preflight()
    soak = common.active_soak_evidence()
    execute_allowed = bool(preflight["ready"] and common.soak_guard_clear(soak))
    plan = {
        "schema": PLAN_SCHEMA,
        "generated_at": utcnow().isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "required_firmware": common.EXPECTED_VERSION,
        "candidate_sha256": common.EXPECTED_SHA256,
        "local_preflight": preflight,
        "soak_guard": soak,
        "shared_physical_lock": str(common.LOCK_DIR),
        "ssh_policy": "v2-pinned",
        "gate_order": list(GATES),
        "fail_fast": True,
        "execute_allowed_now": execute_allowed,
        "hardware_actions_performed": False,
        "persistent_writes": False,
        "mtd_writes": False,
        "flash": False,
    }
    atomic_write_json(args.output_dir / "plan.json", plan)

    if not args.execute:
        children = []
        for name in GATES:
            child_dir = args.output_dir / name
            children.append(run_child(name, child_command(name, args, child_dir, False), child_dir))
        plan["child_preflights"] = children
        plan["child_preflights_pass"] = all(item["returncode"] == 0 for item in children)
        atomic_write_json(args.output_dir / "plan.json", plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0 if preflight["ready"] and plan["child_preflights_pass"] else 1

    if args.ack != ACK:
        raise SystemExit("exact --ack is required")
    if not execute_allowed:
        atomic_write_json(
            args.output_dir / "blocked.json",
            {
                "schema": RESULT_SCHEMA,
                "status": "BLOCKED",
                "phase": "soak-or-lock-exclusion",
                "soak_guard": soak,
                "hardware_actions_performed": False,
            },
        )
        return 2

    gates: list[dict[str, Any]] = []
    status = "PASS"
    failed_gate = ""
    for name in GATES:
        current = common.active_soak_evidence()
        if not common.soak_guard_clear(current):
            status = "BLOCKED"
            failed_gate = name
            gates.append({"name": name, "status": "BLOCKED", "pass": False, "soak_guard": current})
            break
        child_dir = args.output_dir / name
        outcome = run_child(name, child_command(name, args, child_dir, True), child_dir)
        gates.append(outcome)
        if not outcome["pass"]:
            status = "FAIL"
            failed_gate = name
            break

    result = {
        "schema": RESULT_SCHEMA,
        "generated_at": utcnow().isoformat(),
        "status": status,
        "failed_gate": failed_gate,
        "gates": gates,
        "fail_fast": True,
        "firmware": common.EXPECTED_VERSION,
        "candidate_sha256": common.EXPECTED_SHA256,
        "persistent_writes": False,
        "mtd_writes": False,
        "flash": False,
    }
    atomic_write_json(args.output_dir / "result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

