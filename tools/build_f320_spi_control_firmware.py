#!/usr/bin/env python3
"""Package F320 offline over immutable F319; never replace or flash either image."""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import zlib

import build_f170_lyoko_foundation_runtime_fix as engine
import compose_f164_squashfs_product as compose
from build_f196_device_personalized import verify_embedded_key
from init_lyoko_device_host_key import DEFAULT_TOOL, restrict_acl
from build_f320_spi_control_probe import EXPECTED_F319, NAME

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
SOURCE_BASE = "openmitrastar-linux510-f319-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
BASE = "openmitrastar-linux510-f320-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
VERSION = "lyoko-foundation-6.8.4-f320-spi-control-read-device"
MODULE_TARGET = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/" + NAME + ".ko"
FEATURE_TARGET = "etc/openmitrastar/features/spi-control-read-v1"
EXPECTED_CHANGES = {"etc/openmitrastar/release", MODULE_TARGET, FEATURE_TARGET}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_contract(module_dir: Path) -> dict:
    manifest = json.loads((module_dir / "manifest.json").read_text(encoding="ascii"))
    if manifest["status"] != "OFFLINE_PASS" or manifest["physical_validation"] != "NOT_RUN":
        raise ValueError("F320 needs a qualified offline module")
    module = module_dir / (NAME + ".ko")
    if sha(module) != manifest["artifact"]["sha256"]:
        raise ValueError("F320 module changed")
    contract = manifest["contract"]
    expected = {"spi_address": "0xe2000004", "sysctl_map_address": "0xe0000004",
                "spi_reads_max": 1, "sysctl_reads_max": 1, "mmio_writes": 0,
                "flash_opcodes": 0, "autoload": False, "provider_ready": False,
                "default_access": "REFUSED", "mtd_registration": False}
    if any(type(contract.get(key)) is not type(value) or contract[key] != value for key, value in expected.items()):
        raise ValueError("F320 read-only scope changed")
    for item in manifest["provenance"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("F320 source/kernel provenance drift: " + item["path"])
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-dir", required=True, type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--verify-reproducible", action="store_true",
                        help="Rebuild in scratch and compare, never replace the existing candidate")
    args = parser.parse_args()
    module_dir = args.module_dir.resolve()
    module_manifest = verify_contract(module_dir)
    source = DEVICE / "f319-device-bound"
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    if sha(source / (SOURCE_BASE + ".webformat.bin")) != EXPECTED_F319:
        raise SystemExit("immutable F319 base differs")
    final = DEVICE / "f320-device-bound"
    if final.exists() and not args.verify_reproducible:
        raise SystemExit("refusing to overwrite F320; use a new version for changed firmware")
    if args.verify_reproducible and not final.is_dir():
        raise SystemExit("reproducibility verification needs the existing F320 candidate")
    scratch_root = ROOT / ".codex_tmp"
    scratch_root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="f320-package-", dir=scratch_root)).resolve()
    restrict_acl(scratch, directory=True)
    # Exact temporary directory only; final output is never removed on error.
    try:
        source_build = scratch / "source"
        source_build.mkdir()
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, source_build / item.name)
        overlay = scratch / "foundation/overlay"
        module_path = overlay / MODULE_TARGET
        module_path.parent.mkdir(parents=True)
        shutil.copy2(module_dir / (NAME + ".ko"), module_path)
        module_path.chmod(0o644)
        feature = overlay / FEATURE_TARGET
        feature.parent.mkdir(parents=True)
        feature.write_text("OPENMITRASTAR_SPI_CONTROL_MODE=legacy-map-guarded-single-read\n"
                           "OPENMITRASTAR_SPI_CONTROL_AUTOLOAD=0\n"
                           "OPENMITRASTAR_SPI_CONTROL_DEFAULT_EXECUTE=0\n"
                           "OPENMITRASTAR_SPI_CONTROL_READS_MAX=1\n"
                           "OPENMITRASTAR_SPI_CONTROL_MAP_READS_MAX=1\n"
                           "OPENMITRASTAR_SPI_CONTROL_WRITES=0\n"
                           "OPENMITRASTAR_SPI_CONTROL_PROVIDER_READY=0\n", encoding="ascii", newline="\n")
        output = scratch / "build"
        settings = {"SOURCE_BUILD": source_build, "SOURCE_BASE": SOURCE_BASE,
                    "FOUNDATION": scratch / "foundation", "OVERLAY": overlay,
                    "ASSETS": scratch / "assets", "OUT": output, "BASE": BASE,
                    "PRODUCT_VERSION": VERSION, "ASSETS_SCHEMA": "openmitrastar.f320-assets/v1",
                    "DIFF_SCHEMA": "openmitrastar.f320-rootfs-diff/v1", "REMOVE_PATHS": (),
                    "DISTRO": args.distro}
        saved = {key: getattr(engine, key) for key in settings}
        old_window = compose.ROOTFS_WINDOW
        build_log = io.StringIO()
        try:
            for key, value in settings.items():
                setattr(engine, key, value)
            compose.ROOTFS_WINDOW = 0x460000
            with contextlib.redirect_stdout(build_log):
                rc = engine.main()
        finally:
            for key, value in saved.items():
                setattr(engine, key, value)
            compose.ROOTFS_WINDOW = old_window
        if rc:
            raise RuntimeError("F320 composition failed")
        manifest = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
        if changed != EXPECTED_CHANGES:
            raise RuntimeError("unexpected F320 rootfs delta: " + repr(sorted(changed)))
        for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
            if sha(source / (SOURCE_BASE + suffix)) != sha(output / (BASE + suffix)):
                raise RuntimeError("kernel/DTB/config changed: " + suffix)
        rootfs = output / (BASE + ".rootfs.squashfs")
        verify_embedded_key(rootfs, source_manifest["device_identity"]["fingerprint"],
                            args.distro, DEFAULT_TOOL, scratch)
        data = (output / (BASE + ".webformat.bin")).read_bytes()
        if len(data) > 0x5e0000:
            raise RuntimeError("F320 overlaps store")
        full_slot = data + b"\xff" * (0x7a0000 - len(data))
        manifest.update({
            "schema": "openmitrastar.f320-spi-control-candidate/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classification": "PRIVATE_OFFLINE_SINGLE_SPI_CONTROL_READ_NO_PHYSICAL_AUTHORIZATION",
            "candidate_eligible": False, "flash_supported": False, "release_eligible": False,
            "device_identity": source_manifest["device_identity"],
            "web_identity": source_manifest["web_identity"], "web_security": source_manifest["web_security"],
            "source": {"firmware": "exact accepted F319", "sha256": EXPECTED_F319,
                       "module_manifest": str(module_dir / "manifest.json"),
                       "module_manifest_sha256": sha(module_dir / "manifest.json")},
            "spi_control_probe": {**module_manifest["contract"], "module": "/" + MODULE_TARGET,
                                  "module_sha256": module_manifest["artifact"]["sha256"]},
            "change_scope": {"kernel_dtb_radio": "byte-identical to F319",
                             "changed_paths": sorted(EXPECTED_CHANGES)},
            "storage": {**source_manifest["storage"], "persistent_writes_enabled": False,
                        "store_erased_ff": all(byte == 255 for byte in full_slot[0x5e0000:])},
            "physical_validation": {"status": "NOT_RUN", "authorized": False,
                "needs": ["reviewed F320 promotion/runtime/rollback runner", "exact candidate authorization",
                          "fresh HGW UART binding and exclusive lease", "physical power-cycle contingency",
                          "correlated capture, one control read, unload, platform and both radio regression"]},
            "safety": {"normal_write_target": "mtd4/linux_live only under separate authorization",
                       "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
                       "hardware_actions": "none", "recovery": "exact F314 via Bootbase; not mtd3 rescue",
                       "machine_check": "kernel die() halts CPU; SysRq rollback is not guaranteed"},
        })
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
        (output / "composition.log").write_text(build_log.getvalue(), encoding="utf-8")
        (output / "known_hosts.f320").write_bytes((source / "known_hosts.f319").read_bytes())
        (output / "SHA256SUMS").write_text("".join(f"{sha(path)}  {path.name}\n" for path in sorted(output.iterdir())
                                                 if path.is_file() and path.name != "SHA256SUMS"), encoding="ascii")
        if args.verify_reproducible:
            compared = []
            for suffix in (".webformat.bin", ".rootfs.squashfs", ".uncompressed.uImage",
                           ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
                name = BASE + suffix
                if sha(output / name) != sha(final / name):
                    raise RuntimeError("F320 reproducibility mismatch: " + suffix)
                compared.append({"file": name, "sha256": sha(final / name)})
            report_dir = ROOT / "outputs/preflight" / ("f320-firmware-repro-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            report_dir.mkdir(parents=True, exist_ok=False)
            report = {"status": "PASS", "scope": "independent scratch rebuild; immutable original retained",
                      "compared": compared, "hardware_actions": False, "physical_validation": "NOT_RUN"}
            (report_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
            print(json.dumps({"status": "REPRODUCIBLE_PASS", "report": str(report_dir / "result.json")}))
            return 0
        shutil.copytree(output, final)
        restrict_acl(final, directory=True)
        for path in final.iterdir():
            if path.is_file():
                restrict_acl(path, directory=False)
        print(json.dumps({"status": "OFFLINE_CANDIDATE_NO_GO_PHYSICAL", "output": str(final),
                          "sha256": sha(final / (BASE + ".webformat.bin")), "bytes": len(data),
                          "slot_crc32": f"{zlib.crc32(full_slot) & 0xffffffff:08x}",
                          "hardware_actions": False}, indent=2))
    finally:
        if scratch.parent != scratch_root.resolve() or not scratch.name.startswith("f320-package-"):
            raise RuntimeError("unsafe scratch cleanup path")
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
