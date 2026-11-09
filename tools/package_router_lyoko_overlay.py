#!/usr/bin/env python3

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import stat
import tarfile
from pathlib import Path
from typing import Any

import sync_router_lyoko_static_data as sync_static
import validate_router_lyoko_evidence_bindings as evidence_bindings
import validate_router_lyoko_telemetry_contract as telemetry_contract
import verify_router_lyoko_aelita_memory as aelita_memory
import verify_router_lyoko_no_secrets as no_secrets
import verify_router_lyoko_objective_coverage as objective_coverage


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERLAY = ROOT / "work" / "mission-state" / "router-lyoko-v0"
DEFAULT_OUTPUT = ROOT / "outputs" / "router-lyoko" / "router-lyoko-v0-overlay.tar.gz"
DEFAULT_PACKAGE_MANIFEST = ROOT / "outputs" / "router-lyoko" / "router-lyoko-v0-package-manifest.json"
ARCHIVE_PREFIX = "router-lyoko-v0"
SOURCE_DATE_EPOCH = 1785024000

FORBIDDEN = (
    "saveenv",
    "fw_setenv",
    "mtd_write ",
    "flashcp",
    "/dev/mtd",
    "dd if=",
    "dd of=",
    "insmod ",
    "rmmod ",
    "modprobe ",
    "reboot",
    "halt",
    "poweroff",
    "ifconfig br0 ",
    "ip addr add",
    "ip link set",
    "call_qcsapi ",
    "qweconfig set",
    "hostapd_cli ",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rel_path(raw: str) -> Path:
    rel = Path(*raw.split("/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe overlay path: {raw}")
    return rel


def load_and_verify_overlay(overlay: Path) -> dict[str, Any]:
    manifest_path = overlay / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "READ-ONLY-LAB-OVERLAY-NO-FLASH":
        raise RuntimeError("overlay is not classified as read-only/no-flash")
    if manifest.get("guards", {}).get("flash_candidate") is not False:
        raise RuntimeError("overlay flash_candidate guard is not false")

    for raw_rel, meta in manifest["files"].items():
        path = overlay / rel_path(raw_rel)
        if not path.is_file():
            raise FileNotFoundError(f"missing manifest file: {raw_rel}")
        data = path.read_bytes()
        if len(data) != meta["bytes"]:
            raise RuntimeError(f"size mismatch for {raw_rel}")
        if sha256_bytes(data) != meta["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {raw_rel}")
    return manifest


def verify_static_truth_sync(overlay: Path) -> None:
    generated = sync_static.generate_static_data()
    mismatches = sync_static.find_static_drift(
        generated,
        data_dir=overlay / "rootfs" / "var" / "www" / "lyoko-data",
        manifest_path=overlay / "manifest.json",
        sha256sums_path=overlay / "SHA256SUMS",
    )
    if mismatches:
        raise RuntimeError(
            "static Lyoko truth is stale; run tools/sync_router_lyoko_static_data.py "
            f"before packaging: {json.dumps(mismatches, ensure_ascii=False)}"
        )


def verify_aelita_memory_guard(overlay: Path) -> None:
    report = aelita_memory.build_report(overlay / "rootfs" / "var" / "www" / "lyoko-data")
    if not report["ok"]:
        raise RuntimeError(
            "Aelita memory/dialogue guard failed; refusing to package static memory that can "
            f"overclaim hardware or write state: {json.dumps(report['findings'][:10], ensure_ascii=False)}"
        )


def verify_objective_coverage(overlay: Path) -> None:
    report = objective_coverage.build_report(overlay)
    if not report["ok"]:
        raise RuntimeError(
            "Router-Lyoko objective coverage guard failed; refusing to package an overlay that "
            f"misses required surfaces or overclaims hardware: {json.dumps(report['findings'][:10], ensure_ascii=False)}"
        )


def verify_evidence_bindings(overlay: Path) -> None:
    bindings_path = overlay / "evidence-bindings.json"
    web_root = overlay / "rootfs" / "var" / "www"
    report_errors = evidence_bindings.validate(evidence_bindings.load_json(bindings_path), web_root=web_root)
    if report_errors:
        raise RuntimeError(
            "Router-Lyoko evidence bindings guard failed; refusing to package an overlay that "
            f"can blur runtime proof with static snapshots: {json.dumps(report_errors[:10], ensure_ascii=False)}"
        )


def verify_telemetry_contract(overlay: Path) -> None:
    contract_path = overlay / "telemetry-contract.json"
    report_errors = telemetry_contract.validate(telemetry_contract.load_json(contract_path))
    if report_errors:
        raise RuntimeError(
            "Router-Lyoko telemetry contract guard failed; refusing to package an overlay that "
            f"can blur stale/static telemetry with live hardware proof or control actions: {json.dumps(report_errors[:10], ensure_ascii=False)}"
        )


def archive_inputs(overlay: Path, manifest: dict[str, Any]) -> list[Path]:
    paths = [overlay / "manifest.json", overlay / "SHA256SUMS"]
    paths.extend(overlay / rel_path(raw_rel) for raw_rel in manifest["files"])
    unique = sorted(set(paths), key=lambda p: p.relative_to(overlay).as_posix())
    for path in unique:
        if not path.is_file():
            raise FileNotFoundError(f"missing package input: {path}")
    return unique


def scan_forbidden(paths: list[Path]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN:
            if token in text:
                raise RuntimeError(f"forbidden control token {token!r} in {path}")


def verify_no_secrets(paths: list[Path], overlay: Path) -> None:
    no_secrets.assert_no_secrets(
        paths,
        base=overlay / "rootfs" / "var" / "www",
    )


def add_file(tar: tarfile.TarFile, overlay: Path, path: Path) -> None:
    rel = path.relative_to(overlay).as_posix()
    data = path.read_bytes()
    info = tarfile.TarInfo(f"{ARCHIVE_PREFIX}/{rel}")
    info.size = len(data)
    info.mtime = SOURCE_DATE_EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    executable_cgi = {
        "rootfs/var/www/api/lyoko",
        "rootfs/var/www/api/lyoko-control",
    }
    info.mode = 0o755 if rel in executable_cgi else 0o644
    tar.addfile(info, io.BytesIO(data))


def build_archive_bytes(overlay: Path, paths: list[Path]) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in paths:
            add_file(tar, overlay, path)

    gz_buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buffer, mtime=0) as gz:
        gz.write(tar_buffer.getvalue())
    return gz_buffer.getvalue()


def build_package(overlay: Path, output: Path, package_manifest: Path, dry_run: bool) -> dict[str, Any]:
    overlay = overlay.resolve()
    manifest = load_and_verify_overlay(overlay)
    verify_static_truth_sync(overlay)
    verify_aelita_memory_guard(overlay)
    verify_objective_coverage(overlay)
    verify_evidence_bindings(overlay)
    verify_telemetry_contract(overlay)
    paths = archive_inputs(overlay, manifest)
    rootfs = overlay / "rootfs"
    scan_forbidden(
        [
            p
            for p in paths
            if p.is_relative_to(rootfs)
            and p.suffix in {".sh", ".js", ".html", ".css", ".json", ".md", ""}
        ]
    )
    verify_no_secrets([p for p in paths if p.is_relative_to(rootfs)], overlay)
    archive = build_archive_bytes(overlay, paths)
    report = {
        "schema": "router-lyoko.overlay-package/v1",
        "classification": "READ-ONLY-LAB-OVERLAY-PACKAGE-NO-FLASH",
        "archive": {
            "path": str(output),
            "bytes": len(archive),
            "sha256": sha256_bytes(archive),
        },
        "source_overlay": str(overlay),
        "archive_prefix": ARCHIVE_PREFIX,
        "file_count": len(paths),
        "guards": manifest["guards"],
        "dry_run": dry_run,
        "integration_note": "Extract only into a RAM-test rootfs staging area; this package is not a flash candidate.",
    }
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(archive)
        package_manifest.parent.mkdir(parents=True, exist_ok=True)
        package_manifest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic Router-Lyoko read-only overlay package.")
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--package-manifest", type=Path, default=DEFAULT_PACKAGE_MANIFEST)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_package(args.overlay, args.output, args.package_manifest, args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
