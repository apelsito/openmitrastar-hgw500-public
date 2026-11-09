#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://192.168.1.90/lyoko-data/index.json"
EXPECTED_SCHEMA = "router-lyoko.static-data/v1"
EXPECTED_CLASSIFICATION = "STATIC-READONLY-RAM-OVERLAY-NO-FLASH"
STATIC_PREFIX = "rootfs/var/www/lyoko-data/"
REQUIRED_FALSE_SAFETY = (
    "device_write",
    "flash_write",
    "bootenv_write",
    "network_reconfigure",
    "module_mutation",
)
REQUIRED_STATIC_FILES = (
    "mission-truth.json",
    "goal-audit.json",
    "safe-mode.json",
    "control-policy.json",
    "aelita-memory.json",
    "aelita-dialogue.json",
    "evidence-bindings.json",
    "telemetry-contract.json",
    "event-taxonomy.json",
    "sector-map.json",
)


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def load_payload(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.input_json:
        path = Path(args.input_json)
        return json.loads(path.read_text(encoding="utf-8")), f"file:{path}"
    if args.stdin:
        return json.loads(sys.stdin.read()), "stdin"

    req = urllib.request.Request(
        args.url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "openmitrastar-router-lyoko-static-index-verifier/1",
        },
        method="GET",
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=args.timeout) as response:
        body = response.read(args.max_bytes + 1)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if len(body) > args.max_bytes:
            raise RuntimeError(f"response exceeded max bytes: {args.max_bytes}")
        return (
            json.loads(body.decode("utf-8")),
            f"url:{args.url} status={response.status} elapsed_ms={elapsed_ms}",
        )


def load_manifest_static_files(path: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("manifest.files must be an object")

    expected: dict[str, dict[str, Any]] = {}
    for rel, meta in files.items():
        if not isinstance(rel, str) or not rel.startswith(STATIC_PREFIX):
            continue
        name = rel[len(STATIC_PREFIX) :]
        if name == "index.json":
            continue
        if not isinstance(meta, dict):
            continue
        expected[name] = meta
    return expected


def valid_file_meta(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("bytes"), int)
        and value.get("bytes", 0) > 0
        and isinstance(value.get("sha256"), str)
        and len(value.get("sha256", "")) == 64
        and all(ch in "0123456789abcdef" for ch in value.get("sha256", ""))
    )


def validate(doc: dict[str, Any], *, manifest: Path | None) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("schema", doc.get("schema") == EXPECTED_SCHEMA, f"schema must be {EXPECTED_SCHEMA}"))
    checks.append(
        Check(
            "classification",
            doc.get("classification") == EXPECTED_CLASSIFICATION,
            f"classification must be {EXPECTED_CLASSIFICATION}",
        )
    )

    safety = doc.get("safety")
    checks.append(Check("safety.object", isinstance(safety, dict), "safety must be an object"))
    if isinstance(safety, dict):
        for field in REQUIRED_FALSE_SAFETY:
            checks.append(
                Check(
                    f"safety.{field}.false",
                    safety.get(field) is False,
                    f"safety.{field} must be false",
                )
            )

    files = doc.get("files")
    checks.append(Check("files.object", isinstance(files, dict) and bool(files), "files must be a non-empty object"))
    if isinstance(files, dict):
        for name in REQUIRED_STATIC_FILES:
            checks.append(Check(f"files.{name}.present", name in files, f"{name} must be listed"))
        for name, meta in files.items():
            checks.append(Check(f"files.{name}.meta", valid_file_meta(meta), f"{name} must expose positive bytes and lowercase sha256"))

    if manifest is not None:
        expected = load_manifest_static_files(manifest)
        checks.append(Check("manifest.static_files", bool(expected), "manifest must list static lyoko-data files"))
        if isinstance(files, dict):
            for name, meta in expected.items():
                checks.append(Check(f"manifest.{name}.listed", name in files, f"{name} from manifest must be listed in index"))
                if name in files and valid_file_meta(files[name]):
                    checks.append(
                        Check(
                            f"manifest.{name}.bytes",
                            files[name].get("bytes") == meta.get("bytes"),
                            f"{name} bytes must match manifest",
                        )
                    )
                    checks.append(
                        Check(
                            f"manifest.{name}.sha256",
                            files[name].get("sha256") == meta.get("sha256"),
                            f"{name} sha256 must match manifest",
                        )
                    )
            extra = sorted(set(files) - set(expected))
            checks.append(Check("manifest.no_extra_index_files", not extra, f"index must not list files absent from manifest: {extra}"))

    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only verifier for Router-Lyoko static lyoko-data index.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", default=DEFAULT_URL)
    source.add_argument("--input-json")
    source.add_argument("--stdin", action="store_true")
    parser.add_argument("--manifest", type=Path, help="Local overlay manifest to compare static file bytes/SHA256.")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        doc, source = load_payload(args)
        checks = validate(doc, manifest=args.manifest)
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-STATIC-INDEX-VERIFY-NO-CONTROL",
            "source": source,
            "manifest": str(args.manifest) if args.manifest else None,
            "checks": [asdict(check) for check in checks],
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-STATIC-INDEX-VERIFY-NO-CONTROL",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
