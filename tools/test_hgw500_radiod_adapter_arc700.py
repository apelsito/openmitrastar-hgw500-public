#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/userland/hgw500-radiod-adapter-arc700-20260905"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "tools/test_lyoko_radiod_hgw500_adapter.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "tools/build_hgw500_radiod_adapter_arc700.py"), "--replace-existing"], cwd=ROOT, check=True)
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["binary"]["static"] is True
    assert manifest["binary"]["bytes"] < 160 * 1024
    assert all(value is False for key, value in manifest["contract"].items() if key != "snapshot_only")
    assert manifest["contract"]["snapshot_only"] is True
    assert digest(OUT / manifest["binary"]["file"]) == manifest["binary"]["sha256"]
    print("HGW500 radiod adapter ARC700 tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
