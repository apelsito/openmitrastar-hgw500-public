#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://192.168.1.90"
WEB_PREFIX = "rootfs/var/www/"
API_PREFIX = "rootfs/var/www/api/"


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_expected_files(manifest: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("manifest.files must be an object")

    expected: dict[str, dict[str, Any]] = {}
    for rel, meta in files.items():
        if not isinstance(rel, str) or not rel.startswith(WEB_PREFIX):
            continue
        if rel.startswith(API_PREFIX):
            continue
        if not isinstance(meta, dict):
            continue
        web_path = "/" + rel[len(WEB_PREFIX) :]
        expected[web_path] = meta
    return expected


def fetch_url(base_url: str, web_path: str, *, timeout: float, max_bytes: int) -> bytes:
    url = base_url.rstrip("/") + urllib.parse.quote(web_path, safe="/")
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "User-Agent": "openmitrastar-router-lyoko-served-files-verifier/1",
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


def validate(expected: dict[str, dict[str, Any]], actual: dict[str, bytes]) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("manifest.web_files", bool(expected), "manifest must list non-API web files"))
    for web_path, meta in sorted(expected.items()):
        checks.append(Check(f"served.{web_path}.present", web_path in actual, f"{web_path} must be readable"))
        if web_path not in actual:
            continue
        data = actual[web_path]
        checks.append(
            Check(
                f"served.{web_path}.bytes",
                len(data) == meta.get("bytes"),
                f"{web_path} bytes must match manifest",
            )
        )
        checks.append(
            Check(
                f"served.{web_path}.sha256",
                sha256_bytes(data) == meta.get("sha256"),
                f"{web_path} sha256 must match manifest",
            )
        )

    safe_mode_raw = actual.get("/lyoko-data/safe-mode.json")
    checks.append(
        Check(
            "served./lyoko-data/safe-mode.json.present_for_semantic_guard",
            safe_mode_raw is not None,
            "safe-mode.json must be served so the LAB console can use it as the recovery contract",
        )
    )
    if safe_mode_raw is not None:
        try:
            safe_mode = json.loads(safe_mode_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            safe_mode = None
        checks.append(
            Check(
                "served./lyoko-data/safe-mode.json.parse",
                isinstance(safe_mode, dict),
                "safe-mode.json must parse as JSON",
            )
        )
        if isinstance(safe_mode, dict):
            sequence = safe_mode.get("operator_sequence")
            checks.append(
                Check(
                    "served./lyoko-data/safe-mode.json.operator_sequence",
                    isinstance(sequence, list) and bool(sequence),
                    "safe-mode.json must expose operator_sequence",
                )
            )
            tx11_boot_step = None
            tx11_client_step = None
            if isinstance(sequence, list):
                tx11_boot_step = next(
                    (
                        step
                        for step in sequence
                        if isinstance(step, dict) and step.get("id") == "tx11-boot-evidence-collection-plan"
                    ),
                    None,
                )
                tx11_client_step = next(
                    (
                        step
                        for step in sequence
                        if isinstance(step, dict) and step.get("id") == "tx11-2g-client-gate-plan"
                    ),
                    None,
                )
            checks.append(
                Check(
                    "served./lyoko-data/safe-mode.json.tx11_boot_step",
                    isinstance(tx11_boot_step, dict),
                    "safe-mode.json must expose tx11-boot-evidence-collection-plan",
                )
            )
            checks.append(
                Check(
                    "served./lyoko-data/safe-mode.json.tx11_client_step",
                    isinstance(tx11_client_step, dict),
                    "safe-mode.json must expose tx11-2g-client-gate-plan",
                )
            )
            if isinstance(tx11_boot_step, dict):
                rendered = json.dumps(tx11_boot_step, ensure_ascii=False)
                checks.append(
                    Check(
                        "served./lyoko-data/safe-mode.json.tx11_requires_exact_boot",
                        tx11_boot_step.get("requires_exact_image_ram_boot") is True,
                        "TX11 boot evidence step must explicitly require the exact RAM image",
                    )
                )
                checks.append(
                    Check(
                        "served./lyoko-data/safe-mode.json.tx11_boot_collector_command",
                        "collect_w2_tx11_boot_evidence.ps1" in rendered
                        and "OPENMITRASTAR_COLLECT_TX11_BOOT_EVIDENCE_READONLY" in rendered
                        and "w2-tx11-green-boot-controls-boot-evidence-latest.json" in rendered,
                        "TX11 boot evidence step must display the read-only collector and output path",
                    )
                )
            if isinstance(tx11_client_step, dict):
                rendered = json.dumps(tx11_client_step, ensure_ascii=False)
                checks.append(
                    Check(
                        "served./lyoko-data/safe-mode.json.tx11_requires_boot_evidence_json",
                        tx11_client_step.get("requires_tx11_boot_evidence_json") is True,
                        "TX11 operator step must explicitly require boot evidence JSON",
                    )
                )
                checks.append(
                    Check(
                        "served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json",
                        "Tx11BootEvidenceJson" in rendered
                        and "w2-tx11-green-boot-controls-boot-evidence-latest.json" in rendered
                        and "OPENMITRASTAR_TX11_CLIENT_GATE_RAM_ONLY" in rendered,
                        "TX11 operator step must display -Tx11BootEvidenceJson and the exact RAM-only ACK",
                    )
                )
            safety = safe_mode.get("safety")
            checks.append(
                Check(
                    "served./lyoko-data/safe-mode.json.dashboard_no_exec",
                    isinstance(safety, dict) and safety.get("dashboard_executes_commands") is False,
                    "safe-mode.json must keep dashboard_executes_commands=false",
                )
            )

    lyoko_js = actual.get("/lyoko.js", b"").decode("utf-8", errors="replace")
    checks.append(
        Check(
            "served./lyoko.js.fetches_safe_mode_contract",
            "/lyoko-data/safe-mode.json" in lyoko_js and "renderSafeModeContract" in lyoko_js,
            "lyoko.js must fetch safe-mode.json and render the LAB console from that contract",
        )
    )
    checks.append(
        Check(
            "served./lyoko.js.tx11_boot_evidence_guard_visible",
            "tx11_boot_evidence_json" in lyoko_js and "Tx11BootEvidenceJson" in lyoko_js and "w2-tx11-green-boot-controls-boot-evidence-latest.json" in lyoko_js,
            "lyoko.js must visibly guard the TX11 LAB step with Tx11BootEvidenceJson",
        )
    )
    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only verifier that served Router-Lyoko web/static files match the local overlay manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Local overlay manifest with expected bytes/SHA256.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"HTTP base URL (default: {DEFAULT_BASE_URL})")
    source.add_argument("--base-dir", type=Path, help="Local web root for offline tests.")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-file-bytes", type=int, default=512 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        expected = load_expected_files(args.manifest)
        actual: dict[str, bytes] = {}
        read_errors: dict[str, str] = {}
        started = time.monotonic()
        for web_path in expected:
            try:
                if args.base_dir:
                    actual[web_path] = read_base_dir(args.base_dir, web_path, max_bytes=args.max_file_bytes)
                else:
                    actual[web_path] = fetch_url(
                        args.base_url,
                        web_path,
                        timeout=args.timeout,
                        max_bytes=args.max_file_bytes,
                    )
            except (OSError, urllib.error.URLError, RuntimeError) as exc:
                read_errors[web_path] = str(exc)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        checks = validate(expected, actual)
        for web_path, error in sorted(read_errors.items()):
            checks.append(Check(f"served.{web_path}.read_error", False, error))
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
            "source": f"dir:{args.base_dir}" if args.base_dir else f"url:{args.base_url}",
            "manifest": str(args.manifest),
            "elapsed_ms": elapsed_ms,
            "files_checked": len(expected),
            "checks": [asdict(check) for check in checks],
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
