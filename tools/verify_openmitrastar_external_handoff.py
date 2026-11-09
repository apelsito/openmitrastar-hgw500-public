#!/usr/bin/env python3
"""Verify an extracted OpenMitraStar external handoff without local workspace state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAM = ROOT / "artifacts/ram/linux510-radiohw-pci-probe-webformat.bin"
BUNDLE = ROOT / "artifacts/realtek-instrumented"
RAM_SHA256 = "ed1605ddd99b92c5b99851b26fe6a6b79d81692e919277191114ccef73bbbd16"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = ROOT / "MANIFEST.sha256"
    if not manifest.is_file():
        raise SystemExit("missing MANIFEST.sha256")
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing manifest entry: {relative}")
        observed = sha256(path)
        if observed != expected:
            raise SystemExit(f"hash mismatch: {relative}: {observed} != {expected}")
        checked += 1
    if RAM.stat().st_size != 3791872 or sha256(RAM) != RAM_SHA256:
        raise SystemExit("executed RAM image contract failed")
    instrumentation = json.loads(
        (BUNDLE / "instrumentation-manifest.json").read_text(encoding="utf-8")
    )
    for relative, spec in instrumentation["upload_artifacts"].items():
        path = BUNDLE / relative
        if path.stat().st_size != spec["bytes"] or sha256(path) != spec["sha256"]:
            raise SystemExit(f"instrumented module contract failed: {relative}")
    scan = (ROOT / "SECRET_SCAN.txt").read_text(encoding="utf-8")
    if "SECRET_SCAN=PASS" not in scan:
        raise SystemExit("secret scan did not pass")
    print(
        f"HANDOFF_VERIFY_PASS files={checked} ram_sha256={RAM_SHA256} "
        f"rtl_pci={instrumentation['upload_artifacts']['modules/rtl_pci.ko']['sha256']} "
        f"rtl8192ee={instrumentation['upload_artifacts']['modules/rtl8192ee.ko']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
