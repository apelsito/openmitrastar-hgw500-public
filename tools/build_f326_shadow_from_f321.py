"""Build one offline F325 shadow image without compiling or contacting hardware."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

import compose_f164_squashfs_product as compose
import f326_shadow_contract as contract
from build_f321_classic_ui_candidate import EPOCH, KERNEL_FILES, ROOTFS_WINDOW, SLOT_BYTES, STORE_OFFSET, wsl_path
from init_lyoko_device_host_key import restrict_acl
from lyoko_web_rootfs_worker import sha256, validate_overlay


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
SOURCE = DEVICE / "f321-f314-device-bound"
SOURCE_BASE = "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
BASE = "openmitrastar-linux510-f326-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
VERSION = ROOT / "versions/lyoko-foundation-6.9.4-f326-radar-once"
DONOR = ROOT / "versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start"
MODULES = ROOT / "outputs/kernel-port/f325-radar-once-20260919T000320492832Z"
UI_PACKAGE = ROOT / "outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    args = parser.parse_args()
    final = DEVICE / "f326-f321-radar-once-device-bound"
    if final.exists():
        raise ValueError("refusing to replace F325; changed firmware requires a new candidate version")
    contract.pinned((SOURCE / (SOURCE_BASE + ".webformat.bin")).read_bytes(), contract.SOURCE_CANDIDATE, "F321 candidate")
    contract.pinned((SOURCE / (SOURCE_BASE + ".rootfs.squashfs")).read_bytes(), contract.SOURCE_ROOTFS, "F321 rootfs")
    source_manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="ascii"))
    contract.pinned((UI_PACKAGE / "manifest.json").read_bytes(), contract.UI_MANIFEST_SHA256, "UI package")
    ui_manifest = json.loads((UI_PACKAGE / "manifest.json").read_text(encoding="ascii"))
    validate_overlay(UI_PACKAGE / "overlay", ui_manifest)
    if ui_manifest["build_id"] != contract.UI_BUILD_ID or source_manifest["frontend"]["build_id"] != contract.UI_BUILD_ID:
        raise ValueError("F325 must retain the exact accepted UI package")
    module_manifest = json.loads((MODULES / "manifest.json").read_text(encoding="ascii"))
    if module_manifest["status"] != "PASS_OFFLINE_DIAGNOSTIC_MODULE" or module_manifest["authority"] != {"radar_start": False, "radar_get_status": False, "callbacks": 0, "dfs_tx": False}:
        raise ValueError("F325 provider lacks the single-boot non-authoritative contract")
    if module_manifest["qdrv"]["sha256"] != contract.QDRV_SHA256 or module_manifest["provider"]["sha256"] != contract.PROVIDER_SHA256:
        raise ValueError("F325 exact module bindings changed")
    for row in module_manifest["sources"]:
        if sha256(ROOT / row["path"]) != row["sha256"]:
            raise ValueError("F325 module source changed after qualification")
    f315_manifest = json.loads((DEVICE / "f315-device-bound/manifest.json").read_text(encoding="ascii"))
    if source_manifest["artifacts"]["kernel_lzma"]["sha256"] != f315_manifest["artifacts"]["kernel_lzma"]["sha256"]:
        raise ValueError("F315 donor does not share the F321 kernel")
    module_inputs = {"qtn_radar_shadow_f315.ko": contract.PROVIDER_SHA256, "qdrv-f315-external-radar.ko": contract.QDRV_SHA256}
    for filename, digest in module_inputs.items():
        contract.pinned((MODULES / filename).read_bytes(), digest, filename)
    contract.pinned(DONOR.read_bytes(), contract.DONOR_START, "donor bootstrap")
    helper_hashes = {path: sha256(VERSION / "overlay" / path) for path in ("usr/sbin/om-dfs-status", "usr/sbin/om-radarctl", "usr/sbin/om-radar-once")}
    sources = {path.name: sha256(path) for path in [Path(__file__), ROOT / "tools/f326_shadow_contract.py", ROOT / "tools/f326_shadow_rootfs_worker.py"]}
    build_id = contract.digest(json.dumps({"base": contract.SOURCE_CANDIDATE, "modules": module_inputs, "helpers": helper_hashes, "sources": sources}, sort_keys=True).encode("ascii"))[:16]
    scratch_root = DEVICE / ".build-scratch"
    scratch_root.mkdir(exist_ok=True)
    restrict_acl(scratch_root, directory=True)
    scratch = Path(tempfile.mkdtemp(prefix="f326-shadow-", dir=scratch_root)).resolve()
    restrict_acl(scratch, directory=True)
    try:
        assets, output = scratch / "assets", scratch / "build"
        assets.mkdir()
        packed, inventory_path = assets / "rootfs-product-xz-128k.squashfs", scratch / "rootfs-inventory.json"
        argv = ["python3", wsl_path(ROOT / "tools/f326_shadow_rootfs_worker.py"), "--source", wsl_path(SOURCE / (SOURCE_BASE + ".rootfs.squashfs")),
                "--overlay", wsl_path(VERSION / "overlay"), "--donor-start", wsl_path(DONOR), "--module-dir", wsl_path(MODULES),
                "--helper-hashes", json.dumps(helper_hashes, sort_keys=True), "--build-id", build_id,
                "--image", wsl_path(packed), "--result", wsl_path(inventory_path), "--epoch", str(EPOCH)]
        worker = subprocess.run(["wsl.exe", "-d", args.distro, "-u", "root", "-e", "sh", "-c", shlex.join(argv)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, check=False)
        if worker.returncode:
            raise RuntimeError(worker.stderr or worker.stdout or "F325 worker failed")
        inventory = json.loads(inventory_path.read_text(encoding="ascii"))
        if not inventory.get("catalog_verification"):
            raise ValueError("F326 requires complete artifact-catalog verification before and after packing")
        for suffix, name in KERNEL_FILES.items():
            shutil.copy2(SOURCE / (SOURCE_BASE + suffix), assets / name)
        settings = {"ASSETS": assets, "OUT": output, "BASE": BASE, "ROOTFS_WINDOW": ROOTFS_WINDOW, "SOURCE_DATE_EPOCH": EPOCH}
        saved = {name: getattr(compose, name) for name in settings}
        template = compose.f71.TEMPLATE
        log = io.StringIO()
        try:
            for name, value in settings.items(): setattr(compose, name, value)
            compose.f71.TEMPLATE = SOURCE / (SOURCE_BASE + ".webformat.bin")
            with contextlib.redirect_stdout(log): code = compose.main()
        finally:
            compose.f71.TEMPLATE = template
            for name, value in saved.items(): setattr(compose, name, value)
        if code: raise RuntimeError("F325 Bootbase composition failed")
        manifest = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        candidate = output / (BASE + ".webformat.bin")
        data = candidate.read_bytes()
        source_data = (SOURCE / (SOURCE_BASE + ".webformat.bin")).read_bytes()
        if data[64:0x180000] != source_data[64:0x180000] or len(data) > STORE_OFFSET or manifest["contracts"]["bootbase"] != "PASS":
            raise ValueError("F325 kernel/header, rootfs fit or Bootbase contract failed")
        for suffix in KERNEL_FILES:
            if sha256(output / (BASE + suffix)) != sha256(SOURCE / (SOURCE_BASE + suffix)):
                raise ValueError("F325 changed a kernel sidecar")
        # All credentials and UI metadata are covered by the native full-tree inventory comparison.
        full_slot = data + b"\xff" * (SLOT_BYTES - len(data))
        manifest.update({
            "schema": "openmitrastar.f326-shadow-candidate/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "PRIVATE_SINGLE_BOOT_RADAR_DIAGNOSTIC_UNARMED_FULL_RECOVERY_REQUIRED",
            "product_version": contract.PRODUCT_VERSION, "firmware_build_id": build_id,
            "candidate_eligible": False, "flash_supported": False, "release_eligible": False,
            "source": {"firmware": "exact local F321 from F314", "candidate_sha256": contract.SOURCE_CANDIDATE,
                       "rootfs_sha256": contract.SOURCE_ROOTFS, "device_queried": False, "f321_physical_acceptance_required": True},
            "frontend": {**source_manifest["frontend"], "byte_identical_to_f321": True},
            "artifact_catalog": inventory["catalog_verification"],
            "device_identity": source_manifest["device_identity"], "web_identity": source_manifest["web_identity"], "web_security": source_manifest["web_security"],
            "shadow": {"provider_sha256": contract.PROVIDER_SHA256, "qdrv_sha256": contract.QDRV_SHA256, "abi_exports": 18,
                       "existing_offline_abi_contract": "F325 provider rebuilt twice; F315 qdrv ABI dependency and F321 kernel preserved",
                       "donor_manifest_sha256": sha256(MODULES / "manifest.json"),
                       "shadow_enable": True, "shadow_arm_on_boot": False, "automatic_arm": False,
                       "radar_start": False, "radar_get_status": False, "callbacks": 0, "dfs_tx_authorized": False,
                       "authoritative_enable": False, "weather_enable": False, "poll_interval_ms": 50, "sample_limit": 18,
                       "physical_observation": "NOT_RUN", "single_arm_per_boot": True, "sample_window_ms": 20000,
                       "hardware_restore_proven": False, "recovery_after_arm": "FULL_BOOT_AND_EXACT_F321_RESTORE",
                       "module_self_pin_after_configuration": True},
            "change_scope": {"paths": inventory["checks"]["changed_files"], "metadata": inventory["checks"],
                             "kernel_dtb": "byte-identical to F321", "radio_controls": "F321 read controls preserved; radio configuration transactions locked during diagnostic image",
                             "api": "one authenticated read-only DFS route added; all existing bytes retained",
                             "runtime_arming_executor": "om-radar-once requires explicit ACK; separately qualified host campaign still required"},
            "inputs": {"source_tools": sources, "helper_hashes": helper_hashes, "donor_start_sha256": contract.DONOR_START},
            "reproducibility": {"pinned_inputs_and_epoch": True, "second_build": "NOT_RUN_HOST_UART_CAMPAIGN_ACTIVE", "kernel_compilation": False},
            "storage": {**source_manifest["storage"], "store_erased_ff": all(byte == 255 for byte in full_slot[STORE_OFFSET:]), "persistent_writes_enabled": False},
            "physical_validation": {"status": "NOT_RUN", "required": ["accept F321 baseline", "review a separately versioned shadow gate and rollback",
                "exact image authorization and current board/slot/recovery checks", "non-DFS boot with acquisition unarmed",
                "dual-radio/client regression", "explicit bounded shadow arm and temporal acquisition evidence", "zero callbacks and no fatal markers"]},
            "recovery": source_manifest["recovery"],
            "safety": {"hardware_actions": False, "normal_write_target": "mtd4/linux_live only after applicable authorization",
                       "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "mtd6": "logical view, never a physical write target",
                       "flash_go_no_go": "NO_GO_EXECUTOR_AND_RECOVERY_QUALIFICATION", "native_detector": "not included; F325 bounded acquisition experiment only"},
        })
        manifest["layout"]["mtd_mapping"] = "F321 kernel/DTB mapping preserved; rootfs at physical mtd4 slot offset 0x180000"
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
        shutil.copy2(inventory_path, output / "rootfs-inventory.json")
        (output / "known_hosts.f326").write_bytes((SOURCE / "known_hosts.f321").read_bytes())
        (output / "composition.log").write_text(log.getvalue(), encoding="utf-8")
        (output / "LAYOUT.md").write_text("# F326 catalogue-repaired single-boot candidate\n\nExact F321 kernel/UI with the verified F315 external qdrv and shadow provider.\n"
            "\nAcquisition is unarmed at boot; callback authority and DFS transmission remain denied.\n"
            "\nNO GO for physical execution. No arming or flash executor is included.\n", encoding="ascii")
        (output / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file() and p.name != "SHA256SUMS"), encoding="ascii")
        shutil.copytree(output, final)
        restrict_acl(final, directory=True)
        for path in final.iterdir():
            if path.is_file(): restrict_acl(path, directory=False)
        result = {"schema": "openmitrastar.f326-offline-build/v1", "status": "OFFLINE_BUILD_PASS_NO_GO_PHYSICAL",
                  "output": str(final), "candidate": str(final / candidate.name), "bytes": len(data), "sha256": sha256(candidate),
                  "full_slot": manifest["artifacts"]["full_slot"], "bootbase": "PASS", "slot_fit": True,
                  "rootfs_headroom_bytes": ROOTFS_WINDOW - manifest["artifacts"]["rootfs_squashfs"]["bytes"],
                  "ui_build_id": contract.UI_BUILD_ID, "firmware_build_id": build_id, "shadow_armed": False, "hardware_actions": False}
        evidence = ROOT / "outputs/preflight" / ("f326-shadow-build-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        print(json.dumps({**result, "report": str(evidence / "result.json")}, indent=2))
    finally:
        if scratch.parent != scratch_root.resolve() or not scratch.name.startswith("f326-shadow-"):
            raise RuntimeError("unsafe F325 scratch cleanup")
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
