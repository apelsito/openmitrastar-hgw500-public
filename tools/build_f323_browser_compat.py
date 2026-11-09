"""Build or independently reproduce offline F323 from sealed F321, never flash."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

import compose_f164_squashfs_product as compose
import f323_browser_compat_contract as contract
from audit_lyoko_full_liberation import verify_recorded_bootbase_rehearsal
from build_f321_classic_ui_candidate import EPOCH, EXPECTED_F314, KERNEL_FILES, RECOVERY, wsl_path
from init_lyoko_device_host_key import restrict_acl
from lyoko_web_rootfs_worker import sha256
from package_f323_browser_compat import validate_package

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
SOURCE = DEVICE / "f321-f314-device-bound"
SOURCE_BASE = "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
BASE = "openmitrastar-linux510-f323-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
FINAL = DEVICE / "f323-f321-browser-compat-device-bound"
ACCEPTANCE = ROOT / "outputs/postflash/f321-acceptance-20260911T091500Z/result.json"
ACCEPTANCE_SHA = "7795bda97bc87e597677b779715bc0acede2e78ddbdd6fee370a376ce09f8f21"
SOURCE_TOOLS = (
    "build_f323_browser_compat.py", "f323_browser_compat_contract.py", "f323_browser_compat_rootfs_worker.py",
    "package_f323_browser_compat.py", "lyoko_config_store_status_contract.py", "lyoko_web_rootfs_worker.py",
    "compose_f164_squashfs_product.py", "build_f71_qcsapi_interp_from_f70.py", "build_f321_classic_ui_candidate.py",
    "package_lyoko_web_next.py", "lyoko_frontend_identity.py", "bootbase_contract_emulator.py",
    "init_lyoko_device_host_key.py", "audit_lyoko_full_liberation.py",
)


def validate_inputs(package: Path, package_hash: str) -> tuple[dict, dict, dict, dict]:
    if not re.fullmatch(r"[0-9a-f]{64}", package_hash) or sha256(package / "manifest.json") != package_hash:
        raise ValueError("F323 package manifest hash mismatch")
    manifest = json.loads((package / "manifest.json").read_text(encoding="ascii"))
    if package.name != "lyoko-classic-compat-" + manifest["build_id"]:
        raise ValueError("F323 package needs its content-addressed name")
    expected = validate_package(package / "overlay", manifest)
    contract.pinned((SOURCE / "manifest.json").read_bytes(), contract.SOURCE_MANIFEST, "F321 manifest")
    source_manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="ascii"))
    candidate = (SOURCE / (SOURCE_BASE + ".webformat.bin")).read_bytes()
    rootfs = (SOURCE / (SOURCE_BASE + ".rootfs.squashfs")).read_bytes()
    contract.pinned(candidate, contract.SOURCE_CANDIDATE, "F321 image")
    contract.pinned(rootfs, contract.SOURCE_ROOTFS, "F321 rootfs")
    if candidate[contract.ROOTFS_OFFSET:] != rootfs:
        raise ValueError("F321 source sidecar mismatch")
    for key, suffix in (("kernel_lzma", ".kernel.lzma"), ("dtb", ".dtb"), ("config", ".config")):
        if sha256(SOURCE / (SOURCE_BASE + suffix)) != source_manifest["artifacts"][key]["sha256"]:
            raise ValueError("F321 sidecar drift: " + key)
    contract.pinned(ACCEPTANCE.read_bytes(), ACCEPTANCE_SHA, "recorded F321 acceptance")
    acceptance = json.loads(ACCEPTANCE.read_text(encoding="ascii"))
    if acceptance.get("status") != "PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION" or acceptance.get("candidate_sha256") != contract.SOURCE_CANDIDATE:
        raise ValueError("recorded F321 acceptance does not identify the base")
    recovery_file = DEVICE / "f314-device-bound/openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin"
    contract.pinned(recovery_file.read_bytes(), EXPECTED_F314, "exact F314 recovery artifact")
    recovery = verify_recorded_bootbase_rehearsal(RECOVERY)
    if recovery.get("verified") is not True:
        raise ValueError("historical F314 recovery evidence failed revalidation")
    return manifest, expected, source_manifest, recovery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--package-manifest-sha256", required=True)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--verify-reproducible", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve()
    package_manifest, expected_ui, source_manifest, recovery = validate_inputs(package, args.package_manifest_sha256)
    if FINAL.exists() and not args.verify_reproducible:
        raise ValueError("refusing to replace F323; changes require a new version")
    if args.verify_reproducible:
        if not FINAL.is_dir():
            raise ValueError("reproduction requires the original F323 artifact")
        original_manifest = json.loads((FINAL / "manifest.json").read_text(encoding="ascii"))
        if original_manifest["frontend"]["manifest_sha256"] != args.package_manifest_sha256:
            raise ValueError("reproduction requires the original F323 package")
    sources = {name: sha256(ROOT / "tools" / name) for name in SOURCE_TOOLS}
    build_id = contract.digest(json.dumps({"base": contract.SOURCE_CANDIDATE, "package": args.package_manifest_sha256,
        "sources": sources, "epoch": EPOCH}, sort_keys=True, separators=(",", ":")).encode("ascii"))[:16]
    scratch_root = DEVICE / ".build-scratch"
    scratch_root.mkdir(exist_ok=True)
    restrict_acl(scratch_root, directory=True)
    scratch = Path(tempfile.mkdtemp(prefix="f323-browser-", dir=scratch_root)).resolve()
    restrict_acl(scratch, directory=True)
    try:
        assets, output = scratch / "assets", scratch / "build"
        assets.mkdir()
        packed, inventory_path = assets / "rootfs-product-xz-128k.squashfs", scratch / "rootfs-inventory.json"
        argv = ["python3", wsl_path(ROOT / "tools/f323_browser_compat_rootfs_worker.py"),
                "--source", wsl_path(SOURCE / (SOURCE_BASE + ".rootfs.squashfs")),
                "--overlay", wsl_path(package / "overlay"), "--manifest", wsl_path(package / "manifest.json"),
                "--manifest-sha256", args.package_manifest_sha256, "--build-id", build_id,
                "--image", wsl_path(packed), "--result", wsl_path(inventory_path), "--epoch", str(EPOCH)]
        worker = subprocess.run(["wsl.exe", "-d", args.distro, "-u", "root", "-e", "sh", "-c", shlex.join(argv)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, check=False)
        if worker.returncode:
            raise RuntimeError(worker.stderr or worker.stdout or "F323 worker failed")
        inventory = json.loads(inventory_path.read_text(encoding="ascii"))
        contract.verify_delta(inventory["before"], inventory["after"], inventory["expected_changes"], set(expected_ui))
        for suffix, name in KERNEL_FILES.items():
            shutil.copy2(SOURCE / (SOURCE_BASE + suffix), assets / name)
        settings = {"ASSETS": assets, "OUT": output, "BASE": BASE, "ROOTFS_WINDOW": contract.ROOTFS_WINDOW, "SOURCE_DATE_EPOCH": EPOCH}
        saved, template, log = {name: getattr(compose, name) for name in settings}, compose.f71.TEMPLATE, io.StringIO()
        try:
            for name, value in settings.items():
                setattr(compose, name, value)
            compose.f71.TEMPLATE = SOURCE / (SOURCE_BASE + ".webformat.bin")
            with contextlib.redirect_stdout(log):
                code = compose.main()
        finally:
            compose.f71.TEMPLATE = template
            for name, value in saved.items():
                setattr(compose, name, value)
        if code:
            raise RuntimeError("F323 Bootbase composition failed")
        manifest = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        candidate = output / (BASE + ".webformat.bin")
        data = candidate.read_bytes()
        contract.verify_binary((SOURCE / (SOURCE_BASE + ".webformat.bin")).read_bytes(),
            (SOURCE / (SOURCE_BASE + ".rootfs.squashfs")).read_bytes(), data, (output / (BASE + ".rootfs.squashfs")).read_bytes())
        if manifest["contracts"]["bootbase"] != "PASS":
            raise ValueError("F323 Bootbase contract did not pass")
        for suffix in KERNEL_FILES:
            if sha256(output / (BASE + suffix)) != sha256(SOURCE / (SOURCE_BASE + suffix)):
                raise ValueError("F323 changed a kernel sidecar: " + suffix)
        if {name: sha256(ROOT / "tools" / name) for name in SOURCE_TOOLS} != sources:
            raise ValueError("F323 builder sources changed during compilation")
        full_slot = data + b"\xff" * (contract.SLOT_BYTES - len(data))
        manifest.update({
            "schema": "openmitrastar.f323-browser-compat-candidate/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "PRIVATE_OFFLINE_BROWSER_COMPAT_CANDIDATE_NO_PHYSICAL_AUTHORIZATION",
            "product_version": contract.PRODUCT_VERSION, "firmware_build_id": build_id,
            "candidate_eligible": False, "flash_supported": False, "release_eligible": False,
            "source": {"firmware": "exact F321 based on F314", "candidate_sha256": contract.SOURCE_CANDIDATE,
                       "rootfs_sha256": contract.SOURCE_ROOTFS, "manifest_sha256": contract.SOURCE_MANIFEST,
                       "accepted_record": str(ACCEPTANCE), "accepted_record_sha256": ACCEPTANCE_SHA, "device_queried": False},
            "frontend": {"package": str(package), "manifest_sha256": args.package_manifest_sha256,
                         "build_id": package_manifest["build_id"], "ui_version": contract.UI_VERSION,
                         "presentation": "classic Movistar/Telefonica; original CSS and brand assets unchanged"},
            "device_identity": source_manifest["device_identity"], "web_identity": source_manifest["web_identity"], "web_security": source_manifest["web_security"],
            "change_scope": {"paths": inventory["checks"]["changed_files"], "metadata": inventory["checks"],
                             "kernel_dtb_radios": "byte-identical to F321", "storage_modules_and_boot": "unchanged from F321",
                             "api": "literal brace in config/store GET/HEAD contract; POST unchanged",
                             "api_after_sha256": contract.API_AFTER, "dfs": "legacy observation fallback only; no detector or TX authority added"},
            "inputs": {"source_tools": sources, "epoch": EPOCH},
            "storage": {**source_manifest["storage"], "store_erased_ff": all(v == 255 for v in full_slot[contract.STORE_OFFSET:]),
                        "persistent_writes_enabled": False},
            "physical_validation": {"status": "NOT_RUN", "authorized": False, "required": [
                "review exact F323 promoter and recovery executor", "exact new candidate authorization",
                "fresh target/UART ownership and backup/readback", "persistent boot and pinned management",
                "all 19 browser reads plus legacy DFS display and login/logout", "dual-radio client traffic regression"]},
            "recovery": {**source_manifest["recovery"], "file_only_revalidation": recovery,
                         "record_sha256": sha256(RECOVERY), "working_mtd3_rescue_claimed": False,
                         "f323_to_f321_physical_rollback": "NOT_IMPLEMENTED_OR_PROVEN_BY_THIS_BUILD"},
            "safety": {"hardware_actions": False, "normal_write_target": "physical mtd4/linux_live only after separate exact authorization",
                       "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "mtd6": "logical view; never a physical write target",
                       "flash_go_no_go": "NO_GO_PHYSICAL_PENDING_EXECUTOR_AUTHORIZATION_AND_FRESH_GATES"},
        })
        manifest["layout"]["mtd_mapping"] = "F321 kernel/DTB mapping preserved; rootfs at mtd4 slot offset 0x180000"
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
        shutil.copy2(package / "manifest.json", output / "frontend-package-manifest.json")
        shutil.copy2(inventory_path, output / "rootfs-inventory.json")
        (output / "known_hosts.f323").write_bytes((SOURCE / "known_hosts.f321").read_bytes())
        (output / "composition.log").write_text(log.getvalue(), encoding="utf-8")
        (output / "LAYOUT.md").write_text("# F323 browser compatibility candidate\n\nExact F321 kernel, DTB, radios, startup and credentials.\n"
            "\nChanges: classic TSX legacy DFS observation, config/store status BRE guard, bundle/release identity.\n"
            "\nNO GO for hardware. No flash executor, runtime mutation or new radio capability.\n"
            "\nHistorical recovery: exact F314 to mtd4; a working mtd3 rescue remains unproved.\n", encoding="ascii")
        (output / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(output.iterdir())
            if p.is_file() and p.name != "SHA256SUMS"), encoding="ascii")
        result = {"schema": "openmitrastar.f323-offline-build/v1", "status": "OFFLINE_BUILD_PASS_NO_GO_PHYSICAL",
                  "candidate": str(FINAL / candidate.name), "bytes": len(data), "sha256": sha256(candidate),
                  "full_slot": manifest["artifacts"]["full_slot"], "bootbase": "PASS", "slot_fit": True,
                  "rootfs_headroom_bytes": contract.ROOTFS_WINDOW - manifest["artifacts"]["rootfs_squashfs"]["bytes"],
                  "ui_build_id": package_manifest["build_id"], "firmware_build_id": build_id,
                  "changed_paths": inventory["checks"]["changed_files"], "hardware_actions": False}
        if args.verify_reproducible:
            for suffix in (*KERNEL_FILES, ".rootfs.squashfs", ".webformat.bin"):
                if sha256(output / (BASE + suffix)) != sha256(FINAL / (BASE + suffix)):
                    raise ValueError("F323 reproduction mismatch: " + suffix)
            result["status"] = "REPRODUCIBLE_PASS_NO_GO_PHYSICAL"
        else:
            shutil.copytree(output, FINAL)
            restrict_acl(FINAL, directory=True)
            for path in FINAL.iterdir():
                if path.is_file():
                    restrict_acl(path, directory=False)
        evidence = ROOT / "outputs/preflight" / ("f323-browser-compat-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        print(json.dumps({**result, "report": str(evidence / "result.json")}, indent=2))
    finally:
        if scratch.parent != scratch_root.resolve() or not scratch.name.startswith("f323-browser-"):
            raise RuntimeError("unsafe F323 scratch cleanup")
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
