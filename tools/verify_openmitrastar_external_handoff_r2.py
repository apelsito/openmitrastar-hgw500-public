#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAM_SHA = "900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48"
RTL_PCI_SHA = "53bea265eb846f561e1c64f1ffd9216caa1116d8736ba9b05ef8e688d0fe1375"
RTL8192EE_SHA = "8ebda96ee35ffc0aa51838dd3fef32581b679b6f36c807b00be56df4a00d77e7"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    count = 0
    for line in (ROOT / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"manifest failure: {relative}")
        count += 1
    if sha256(ROOT / "artifacts/ram/linux510-radiohw-intx-irqchip-v2-webformat.bin") != RAM_SHA:
        raise SystemExit("RAM kernel mismatch")
    bundle = ROOT / "artifacts/realtek-intx-lifecycle-v3-final"
    if sha256(bundle / "modules/rtl_pci.ko") != RTL_PCI_SHA:
        raise SystemExit("rtl_pci v3 mismatch")
    if sha256(bundle / "modules/rtl8192ee.ko") != RTL8192EE_SHA:
        raise SystemExit("rtl8192ee mismatch")
    v1 = (ROOT / "evidence/v1-host-enable-rejected.log").read_text(encoding="utf-8")
    v2 = (ROOT / "evidence/v2-irqchip-too-early-rejected.log").read_text(encoding="utf-8")
    v3 = (ROOT / "evidence/v3-lifecycle-hardware-pass.log").read_text(encoding="utf-8")
    iatu = (ROOT / "evidence/iatu-disproven.log").read_text(encoding="utf-8")
    if "intb=0x100" not in v1 or "intb=0x100" not in v2:
        raise SystemExit("rejection evidence missing")
    for marker in (
        "irq-lifecycle-policy managed=1",
        "irq-line-hold where=request-legacy",
        "irq-line-release where=start-ready",
        "MONITOR_RX_PASS frames=10",
        "MONITOR_PROBE_TX_PASS frames=3",
    ):
        if marker not in v3:
            raise SystemExit(f"v3 marker missing: {marker}")
    if "inbound0" not in iatu or "cr2=0x00000000" not in iatu or "RP_EQUALS_WP=true" not in iatu:
        raise SystemExit("iATU refutation evidence missing")
    psk = re.compile(
        r"(?im)^\s*(?:wpa_passphrase|wpa_psk|psk|sae_password|passphrase)\s*=\s*"
        r"(?!re\.compile\b|none\b|false\b|true\b)[^\s#]{8,}"
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {
            ".md", ".txt", ".log", ".json", ".c", ".h", ".patch", ".sh", ".py"
        }:
            continue
        if psk.search(path.read_text(encoding="utf-8", errors="replace")):
            raise SystemExit(f"PSK-like assignment found: {path.relative_to(ROOT)}")
    if "SECRET_SCAN=PASS" not in (ROOT / "SECRET_SCAN.txt").read_text(encoding="utf-8"):
        raise SystemExit("secret scan did not pass")
    print(
        f"HANDOFF_R2_VERIFY_PASS files={count} ram={RAM_SHA} "
        f"rtl_pci={RTL_PCI_SHA} rtl8192ee={RTL8192EE_SHA} ap_addendum=pending-nonblocking"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
