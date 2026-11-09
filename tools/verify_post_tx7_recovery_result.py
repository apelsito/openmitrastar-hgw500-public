#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import verify_router_lyoko_no_secrets as no_secrets


EXPECTED_SCHEMA = "openmitrastar.post-tx7-recovery-result/v1"
EXPECTED_PASS_STATUS = "RECOVERY_PROVEN_READONLY"
EXPECTED_FAIL_STATUS = "RECOVERY_NOT_PROVEN"
KERNEL_PATTERN = re.compile(r"5\.10\.260-openmitrastar-radiohw")
ETH0_SECTION_PATTERN = re.compile(
    r"OMPOSTTX7_RECOVERY_ETH0_BEGIN\r?\n(?P<body>.*?)\r?\nOMPOSTTX7_RECOVERY_ETH0_END",
    re.DOTALL,
)
FATAL_PATTERN = re.compile(
    r"Kernel panic|Oops|BUG:|Unable to handle|EV_TLB|EV_ProtV|Misaligned Access|"
    r"Misaligned r/w|Invalid Read|Invalid Write|MuC:.*exception|MuC exception|"
    r"MuC has halted|forcing reboot",
    re.IGNORECASE,
)
PING_SUCCESS_PATTERN = re.compile(r"\bTTL=", re.IGNORECASE)
PING_FAILURE_PATTERN = re.compile(
    r"unreachable|timed out|inaccesible|agotado|error general|general failure",
    re.IGNORECASE,
)
EXPECTED_FALSE_MUTATIONS = (
    "uart_opened",
    "reboot",
    "bootenv",
    "mtd",
    "flash",
)


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return json.loads(raw.decode("utf-16"))
    return json.loads(raw.decode("utf-8-sig"))


