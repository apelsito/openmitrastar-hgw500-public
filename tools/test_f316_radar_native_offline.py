#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f316_radar_native/qtn_radar_native_f316_main.c"
OUT = ROOT / "outputs/kernel-port/f316-radar-native-20260905"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    text = SOURCE.read_text(encoding="ascii")
    for marker in (
        "authoritative_enable",
        "weather_enable",
        "f316_classifier_process",
        "f316_delivered_epoch != epoch",
        "cancel_delayed_work(&f315_poll_work)",
        "cancel_delayed_work_sync(&f315_poll_work)",
    ):
        assert marker in text
    assert "qdrv_radar_detected" not in text
    assert "mark_radar" not in text
    subprocess.run(
        [sys.executable, str(ROOT / "tools/test_f316_classifier_offline.py")],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_f316_radar_native_offline.py"), "--replace-existing"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "ACTIVE_CAPABLE_PROVIDER_AUTHORITY_DEFAULT_OFF"
    assert manifest["runtime_defaults"]["authoritative_enable"] is False
    assert manifest["runtime_defaults"]["weather_enable"] is False
    assert manifest["qdrv"]["external_provider_link"] == "PASS"
    assert len(manifest["provider"]["exports"]) == 18
    for line in (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(OUT / name) == expected
    print("F316 native provider offline tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
