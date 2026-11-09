#!/usr/bin/env python3
"""Build a private F159-era HGW-500 handoff with stable drivers and two dumps."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f71_qcsapi_interp_from_f70 as cpio  # noqa: E402

NAME = "OpenMitraStar-HGW500-F159-Latest-Try-Full-Private-Handoff-20260831-v2"
OUT = ROOT / "handoff" / NAME
ZIP = OUT.with_suffix(".zip")

F150 = ROOT / "handoff" / "OpenMitraStar-HGW500-F150-Dual-Radio-Handoff-20260831"
F157_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f157-5g-persistent-bridge-from-f156/build"
F159_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f159-2g-rtlpci-historical-fast-from-f158/build"
OEM = ROOT / "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
OLD_DUMP = ROOT / "hgw500bna-qcv2-firmware-dump-verified.zip"
NEW_DUMP = ROOT / "outputs/flash-backups/f159-physical-new-dump-20260831T2359"
F157_EVIDENCE = ROOT / "outputs/f3-certification/qtn-5g-f157-persistent-v2-20260831-224613"
F159_EVIDENCE_DIRS = [
    ROOT / "outputs/f3-certification/realtek-2g-f159-historical-20260831-232641",
    ROOT / "outputs/f3-certification/realtek-2g-f159-wifi0-detached-20260831-233750",
]
F159_CLEAN_REBOOT_STATUS = ROOT / "outputs/postflash/f159-clean-reboot-ready-20260831-235907/status.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, relative: str) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def copy_tree(source: Path, relative: str) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    shutil.copytree(source, OUT / relative)


def one(pattern: str, parent: Path) -> Path:
    matches = list(parent.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {pattern} under {parent}, found {len(matches)}")
    return matches[0]


def extract_f159_drivers() -> dict[str, object]:
    raw = one("*.decompressed.bin", F159_BUILD).read_bytes()
    _, entries, _ = cpio.parse_first_cpio(raw)
    selected: list[cpio.CpioEntry] = []
    exact_runtime = {
        "etc/init.d/S55-radio5-ap",
        "usr/sbin/hostapd-qtn",
        "usr/sbin/om-radio2g-toggle",
        "usr/sbin/om-radio5-start",
        "usr/sbin/om-radio5-stop",
        "usr/sbin/om-radio5g-toggle",
        "usr/sbin/ram-insmod-qtn",
    }
    for entry in entries:
        if not stat.S_ISREG(entry.mode):
            continue
        if (
            "/openmitrastar/radio2g/" in entry.name
            or "/openmitrastar/radio5g/" in entry.name
            or entry.name.startswith("usr/share/openmitrastar/radio2g/")
            or entry.name.startswith("usr/share/openmitrastar/radio5g/")
            or entry.name.startswith("lib/firmware/rtlwifi/")
            or entry.name in {
                "lib/firmware/auc_driver.default.0.bin",
                "lib/firmware/auc_driver.nomu.0.bin",
                "lib/firmware/qtn_driver.qtn_ruby.0.bin",
                "lib/firmware/rdsp_driver.0.bin",
                "lib/firmware/regulatory.db",
            }
            or entry.name in exact_runtime
        ):
            selected.append(entry)
    if not any(e.name.endswith("radio2g/rtl_pci.ko") for e in selected):
        raise RuntimeError("F159 rtl_pci.ko missing")
    if not any(e.name.endswith("radio5g/qdrv.ko") for e in selected):
        raise RuntimeError("F159 qdrv.ko missing")
    manifest: list[dict[str, object]] = []
    for entry in selected:
        target = OUT / "latest-try/f159/extracted-rootfs" / entry.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.data)
        manifest.append({"path": entry.name, "bytes": len(entry.data), "sha256": hashlib.sha256(entry.data).hexdigest()})
    return {"file_count": len(manifest), "files": manifest}


def sanitized_summary(source: Path, relative: str) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    for key in ("first_station", "last_station"):
        if isinstance(data.get(key), dict):
            data[key].pop("station_mac", None)
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if OUT.exists() or ZIP.exists():
        raise RuntimeError(f"refusing to overwrite existing handoff: {OUT} or {ZIP}")
    OUT.mkdir(parents=True)

    copy_tree(F150 / "drivers", "stable-drivers/f150-dual-radio/drivers")
    copy_file(F150 / "manifest.json", "stable-drivers/f150-dual-radio/f150-handoff-manifest.json")
    copy_file(F150 / "README.md", "stable-drivers/f150-dual-radio/README.md")

    f157_image = one("*.webformat.bin", F157_BUILD)
    copy_file(f157_image, "stable-drivers/f157-5ghz/firmware/OpenMitraStar-HGW500-F157-Linux-5.10.webformat.bin")
    for name in ("manifest.json", "bootbase-contract.json", "entry-contract.json", "SHA256SUMS"):
        copy_file(F157_BUILD / name, f"stable-drivers/f157-5ghz/evidence/{name}")
    copy_file(one("flash-one-shot-*/result.json", F157_BUILD), "stable-drivers/f157-5ghz/evidence/flash-result.json")
    copy_file(one("evaluation-*.json", F157_EVIDENCE), "stable-drivers/f157-5ghz/evidence/client-traffic-evaluation.json")

    f159_image = one("*.webformat.bin", F159_BUILD)
    copy_file(f159_image, "latest-try/f159/firmware/OpenMitraStar-HGW500-F159-Linux-5.10.webformat.bin")
    for name in ("manifest.json", "bootbase-contract.json", "entry-contract.json", "SHA256SUMS"):
        copy_file(F159_BUILD / name, f"latest-try/f159/evidence/{name}")
    copy_file(one("flash-one-shot-*/result.json", F159_BUILD), "latest-try/f159/evidence/flash-result.json")
    for source in F159_EVIDENCE_DIRS:
        sanitized_summary(source / "summary.json", f"latest-try/f159/evidence/{source.name}-summary.redacted.json")
    copy_file(F159_CLEAN_REBOOT_STATUS, "latest-try/f159/evidence/clean-reboot-ready-status.json")
    driver_manifest = extract_f159_drivers()

    copy_file(OEM, "firmware-oem/" + OEM.name)
    copy_file(OLD_DUMP, "dumps/historical-oem/hgw500bna-qcv2-firmware-dump-verified.zip")
    copy_tree(NEW_DUMP, "dumps/current-f159-physical")
    copy_file(ROOT / "docs/OPENMITRASTAR_HGW500_OPS.md", "docs/OPENMITRASTAR_HGW500_OPS.md")
    copy_file(ROOT / "docs/OPENMITRASTAR_F150_CURRENT_STATE.md", "docs/OPENMITRASTAR_F150_CURRENT_STATE.md")

    new_full = OUT / "dumps/current-f159-physical/hgw500-physical-mtd0-mtd5-16MiB.bin"
    manifest = {
        "schema": "openmitrastar.f159-latest-try-full-private-handoff/v1",
        "generated_date": "2026-08-31",
        "classification": "PRIVATE_OWNER_BACKUP_CONTAINS_RAW_MTD5",
        "target": "HGW-500BNA-QCv2 A2",
        "kernel": "5.10.260-openmitrastar-radiohw",
        "stable_baselines": {
            "dual_radio_f150": "known-good persistent dual-radio functional checkpoint",
            "radio5_f157": "WPA2 bridge, DHCP/DNS/Internet and bidirectional performance PASS",
        },
        "latest_try": {
            "version": "F159",
            "image_sha256": sha256(OUT / "latest-try/f159/firmware/OpenMitraStar-HGW500-F159-Linux-5.10.webformat.bin"),
            "installed_and_read_back": True,
            "release_ready": False,
            "driver_extract": driver_manifest,
        },
        "oem_firmware": {"sha256": sha256(OUT / "firmware-oem" / OEM.name), "immutable_reference": True},
        "dumps": {
            "historical_archive_sha256": sha256(OUT / "dumps/historical-oem/hgw500bna-qcv2-firmware-dump-verified.zip"),
            "historical_warning": "contains logical mtd6 appended; not a raw physical SPI image",
            "current_physical_bytes": new_full.stat().st_size,
            "current_physical_sha256": sha256(new_full),
            "current_physical_layout": "mtd0 through mtd5 only, exact 16 MiB SPI image",
        },
        "privacy": {"raw_mtd5_included": True, "credentials_echoed_in_docs": False, "share_publicly": False},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    readme = """# OpenMitraStar HGW-500 F159 full private handoff

