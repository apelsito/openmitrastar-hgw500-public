"""Compose an immutable, offline UI-only F321 candidate from exact F314/F319."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import zlib

import compose_f164_squashfs_product as compose
from audit_lyoko_full_liberation import verify_recorded_bootbase_rehearsal, verify_recorded_f319_runtime
from build_f196_device_personalized import verify_embedded_key
from f321_classic_ui_rootfs_worker import RELEASE_PATH, SOURCE_ROOTFS_HASHES, product_version
from init_lyoko_device_host_key import DEFAULT_TOOL, restrict_acl
from lyoko_web_rootfs_worker import API_PATH, sha256, validate_overlay


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
BASE = "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
EXPECTED_F319 = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
EXPECTED_F314 = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
BASE_CANDIDATE_HASHES = {"f314": EXPECTED_F314, "f319": EXPECTED_F319}
ROOTFS_OFFSET, ROOTFS_WINDOW, STORE_OFFSET, SLOT_BYTES = 0x180000, 0x460000, 0x5E0000, 0x7A0000
EPOCH = 1788566400
RECOVERY = ROOT / "outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json"
RUNTIME = ROOT / "outputs/preflight/f319-runtime-probe-20260907T192754Z"
KERNEL_FILES = {
    ".uncompressed.uImage": "kernel-squashfs.uncompressed.uImage", ".kernel.raw.bin": "kernel-squashfs.raw.bin",
    ".kernel.lzma": "kernel-squashfs.lzma", ".config": "kernel-squashfs.config",
    ".dtb": "topaz_mitrastar_squashfs.dtb", ".vmlinux": "kernel-squashfs.vmlinux",
}


def wsl_path(path: Path) -> str:
    path = path.resolve()
    return "/mnt/" + path.drive[0].lower() + "/" + path.as_posix()[3:]


def validate_package(package: Path, expected_hash: str) -> tuple[dict, dict]:
    manifest_path = package / "manifest.json"
    if not re.fullmatch("[0-9a-f]{64}", expected_hash) or sha256(manifest_path) != expected_hash:
        raise ValueError("exact frontend package manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    if manifest.get("schema") != "openmitrastar.lyoko-web-next-overlay/v3":
        raise ValueError("only classic TSX v3 packages are accepted")
    if package.name != "lyoko-classic-tsx-" + manifest["build_id"]:
        raise ValueError("frontend package must keep its content-addressed directory name")
    return manifest, validate_overlay(package / "overlay", manifest)


def source_paths(base: str) -> tuple[Path, str]:
    if base not in BASE_CANDIDATE_HASHES:
        raise ValueError("unknown firmware base")
    return DEVICE / (base + "-device-bound"), f"openmitrastar-linux510-{base}-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"


def validate_base(base: str) -> dict:
    source_dir, source_base = source_paths(base)
    candidate = source_dir / (source_base + ".webformat.bin")
    rootfs = source_dir / (source_base + ".rootfs.squashfs")
    if sha256(candidate) != BASE_CANDIDATE_HASHES[base] or sha256(rootfs) != SOURCE_ROOTFS_HASHES[base]:
        raise ValueError("immutable " + base.upper() + " base hash mismatch")
    if candidate.read_bytes()[ROOTFS_OFFSET:] != rootfs.read_bytes():
        raise ValueError("rootfs sidecar does not match the exact candidate")
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="ascii"))
    if manifest["artifacts"]["webformat"]["sha256"] != BASE_CANDIDATE_HASHES[base]:
        raise ValueError("base manifest identifies another candidate")
    for name, suffix in (("kernel_lzma", ".kernel.lzma"), ("dtb", ".dtb"), ("config", ".config")):
        if sha256(source_dir / (source_base + suffix)) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("base sidecar drift: " + name)
    return manifest


def verify_candidate_delta(result: dict, expected_files: set[str]) -> None:
    allowed = expected_files | {API_PATH, RELEASE_PATH}
    if not set(result["checks"]["changed_files"]).issubset(allowed):
        raise ValueError("F321 changed a file outside the UI and release contract")
    for path, previous in result["before"].items():
        if path not in allowed and result["after"].get(path) != previous:
            raise ValueError("F321 modified a protected runtime entry: " + path)


def worker_build(package: Path, manifest_hash: str, target: Path, result_path: Path, distro: str, base: str, firmware_build_id: str) -> dict:
    source_dir, source_base = source_paths(base)
    argv = ["python3", wsl_path(ROOT / "tools/f321_classic_ui_rootfs_worker.py"),
            "--base", base, "--firmware-build-id", firmware_build_id,
            "--source", wsl_path(source_dir / (source_base + ".rootfs.squashfs")),
            "--overlay", wsl_path(package / "overlay"), "--manifest", wsl_path(package / "manifest.json"),
            "--manifest-sha256", manifest_hash, "--image", wsl_path(target), "--result", wsl_path(result_path), "--epoch", str(EPOCH)]
    result = subprocess.run(["wsl.exe", "-d", distro, "-u", "root", "-e", "sh", "-c", shlex.join(argv)],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or "F321 rootfs worker failed")
    return json.loads(result_path.read_text(encoding="ascii"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, choices=tuple(BASE_CANDIDATE_HASHES))
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--package-manifest-sha256", required=True)
    parser.add_argument("--baseline-observation", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--verify-reproducible", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    package_manifest, overlay = validate_package(package, args.package_manifest_sha256)
    source_manifest = validate_base(args.base)
    source_dir, source_base = source_paths(args.base)
    base_hash = BASE_CANDIDATE_HASHES[args.base]
    firmware_build_id = hashlib.sha256((base_hash + args.package_manifest_sha256).encode("ascii")).hexdigest()[:16]
    observation = None
    if args.baseline_observation:
        observed = json.loads(args.baseline_observation.read_text(encoding="ascii"))
        expected_version = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device" if args.base == "f314" else "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
        if observed.get("pinned_ssh") is not True or observed.get("exit_code") != 0 or ("OPENMITRASTAR_PRODUCT_VERSION=" + expected_version) not in observed.get("stdout", "").splitlines():
            raise ValueError("baseline observation does not identify the selected release")
        observation = {"path": str(args.baseline_observation.resolve()), "sha256": sha256(args.baseline_observation), "observed_at": observed.get("generated_at"),
                       "scope": "pinned SSH release observation; not a whole-flash readback"}
    recovery_candidate = DEVICE / "f314-device-bound" / "openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin"
    if sha256(recovery_candidate) != EXPECTED_F314:
        raise ValueError("exact F314 recovery artifact changed")
    recovery = verify_recorded_bootbase_rehearsal(RECOVERY)
    runtime = verify_recorded_f319_runtime(RUNTIME) if args.base == "f319" else None
    if recovery.get("verified") is not True or (runtime is not None and runtime.get("verified") is not True):
        raise ValueError("recorded base acceptance or F314 recovery proof could not be revalidated")
    final = DEVICE / ("f321-" + args.base + "-device-bound")
    if final.exists() and not args.verify_reproducible:
        raise ValueError("refusing to overwrite F321; changed firmware requires a new version")
    if args.verify_reproducible and not final.is_dir():
        raise ValueError("reproducibility verification requires an existing F321 candidate")
    if args.verify_reproducible:
        existing = json.loads((final / "manifest.json").read_text(encoding="ascii"))
        if existing["frontend"]["manifest_sha256"] != args.package_manifest_sha256:
            raise ValueError("F321 reproducibility requires its original exact UI package")

    scratch_root = DEVICE / ".build-scratch"
    scratch_root.mkdir(exist_ok=True)
    restrict_acl(scratch_root, directory=True)
    scratch = Path(tempfile.mkdtemp(prefix="f321-ui-", dir=scratch_root)).resolve()
    restrict_acl(scratch, directory=True)
    try:
        assets, output = scratch / "assets", scratch / "build"
        assets.mkdir()
        inventory_path = scratch / "rootfs-inventory.json"
        inventory = worker_build(package, args.package_manifest_sha256, assets / "rootfs-product-xz-128k.squashfs", inventory_path, args.distro, args.base, firmware_build_id)
        verify_candidate_delta(inventory, set(overlay))
        for suffix, name in KERNEL_FILES.items():
            shutil.copy2(source_dir / (source_base + suffix), assets / name)
        settings = {"ASSETS": assets, "OUT": output, "BASE": BASE, "ROOTFS_WINDOW": ROOTFS_WINDOW, "SOURCE_DATE_EPOCH": EPOCH}
        saved = {name: getattr(compose, name) for name in settings}
        template = compose.f71.TEMPLATE
        build_log = io.StringIO()
        try:
            for name, value in settings.items():
                setattr(compose, name, value)
            # Use only the exact selected header/template, never a mutable OEM input.
            compose.f71.TEMPLATE = source_dir / (source_base + ".webformat.bin")
            with contextlib.redirect_stdout(build_log):
                code = compose.main()
        finally:
            compose.f71.TEMPLATE = template
            for name, value in saved.items():
                setattr(compose, name, value)
        if code:
            raise RuntimeError("F321 Bootbase composition failed")
        manifest = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        for suffix in KERNEL_FILES:
            if sha256(source_dir / (source_base + suffix)) != sha256(output / (BASE + suffix)):
                raise ValueError("F321 unexpectedly changed a kernel sidecar: " + suffix)
        candidate = output / (BASE + ".webformat.bin")
        data = candidate.read_bytes()
        baseline = (source_dir / (source_base + ".webformat.bin")).read_bytes()
        if data[64:ROOTFS_OFFSET] != baseline[64:ROOTFS_OFFSET]:
            raise ValueError("F321 changed the sealed header padding or kernel payload")
        if len(data) > STORE_OFFSET or manifest["contracts"]["bootbase"] != "PASS":
            raise ValueError("F321 Bootbase/store-fit contract failed")
        full_slot = data + b"\xff" * (SLOT_BYTES - len(data))
        verify_embedded_key(output / (BASE + ".rootfs.squashfs"), source_manifest["device_identity"]["fingerprint"], args.distro, DEFAULT_TOOL, scratch)
        manifest.update({
            "schema": "openmitrastar.f321-classic-ui-candidate/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "PRIVATE_OFFLINE_UI_ONLY_CANDIDATE_NO_PHYSICAL_AUTHORIZATION",
            "product_version": product_version(args.base), "firmware_build_id": firmware_build_id,
            "candidate_eligible": False, "release_eligible": False, "flash_supported": False,
            "source": {"firmware": "exact local " + args.base.upper(), "candidate_sha256": base_hash, "rootfs_sha256": SOURCE_ROOTFS_HASHES[args.base],
                       "accepted_runtime_record": str(RUNTIME / "result.json") if runtime else str(RECOVERY), "current_device_state_queried": False,
                       "baseline_observation": observation},
            "frontend": {"package": str(package), "build_id": package_manifest["build_id"], "manifest_sha256": args.package_manifest_sha256,
                         "presentation": "classic Movistar/Telefonica TSX", "new_assets_bytes": package_manifest["total_bytes"]},
            "device_identity": source_manifest["device_identity"], "web_identity": source_manifest["web_identity"], "web_security": source_manifest["web_security"],
            "change_scope": {"changed_paths": inventory["checks"]["changed_files"], "metadata": inventory["checks"],
                             "kernel_dtb_radios": "byte-identical to " + args.base.upper(), "spi_modules_and_autoload": "unchanged from " + args.base.upper(),
                             "dfs_backend": "unchanged; no native detector or CAC guard overlay integrated",
                             "api_transform": inventory["transforms"], "release_identity": inventory["release_identity"]},
            "storage": {**source_manifest["storage"], "persistent_writes_enabled": False, "candidate_ends_before_store": True,
                        "store_erased_ff": all(byte == 255 for byte in full_slot[STORE_OFFSET:])},
            "physical_validation": {"status": "NOT_RUN", "authorized": False,
                                    "required": ["reviewed F321 promotion and rollback executor", "exact candidate authorization",
                                                 "fresh target identity, current backup/readback and exclusive UART ownership",
                                                 "persistent boot, pinned SSH, authenticated UI/API and dual-radio regression"]},
            "recovery": {"candidate": str(recovery_candidate), "candidate_sha256": EXPECTED_F314, "full_slot_crc32": "d6b13baa",
                         "record": str(RECOVERY), "record_sha256": sha256(RECOVERY), "file_only_revalidation": recovery,
                         "plan": "Restore exact F314 to physical mtd4 through the guarded Bootbase path; preserve OEM, safety, bootenv and calibration",
                         "working_mtd3_rescue_claimed": False},
            "safety": {"hardware_actions": False, "normal_write_target": "mtd4/linux_live only after separate exact authorization",
                       "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "mtd6": "logical rootfs view; never a physical write target",
                       "flash_go_no_go": "NO_GO_PHYSICAL_PENDING_EXECUTOR_REVIEW_AUTHORIZATION_AND_FRESH_GATES"},
        })
        manifest["layout"]["mtd_mapping"] = args.base.upper() + " kernel/DTB mapping preserved; physical mtd4 rootfs subwindow begins at slot offset 0x180000"
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
        shutil.copy2(package / "manifest.json", output / "frontend-package-manifest.json")
        shutil.copy2(inventory_path, output / "rootfs-inventory.json")
        (output / "composition.log").write_text(build_log.getvalue(), encoding="utf-8")
        (output / "known_hosts.f321").write_bytes((source_dir / ("known_hosts." + args.base)).read_bytes())
        (output / "LAYOUT.md").write_text(f"# F321 classic UI candidate\n\nUI package `{package_manifest['build_id']}` over exact {args.base.upper()}.\n"
            f"\nCandidate: {len(data)} bytes; rootfs offset 0x180000; rootfs window 0x460000; store starts at 0x5e0000.\n"
            "\nNO GO for physical execution. Kernel, DTB, radio controls and storage modules remain unchanged.\n"
            "Recovery: exact F314 through guarded Bootbase to mtd4; this does not claim a working mtd3 rescue.\n", encoding="ascii")
        (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS"), encoding="ascii")
        report = {"status": "OFFLINE_CANDIDATE_NO_GO_PHYSICAL", "output": str(final), "candidate": str(final / candidate.name),
                  "base": args.base.upper(), "product_version": product_version(args.base), "firmware_build_id": firmware_build_id,
                  "bytes": len(data), "sha256": sha256(candidate), "full_slot_crc32": f"{zlib.crc32(full_slot) & 0xffffffff:08x}",
                  "bootbase": "PASS", "slot_fit": True, "rootfs_headroom_bytes": ROOTFS_WINDOW - manifest["artifacts"]["rootfs_squashfs"]["bytes"],
                  "package_build_id": package_manifest["build_id"], "hardware_actions": False}
        if args.verify_reproducible:
            for suffix in (*KERNEL_FILES, ".rootfs.squashfs", ".webformat.bin"):
                if sha256(output / (BASE + suffix)) != sha256(final / (BASE + suffix)):
                    raise ValueError("F321 reproducibility mismatch: " + suffix)
            report["status"] = "REPRODUCIBLE_PASS_NO_GO_PHYSICAL"
        else:
            shutil.copytree(output, final)
            restrict_acl(final, directory=True)
            for path in final.iterdir():
                if path.is_file():
                    restrict_acl(path, directory=False)
        evidence = ROOT / "outputs/preflight" / ("f321-classic-ui-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
        print(json.dumps({**report, "report": str(evidence / "result.json")}, indent=2))
    finally:
        if scratch.parent != scratch_root.resolve() or not scratch.name.startswith("f321-ui-"):
            raise RuntimeError("unsafe F321 scratch cleanup path")
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
