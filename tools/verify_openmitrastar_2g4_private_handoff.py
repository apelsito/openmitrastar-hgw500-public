#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "artifacts/kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin": "900282bd7e31607d86ccf040c89967371af3884a2089e7d405e7b5301d848c48",
    "artifacts/modules/rtl_pci.ko": "e572839c296703732cd26171901dd481d6baed7fdcdd610c46d4f422499531ab",
    "artifacts/modules/rtl8192ee.ko": "8ebda96ee35ffc0aa51838dd3fef32581b679b6f36c807b00be56df4a00d77e7",
    "artifacts/firmware/rtlwifi/rtl8192eefw.bin": "c6e5beeeb2a716ce417a9ede5974d0876b18ebf0368c195da8a181f6ba6d9b4b",
    "artifacts/firmware/regulatory.db": "e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393",
    "artifacts/ap/openmitrastar-realtek-ap-RAM-ONLY-NO-FLASH.tar": "2f79e625dbc7c1400f245159fd99797fbd0f7fd780d8138ae48b69d4320f19b6",
}
PSK = re.compile(
    r"(?im)^\s*(?:wpa_passphrase|wpa_psk|psk|sae_password|passphrase)\s*=\s*"
    r"(?!__RUNTIME_|\$|@|\{|<|re\.compile\b|none\b|false\b|true\b)[^\s#]{8,}"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    checked = 0
    for line in (ROOT / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"manifest failure: {relative}")
        checked += 1
    for relative, expected in EXPECTED.items():
        if sha256(ROOT / relative) != expected:
            raise SystemExit(f"pinned artifact mismatch: {relative}")
    for directory, minimum in (
        ("src/linux-5.10/drivers/net/wireless/realtek/rtlwifi", 100),
        ("src/linux-5.10/net/mac80211", 80),
        ("src/linux-5.10/net/wireless", 40),
    ):
        count = sum(1 for p in (ROOT / directory).rglob("*") if p.is_file())
        if count < minimum:
            raise SystemExit(f"source set incomplete: {directory} files={count}")
    migration = (ROOT / "MIGRATION_TARGET_2G4.md").read_text(encoding="utf-8")
    for marker in (
        "OEM/origen",
        "Linux 5.10",
        "V5",
        "iATU",
        "AP",
        "bridge",
        "runtime pendiente",
    ):
        if marker not in migration:
            raise SystemExit(f"migration marker missing: {marker}")
    evidence = (ROOT / "evidence/v5-ap-lifecycle.log").read_text(encoding="utf-8")
    if "reason=managed-deferred" not in evidence or "nobody cared" in evidence:
        raise SystemExit("V5 evidence contract failed")
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {
            ".md", ".txt", ".log", ".json", ".c", ".h", ".patch", ".sh", ".py", ".conf", ".in"
        }:
            continue
        if PSK.search(path.read_text(encoding="utf-8", errors="replace")):
            raise SystemExit(f"concrete PSK found: {path.relative_to(ROOT)}")
    ap_tar = ROOT / "artifacts/ap/openmitrastar-realtek-ap-RAM-ONLY-NO-FLASH.tar"
    with tarfile.open(ap_tar, "r") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.size > 2_000_000:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            blob = extracted.read()
            if b"\0" not in blob[:4096] and PSK.search(blob.decode("utf-8", errors="replace")):
                raise SystemExit(f"concrete PSK in AP tar: {member.name}")
    if "SECRET_SCAN=PASS" not in (ROOT / "SECRET_SCAN.txt").read_text(encoding="utf-8"):
        raise SystemExit("secret scan failed")
    print(
        f"PRIVATE_2G4_HANDOFF_VERIFY_PASS files={checked} "
        f"kernel={EXPECTED['artifacts/kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin']} "
        f"rtl_pci={EXPECTED['artifacts/modules/rtl_pci.ko']} ap_runtime=pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
