#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/kernel-port/f316-radar-classifier-20260905"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_f316_classifier_offline.py"), "--replace-existing"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["authority"] == {
        "authoritative": False,
        "callback_allowed": False,
        "dfs_tx_authorized": False,
        "physical_vectors": False,
    }
    assert manifest["lanes"]["unified_long_run"] == "PASS_100_BATCHES"
    assert manifest["lanes"]["candidate_selector"] == "PASS_DATA_DRIVEN_ROUTE"
    assert manifest["lanes"]["weather"] == "FAIL_CLOSED_PENDING_PHYSICAL_VECTORS"
    assert manifest["artifact"]["bytes"] < 32 * 1024
    assert digest(OUT / manifest["artifact"]["file"]) == manifest["artifact"]["sha256"]
    for line in (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert digest(OUT / name) == expected
    print("F316 classifier offline tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