This is a private owner backup. It includes the raw physical `mtd5/data` partition; do not upload or publish it.

## Contents

- `stable-drivers/f150-dual-radio/`: last conservative dual-radio checkpoint and its exact extracted driver set.
- `stable-drivers/f157-5ghz/`: last fully demonstrated 5 GHz WPA2/bridge/Internet performance checkpoint.
- `latest-try/f159/`: latest materialized attempt, exact webformat image, build/flash contracts, redacted 2.4 GHz evidence and byte-extracted drivers.
- `firmware-oem/`: immutable original Movistar/MitraStar webformat firmware.
- `dumps/historical-oem/`: older verified archive. Its `mtd0-mtd6` concatenation is NOT a raw physical flash image.
- `dumps/current-f159-physical/`: new read-only physical 16 MiB capture of `mtd0..mtd5`, plus split partitions and manifest.

## Status boundary

F157 is the 5 GHz stable checkpoint. F159 is the newest materialized try at packaging time and is not declared release-ready. The current physical dump contains F159 in `mtd4/linux_live`; `mtd3/linux_safety` remains preserved.

Never write the historical `mtd0-mtd6` concatenation to SPI. Normal firmware writes target only physical `mtd4/linux_live` and require a fresh reviewed flash plan.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    sums: list[str] = []
    for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
        sums.append(f"{sha256(path)}  {path.relative_to(OUT).as_posix()}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")

    shutil.make_archive(str(OUT), "zip", root_dir=OUT.parent, base_dir=OUT.name)
    with zipfile.ZipFile(ZIP) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failure: {bad}")
        names = set(archive.namelist())
        for required in (
            f"{NAME}/manifest.json",
            f"{NAME}/firmware-oem/{OEM.name}",
            f"{NAME}/dumps/current-f159-physical/hgw500-physical-mtd0-mtd5-16MiB.bin",
            f"{NAME}/latest-try/f159/firmware/OpenMitraStar-HGW500-F159-Linux-5.10.webformat.bin",
        ):
            if required not in names:
                raise RuntimeError(f"ZIP missing {required}")
    sidecar = ZIP.with_suffix(ZIP.suffix + ".sha256")
    sidecar.write_text(f"{sha256(ZIP)}  {ZIP.name}\n", encoding="ascii")
    print(f"HANDOFF_PASS zip={ZIP} bytes={ZIP.stat().st_size} sha256={sha256(ZIP)} files={len(sums)+1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
