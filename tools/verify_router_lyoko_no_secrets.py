#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_ROOT = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "rootfs" / "var" / "www"

SECRET_KEY_NAMES = (
    "wifi_default_key",
    "wpa_psk",
    "psk",
    "passphrase",
    "password",
    "passwd",
    "COOKIE_SESSION_KEY",
    "login_password",
    "tr069_Key",
    "AUTH_SECRET",
    "SECRET_ACCESS_KEY",
)

SAFE_VALUE_WORDS = {
    "",
    "false",
    "true",
    "null",
    "none",
    "n/a",
    "na",
    "blocked",
    "denied",
    "disabled",
    "redacted",
    "masked",
    "placeholder",
    "example",
    "dummy",
    "fake",
    "not_set",
    "unset",
    "observe_only",
}

SAFE_VALUE_FRAGMENTS = (
    "redacted",
    "masked",
    "placeholder",
    "example",
    "dummy",
    "fake",
    "not set",
    "not_set",
    "no secret",
    "no secrets",
    "without secret",
    "blocked",
    "disabled",
    "denied",
)

KEY_PATTERN = "|".join(re.escape(name) for name in sorted(SECRET_KEY_NAMES, key=len, reverse=True))
SECRET_ASSIGNMENT_RE = re.compile(
    rf"""
    (?<![A-Za-z0-9_])
    ['"]?
    (?P<key>{KEY_PATTERN})
    ['"]?
    (?![A-Za-z0-9_])
    \s*(?:=|:)\s*
    (?P<value>
        "(?:[^"\\]|\\.)*" |
        '(?:[^'\\]|\\.)*' |
        [^,\s#;\r\n][^,#;\r\n]*
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

PEM_SECRET_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?(?:PRIVATE KEY|CERTIFICATE)-----",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    path: str
    line: int
    key: str | None
    detail: str


def display_path(path: Path, base: Path | None) -> str:
    if base is not None:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def normalize_value(raw: str) -> str:
    value = raw.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def is_placeholder_mask(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    if stripped.startswith("${") and stripped.endswith("}"):
        return True
    if stripped.startswith("$") and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", stripped):
        return True
    if "<" in stripped and ">" in stripped:
        return True
    mask_chars = set("*xX._-")
    return set(stripped) <= mask_chars


def is_concrete_secret_value(raw: str) -> bool:
    value = normalize_value(raw)
    lowered = value.lower()
    if lowered in SAFE_VALUE_WORDS:
        return False
    if any(fragment in lowered for fragment in SAFE_VALUE_FRAGMENTS):
        return False
    if is_placeholder_mask(value):
        return False
    return True


def scan_file(path: Path, base: Path | None = None) -> list[SecretFinding]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return scan_text(text, display_path(path, base))


def scan_text(text: str, path_label: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if PEM_SECRET_RE.search(line):
            findings.append(
                SecretFinding(
                    kind="pem_secret_material",
                    path=path_label,
                    line=line_no,
                    key=None,
                    detail="PEM private-key/certificate marker is present",
                )
            )
        for match in SECRET_ASSIGNMENT_RE.finditer(line):
            raw_value = match.group("value")
            if not is_concrete_secret_value(raw_value):
                continue
            findings.append(
                SecretFinding(
                    kind="secret_assignment",
                    path=path_label,
                    line=line_no,
                    key=match.group("key"),
                    detail="sensitive key has a concrete value; value redacted",
                )
            )
    return findings


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(path)
    return files


def scan_paths(paths: list[Path], base: Path | None = None) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in iter_files(paths):
        findings.extend(scan_file(path, base=base))
    return findings


def assert_no_secrets(paths: list[Path], base: Path | None = None) -> None:
    findings = scan_paths(paths, base=base)
    if findings:
        summary = [
            {"kind": f.kind, "path": f.path, "line": f.line, "key": f.key}
            for f in findings[:10]
        ]
        raise RuntimeError(
            "Lyoko web overlay contains secret material; refusing to continue: "
            f"{json.dumps(summary, ensure_ascii=False)}"
        )


def build_report(web_root: Path) -> dict:
    web_root = web_root.resolve()
    files = iter_files([web_root])
    findings = scan_paths(files, base=web_root)
    return {
        "schema": "router-lyoko.no-secrets-scan/v1",
        "classification": "READONLY-WEB-SECRET-SCAN-NO-CONTROL",
        "ok": not findings,
        "web_root": str(web_root),
        "scanned_files": len(files),
        "findings_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "note": "Findings never include the secret value; only file, line and key are reported.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Router-Lyoko web/API overlay does not expose concrete secrets."
    )
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.web_root)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
