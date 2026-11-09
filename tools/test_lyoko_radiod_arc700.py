#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_lyoko_radiod_arc700.py"
OUT = ROOT / "outputs/userland/lyoko-radiod-arc700-20260905"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "tools/test_lyoko_radiod.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(BUILDER), "--replace-existing"], cwd=ROOT, check=True)
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["binary"]["static"] is True
    assert manifest["binary"]["undefined_symbols"] == 0
    assert manifest["binary"]["bytes"] < 128 * 1024
    assert sha256(OUT / "lyoko-radiod") == manifest["binary"]["sha256"]
    for line in (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(OUT / name) == expected
    print("lyoko-radiod ARC700 build/tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
