#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import verify_router_lyoko_no_secrets as no_secrets
from verify_router_lyoko_served_files import load_expected_files


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://192.168.1.90"
DEFAULT_MANIFEST = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "manifest.json"
DEFAULT_BASE_DIR = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "rootfs" / "var" / "www"
API_PATHS = ("/api/lyoko", "/api/lyoko-control")


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def fetch_url(base_url: str, web_path: str, *, timeout: float, max_bytes: int) -> bytes:
    url = base_url.rstrip("/") + urllib.parse.quote(web_path, safe="/")
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "openmitrastar-router-lyoko-served-no-secrets-verifier/1",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RuntimeError(f"{web_path} exceeded max bytes: {max_bytes}")
        return body


def read_base_dir(base_dir: Path, web_path: str, *, max_bytes: int) -> bytes:
    normalized = web_path.lstrip("/")
    path = (base_dir / Path(*normalized.split("/"))).resolve()
    base_resolved = base_dir.resolve()
    if base_resolved != path and base_resolved not in path.parents:
        raise RuntimeError(f"path escapes base directory: {web_path}")
    body = path.read_bytes()
    if len(body) > max_bytes:
        raise RuntimeError(f"{web_path} exceeded max bytes: {max_bytes}")
    return body


def served_paths(manifest: Path) -> list[str]:
    expected = load_expected_files(manifest)
    return list(API_PATHS) + sorted(expected)


def scan_payloads(payloads: dict[str, bytes]) -> tuple[list[Check], list[no_secrets.SecretFinding]]:
    checks: list[Check] = []
    findings: list[no_secrets.SecretFinding] = []
    checks.append(Check("served.payloads.present", bool(payloads), "at least one served payload must be scanned"))
    for web_path, body in sorted(payloads.items()):
        text = body.decode("utf-8", errors="ignore")
        file_findings = no_secrets.scan_text(text, web_path)
        findings.extend(file_findings)
        checks.append(
            Check(
                f"served_no_secrets.{web_path}",
                not file_findings,
                f"{web_path} must not expose concrete secrets",
            )
        )
    return checks, findings


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paths = served_paths(args.manifest)
    payloads: dict[str, bytes] = {}
    read_errors: dict[str, str] = {}
    started = time.monotonic()
    for web_path in paths:
        try:
            if args.base_dir:
                payloads[web_path] = read_base_dir(args.base_dir, web_path, max_bytes=args.max_file_bytes)
            else:
                payloads[web_path] = fetch_url(
                    args.base_url,
                    web_path,
                    timeout=args.timeout,
                    max_bytes=args.max_file_bytes,
                )
        except (OSError, urllib.error.URLError, RuntimeError) as exc:
            read_errors[web_path] = str(exc)
    checks, findings = scan_payloads(payloads)
    for web_path, error in sorted(read_errors.items()):
        checks.append(Check(f"served_no_secrets.{web_path}.read_error", False, error))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": all(check.ok for check in checks),
        "classification": "READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
        "source": f"dir:{args.base_dir}" if args.base_dir else f"url:{args.base_url}",
        "manifest": str(args.manifest),
        "elapsed_ms": elapsed_ms,
        "payloads_scanned": len(payloads),
        "findings_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "checks": [asdict(check) for check in checks],
        "note": "Findings never include the secret value; only path, line and key are reported.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only verifier that served Router-Lyoko web/API responses expose no concrete secrets."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"HTTP base URL (default: {DEFAULT_BASE_URL})")
    source.add_argument("--base-dir", type=Path, help="Local web root for offline tests.")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-file-bytes", type=int, default=512 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
