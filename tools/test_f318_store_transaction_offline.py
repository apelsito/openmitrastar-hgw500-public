#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/kernel-port/f318-store-transaction-core-20260905"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_f318_store_transaction_offline.py"), "--replace-existing"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "PORTABLE_OFFLINE_TWO_ERASEBLOCK_TRANSACTION_CORE"
    assert manifest["store"]["slot_offsets"] == ["0x00dc0000", "0x00dd0000"]
    assert manifest["store"]["remaining_store_blocks_untouched"] == 26
    assert manifest["transaction"]["global_protection_operation_available"] is False
    assert manifest["transaction"]["exact_target_protection_restore"] is True
    assert manifest["provider_boundary"]["hardware_provider"] == "NOT_IMPLEMENTED"
    assert manifest["authority"] == {
        "persistent_writes_enabled": False,
        "firmware_candidate_produced": False,
        "flash_supported": False,
    }
    artifact = OUT / manifest["artifact"]["file"]
    assert digest(artifact) == manifest["artifact"]["sha256"]
    for line in (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert digest(OUT / name) == expected
    print("F318 store transaction offline tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
