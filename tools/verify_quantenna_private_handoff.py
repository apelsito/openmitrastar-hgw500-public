#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


FW = {
    "auc_driver.nomu.0.bin": "c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6",
    "auc_driver.default.0.bin": "e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af",
    "qtn_driver.qtn_ruby.0.bin": "71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4",
    "rdsp_driver.0.bin": "87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    count = 0
    for line in (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"manifest failure: {relative}")
        count += 1
    for name, expected in FW.items():
        path = root / "private/proprietary-firmware-v37.4.0.89" / name
        if sha256(path) != expected:
            raise SystemExit(f"firmware mismatch: {name}")
    modules = list((root / "artifacts/linux510-modules/extra/quantenna").rglob("*.ko"))
    if len(modules) != 22:
        raise SystemExit(f"expected 22 Linux 5.10 modules, found {len(modules)}")
    target = (root / "MIGRATION_TARGET_5G.md").read_text(encoding="utf-8")
    for marker in (
        "TARGET_HOST_ABI=0x25040059",
        "W3_PAIR_APPROVED=0",
        "shared_params: 384 -> 400",
        "STOP before HBM/MMIO",
    ):
        if marker not in target:
            raise SystemExit(f"migration marker missing: {marker}")
    scan = (root / "SECRET_SCAN.txt").read_text(encoding="utf-8")
    if "SECRET_SCAN=PASS" not in scan:
        raise SystemExit("secret scan did not pass")
    forbidden_names = re.compile(
        r"(?i)(mtdblock|full[_-]?flash|firmware[_-]?dump|accesos|romfile|pdetector|tx_power_|\.cal$|id_rsa|private[_-]?key)"
    )
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and forbidden_names.search(rel) and not rel.startswith("src/oem-gpl/"):
            raise SystemExit(f"forbidden artifact: {path.relative_to(root)}")
    print(f"QUANTENNA_PRIVATE_HANDOFF_VERIFY_PASS files={count} modules=22 firmware=4 runtime_approved=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
