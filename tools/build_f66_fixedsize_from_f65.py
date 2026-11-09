#!/usr/bin/env python3
"""Build an offline F66 autorate/reclaim candidate by fixed-size patching F65's initramfs.

This is intentionally an offline image recomposer. It does not open UART, touch
the router, start TFTP, or write flash. The only runtime change is replacing the
2.4 GHz module loader script already embedded in F65 with a compact autorate
reclaim-poll variant padded to the exact original byte span.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f65/build"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/build"
BASE_IN = "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH"
BASE_OUT = "openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH"
OLD_LOADER = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules"
F66_LOADER = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/prep/om-radio-modules"
TEMPLATE = ROOT / "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
BOOTBASE = ROOT / "tools/bootbase_contract_emulator.py"
LEGACY_LZMA = ROOT / "work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
PARTS_DIR = ROOT / "hgw500bna-qcv2-firmware-dump-verified"

UIMAGE_MAGIC = 0x27051956
UIMAGE_HEADER = 64
RAS_OFFSET = 0x2000
SLOT_BYTES = 7_995_392


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def parse_uimage_header(blob: bytes) -> list[int | bytes]:
    if len(blob) < UIMAGE_HEADER:
        raise SystemExit("uImage too short")
    values = list(struct.unpack(">7I4B32s", blob[:UIMAGE_HEADER]))
    if values[0] != UIMAGE_MAGIC:
        raise SystemExit("bad uImage magic")
    header = bytearray(blob[:UIMAGE_HEADER])
    header[4:8] = b"\0\0\0\0"
    if zlib.crc32(header) & 0xFFFFFFFF != values[1]:
        raise SystemExit("uImage header CRC mismatch")
    return values


def write_uimage(source_uimage: Path, raw: bytes, out: Path, compression: int) -> None:
    source = source_uimage.read_bytes()
    values = parse_uimage_header(source)
    values[1] = 0
    values[3] = len(raw)
    values[6] = zlib.crc32(raw) & 0xFFFFFFFF
    values[10] = compression
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    out.write_bytes(struct.pack(">7I4B32s", *values) + raw)


def write_webformat(uimage: Path, out: Path) -> None:
    source = uimage.read_bytes()
    values = parse_uimage_header(source)
    payload_size = int(values[3])
    if len(source) != UIMAGE_HEADER + payload_size:
        raise SystemExit("uImage size does not match header")
    payload = source[UIMAGE_HEADER:]
    image = bytearray(TEMPLATE.read_bytes()[:RAS_OFFSET])
    image.extend(payload)
    values[1] = 0
    values[3] = len(payload)
    values[6] = zlib.crc32(payload) & 0xFFFFFFFF
    values[8] = 0x13
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    image[:UIMAGE_HEADER] = struct.pack(">7I4B32s", *values)
    out.write_bytes(image)


def compact_loader(text: str) -> str:
    lines: list[str] = []
    for index, raw_line in enumerate(text.splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and index != 0:
            continue
        if stripped == "profile=all64-autorate-eapol-mgntq-reclaim":
            lines.append(stripped)
            continue
        lines.append(raw_line.rstrip())
    compact = "\n".join(lines) + "\n"
    # Keep the full profile string once for offline tests, but shorten runtime
    # telemetry elsewhere to fit inside the F65 script span.
    first = True
    out_lines: list[str] = []
    for line in compact.splitlines():
        if "profile=all64-autorate-eapol-mgntq-reclaim" in line:
            if first:
                first = False
            else:
                line = line.replace("profile=all64-autorate-eapol-mgntq-reclaim", "profile=autorate-reclaim")
        if " eapol_param_source=insmod optional_missing=warn" in line:
            line = line.replace(" eapol_param_source=insmod optional_missing=warn", "")
        if " order=ctr,ccm,cmac,cfg80211,libarc4,mac80211,rtlwifi,btcoexist,rtl_pci,rtl8192ee" in line:
            line = line.replace(" order=ctr,ccm,cmac,cfg80211,libarc4,mac80211,rtlwifi,btcoexist,rtl_pci,rtl8192ee", "")
        out_lines.append(line)
    return "\n".join(out_lines) + "\n"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix()[3:]
    return f"/mnt/{drive}/{rest}"


def encode_lzma_legacy(raw_path: Path) -> bytes:
    if not LEGACY_LZMA.is_file():
        raise SystemExit(f"missing legacy lzma encoder: {LEGACY_LZMA}")
    proc = subprocess.run(
        [
            "wsl",
            "-d",
            "podman-openmitrastar-analysis",
            "--",
            wsl_path(LEGACY_LZMA),
            "--keep",
            "--best",
            wsl_path(raw_path),
            "-c",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.decode("utf-8", errors="replace") or "legacy lzma failed")
    return proc.stdout


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{BASE_IN}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{BASE_IN}.uncompressed.uImage"
    source_web = SRC_BUILD / f"{BASE_IN}.webformat.bin"
    source_config = SRC_BUILD / f"{BASE_IN}.config"
    for path in (source_raw, source_uncompressed, source_web, source_config, OLD_LOADER, F66_LOADER, TEMPLATE, LEGACY_LZMA):
        if not path.is_file():
            raise SystemExit(f"missing input: {path}")
    for index in range(6):
        part = PARTS_DIR / f"hgw500_mtdblock{index}.bin"
        if not part.is_file():
            raise SystemExit(f"missing input: {part}")

    raw = bytearray(source_raw.read_bytes())
    old = OLD_LOADER.read_bytes()
    compact = compact_loader(F66_LOADER.read_text(encoding="utf-8")).encode("utf-8")
    count = raw.count(old)
    if count != 1:
        raise SystemExit(f"expected one old loader occurrence in F65, found {count}")
    if len(compact) > len(old):
        raise SystemExit(f"compact F66 loader is {len(compact)} bytes, old span is {len(old)}")

    offset = raw.index(old)
    raw[offset : offset + len(old)] = compact + (b"\0" * (len(old) - len(compact)))

    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    compact_loader_path = OUT / "om-radio-modules.fixedsize"
    report_path = OUT / "f66-fixed-size-patch-report.json"
    manifest_path = OUT / "manifest.json"
    contract_path = OUT / "bootbase-contract.json"

    compact_loader_path.write_bytes(compact)
    shutil.copy2(source_config, config_path)
    raw_path.write_bytes(raw)
    write_uimage(source_uncompressed, bytes(raw), uncompressed_path, compression=0)

    encoded = encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != bytes(raw):
        raise SystemExit("LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    write_webformat(uimage_path, web_path)

    if len(web_path.read_bytes()) > SLOT_BYTES:
        raise SystemExit("webformat exceeds linux_live slot")

    contract = subprocess.run(
        [
            sys.executable,
            str(BOOTBASE),
            "--candidate-slot",
            str(web_path),
            "--candidate-name",
            "linux_live-f66-autorate-reclaim-fixedsize",
            "--parts-dir",
            str(PARTS_DIR),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if contract.returncode != 0:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path.write_text(contract.stdout, encoding="utf-8")
    contract_json = json.loads(contract.stdout)

    report = {
        "schema": "openmitrastar.f66-fixed-size-initramfs-patch/v1",
        "source": "F65",
        "changed_file": "usr/sbin/om-radio-modules",
        "old_loader_size": len(old),
        "compact_loader_size": len(compact),
        "padding_bytes": len(old) - len(compact),
        "loader_offset": f"0x{offset:x}",
        "loader_sha256": sha256(compact),
        "initramfs_sha256": sha256(bytes(raw)),
        "uncompressed_uimage_sha256": sha256(uncompressed_path.read_bytes()),
        "webformat_sha256": sha256(web_path.read_bytes()),
        "webformat_crc32": crc32(web_path.read_bytes()),
        "bootbase_contract": contract_json.get("result"),
        "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract"),
        "markers": {
            "queue_guard": b"hgw500_tx_queue_guard=1" in compact,
            "queue_guard_disabled": b"hgw500_tx_queue_guard=N" in compact,
            "queue_guard_high_16": b"hgw500_tx_queue_guard_high=16" in compact,
            "queue_guard_low_8": b"hgw500_tx_queue_guard_low=8" in compact,
            "reclaim_poll": b"hgw500_tx_reclaim_poll=1" in compact,
            "autorate": b"hgw500_force_data_mcs7=0" in compact and b"hgw500_force_data_mcs7=Y" not in compact,
            "mcs7": b"hgw500_force_data_mcs7=1" in compact or b"hgw500_force_data_mcs7=Y" in compact,
            "be_data_split": b"hgw500_txbd_be_data_split=1" in compact,
        },
        "hardware_actions": False,
        "flash_supported": False,
        "runtime_gates": {
            "boot": "pending-flash",
            "realtek_2g_autostart": "pending-flash",
            "ssh": "pending-flash",
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")

    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f66/v1",
        "classification": "F66_FIXED_SIZE_FROM_F65_2G_AUTORATE_RECLAIM",
        "source": "q3-persistent-composite-f65",
        "artifacts": {
            "decompressed_payload": {"file": raw_path.name, "bytes": raw_path.stat().st_size, "sha256": sha256(raw_path.read_bytes())},
            "uncompressed_uimage": {"file": uncompressed_path.name, "bytes": uncompressed_path.stat().st_size, "sha256": sha256(uncompressed_path.read_bytes())},
            "lzma": {"file": lzma_path.name, "bytes": lzma_path.stat().st_size, "sha256": sha256(lzma_path.read_bytes())},
            "uimage": {"file": uimage_path.name, "bytes": uimage_path.stat().st_size, "sha256": sha256(uimage_path.read_bytes())},
            "webformat": {"file": web_path.name, "bytes": web_path.stat().st_size, "sha256": sha256(web_path.read_bytes()), "crc32": crc32(web_path.read_bytes())},
            "kconfig": {"file": config_path.name, "bytes": config_path.stat().st_size, "sha256": sha256(config_path.read_bytes())},
        },
        "slot": {"name": "linux_live", "bytes": SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": web_path.stat().st_size <= SLOT_BYTES},
        "bootbase_contract": {"file": contract_path.name, "result": contract_json.get("result"), "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract")},
        "runtime_gates": report["runtime_gates"],
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sha256sum_paths = (
        contract_path,
        report_path,
        manifest_path,
        compact_loader_path,
        config_path,
        raw_path,
        lzma_path,
        uimage_path,
        uncompressed_path,
        web_path,
    )
    with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted(sha256sum_paths, key=lambda item: item.name):
            fh.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")

    shutil.copy2(web_path, ROOT / "work/tftp/omvl" / web_path.name)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