def resolve_under(base: Path, candidate: Any) -> Path | None:
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def is_under(path: Path, base: Path) -> bool:
    base = base.resolve()
    path = path.resolve()
    return path == base or base in path.parents


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def eth0_section_proves_link(stdout: str) -> bool:
    match = ETH0_SECTION_PATTERN.search(stdout)
    if not match:
        return False
    lines = [line.strip() for line in match.group("body").splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    operstate, carrier, rx_packets, tx_packets = lines[:4]
    return (
        operstate in {"up", "unknown"}
        and carrier == "1"
        and bool(re.fullmatch(r"\d+", rx_packets))
        and bool(re.fullmatch(r"\d+", tx_packets))
    )


def ping_text_proves_reachability(ping_text: str, ping_exit: Any) -> bool:
    return (
        ping_exit == 0
        and bool(PING_SUCCESS_PATTERN.search(ping_text))
        and not bool(PING_FAILURE_PATTERN.search(ping_text))
    )


def scan_no_secrets(label: str, path: Path | None, output_dir: Path) -> Check:
    if path is None or str(path) == ".":
        return Check(f"{label}.no_secrets", False, f"{label} path is missing")
    if not path.is_file() or not is_under(path, output_dir):
        return Check(f"{label}.no_secrets", False, f"{label} must exist under output_dir before secret scan")
    findings = no_secrets.scan_text(read_text(path), label)
    return Check(
        f"{label}.no_secrets",
        not findings,
        f"{label} must not contain concrete secrets; findings={len(findings)}",
    )


def validate(result: dict[str, Any], *, result_path: Path, output_dir_arg: Path | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("schema", result.get("schema") == EXPECTED_SCHEMA, f"schema must be {EXPECTED_SCHEMA}"))

    evidence = result.get("evidence")
    checks.append(Check("evidence.object", isinstance(evidence, dict), "evidence must be an object"))
    evidence = evidence if isinstance(evidence, dict) else {}

    recorded_output_dir = resolve_under(result_path.parent, evidence.get("output_dir"))
    output_dir = (output_dir_arg.resolve() if output_dir_arg else recorded_output_dir) or result_path.parent.resolve()
    checks.append(Check("evidence.output_dir.present", recorded_output_dir is not None, "evidence.output_dir must be present"))
    if recorded_output_dir is not None:
        checks.append(Check("evidence.output_dir.exists", recorded_output_dir.is_dir(), "evidence.output_dir must exist"))
        if output_dir_arg is not None:
            checks.append(
                Check(
                    "evidence.output_dir.matches_arg",
                    recorded_output_dir == output_dir,
                    "recorded output_dir must match --output-dir",
                )
            )

    evidence_paths: dict[str, Path] = {}
    for key in ("ping", "ssh_stdout", "ssh_stderr", "result_json"):
        path = resolve_under(output_dir, evidence.get(key))
        evidence_paths[key] = path if path is not None else Path()
        checks.append(Check(f"evidence.{key}.present", path is not None, f"evidence.{key} must be present"))
        if path is None:
            continue
        checks.append(Check(f"evidence.{key}.under_output_dir", is_under(path, output_dir), f"{key} must stay under output_dir"))
        checks.append(Check(f"evidence.{key}.exists", path.is_file(), f"{key} must exist"))

    result_json_path = evidence_paths.get("result_json")
    if result_json_path and str(result_json_path) != ".":
        checks.append(
            Check(
                "evidence.result_json.self",
                result_json_path.resolve() == result_path.resolve(),
                "evidence.result_json must point to the validated result file",
            )
        )

    mutations = result.get("mutations")
    checks.append(Check("mutations.object", isinstance(mutations, dict), "mutations must be an object"))
    if isinstance(mutations, dict):
        for field in EXPECTED_FALSE_MUTATIONS:
            checks.append(Check(f"mutations.{field}.false", mutations.get(field) is False, f"{field} must be false"))

    ping_exit = result.get("ping_exit")
    ssh_exit = result.get("ssh_exit")
    ssh_marker = result.get("ssh_marker")
    kernel_ok = result.get("kernel_ok")
    eth0_ok = result.get("eth0_ok")
    fatal_found = result.get("fatal_found")
    checks.append(Check("ping_exit.int", isinstance(ping_exit, int), "ping_exit must be an integer"))
    checks.append(Check("ssh_exit.int", isinstance(ssh_exit, int), "ssh_exit must be an integer"))
    for key, value in (
        ("ssh_marker", ssh_marker),
        ("kernel_ok", kernel_ok),
        ("eth0_ok", eth0_ok),
        ("fatal_found", fatal_found),
        ("pass", result.get("pass")),
    ):
        checks.append(Check(f"{key}.bool", isinstance(value, bool), f"{key} must be a boolean"))

    stdout_text = ""
    stdout_path = evidence_paths.get("ssh_stdout")
    if stdout_path and stdout_path.is_file() and is_under(stdout_path, output_dir):
        stdout_text = read_text(stdout_path)
        checks.append(Check("ssh_stdout.readable", True, "ssh stdout is readable"))
    else:
        checks.append(Check("ssh_stdout.readable", False, "ssh stdout must exist under output_dir"))

    ping_text = ""
    ping_path = evidence_paths.get("ping")
    if ping_path and ping_path.is_file() and is_under(ping_path, output_dir):
        ping_text = read_text(ping_path)
        checks.append(Check("ping.readable", True, "ping output is readable"))
    else:
        checks.append(Check("ping.readable", False, "ping output must exist under output_dir"))

    checks.append(scan_no_secrets("ssh_stdout", stdout_path, output_dir))
    checks.append(scan_no_secrets("ssh_stderr", evidence_paths.get("ssh_stderr"), output_dir))

    computed_marker = "OMPOSTTX7_RECOVERY_BEGIN" in stdout_text and "OMPOSTTX7_RECOVERY_END" in stdout_text
    computed_kernel = bool(KERNEL_PATTERN.search(stdout_text))
    computed_eth0 = eth0_section_proves_link(stdout_text)
    computed_fatal = bool(FATAL_PATTERN.search(stdout_text))
    computed_ping = ping_text_proves_reachability(ping_text, ping_exit)
    ping_ok = result.get("ping_ok")

    checks.append(Check("ping_ok.bool", isinstance(ping_ok, bool), "ping_ok must be a boolean"))
    checks.append(Check("ping_ok.matches_ping_output", ping_ok == computed_ping, "ping_ok must match ping output content"))
    checks.append(Check("ssh_marker.matches_stdout", ssh_marker == computed_marker, "ssh_marker must match stdout markers"))
    checks.append(Check("kernel_ok.matches_stdout", kernel_ok == computed_kernel, "kernel_ok must match stdout kernel string"))
    checks.append(Check("eth0_ok.matches_stdout", eth0_ok == computed_eth0, "eth0_ok must match stdout eth0 section: operstate up/unknown, carrier 1, numeric rx/tx packets"))
    checks.append(Check("fatal_found.matches_stdout", fatal_found == computed_fatal, "fatal_found must match fatal pattern scan"))

    computed_pass = (
        computed_ping
        and ssh_exit == 0
        and computed_marker
        and computed_kernel
        and computed_eth0
        and not computed_fatal
    )
    declared_pass = result.get("pass")
    checks.append(Check("pass.matches_evidence", declared_pass == computed_pass, "pass must match ping/ssh/stdout/fatal evidence"))
    checks.append(
        Check(
            "status.matches_pass",
            (
                declared_pass is True
                and result.get("status") == EXPECTED_PASS_STATUS
            )
            or (
                declared_pass is False
                and result.get("status") == EXPECTED_FAIL_STATUS
            ),
            "status must be proven only for pass=true, otherwise not-proven",
        )
    )
    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate post-TX7 recovery-result.json against captured read-only evidence."
    )
    parser.add_argument("result_json", type=Path, help="Path to recovery-result.json")
    parser.add_argument("--output-dir", type=Path, help="Expected evidence output directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result_path = args.result_json.resolve()
    try:
        result = load_json(result_path)
        checks = validate(result, result_path=result_path, output_dir_arg=args.output_dir)
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-POST-TX7-RECOVERY-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "checks": [asdict(check) for check in checks],
            "note": "Findings never include the secret value; only evidence stream and count are reported.",
        }
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-POST-TX7-RECOVERY-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
