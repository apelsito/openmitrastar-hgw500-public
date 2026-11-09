"""Rebuild sealed F322 once into new private evidence; never replace the candidate."""
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

import build_f322_shadow_from_f321 as build
import f322_shadow_contract as contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    args = parser.parse_args()
    sealed = build.DEVICE / "f322-f321-shadow-device-bound"
    sealed_manifest = sealed / "manifest.json"
    sealed_manifest_hash = build.sha256(sealed_manifest)
    manifest = json.loads(sealed_manifest.read_text(encoding="ascii"))
    if manifest["schema"] != "openmitrastar.f322-shadow-candidate/v1":
        raise ValueError("unexpected sealed manifest schema")
    for line in (sealed / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        if Path(name).name != name or build.sha256(sealed / name) != expected:
            raise ValueError("sealed F322 evidence changed: " + name)
    for name, expected in manifest["inputs"]["source_tools"].items():
        contract.pinned((build.ROOT / "tools" / name).read_bytes(), expected, name)
    for relative, expected in manifest["inputs"]["helper_hashes"].items():
        contract.pinned((build.VERSION / "overlay" / relative).read_bytes(), expected, relative)
    contract.pinned((build.SOURCE / (build.SOURCE_BASE + ".webformat.bin")).read_bytes(), contract.SOURCE_CANDIDATE, "F321 candidate")
    contract.pinned((build.SOURCE / (build.SOURCE_BASE + ".rootfs.squashfs")).read_bytes(), contract.SOURCE_ROOTFS, "F321 rootfs")
    contract.pinned((build.UI_PACKAGE / "manifest.json").read_bytes(), contract.UI_MANIFEST_SHA256, "UI package")
    build.validate_overlay(build.UI_PACKAGE / "overlay", json.loads((build.UI_PACKAGE / "manifest.json").read_text(encoding="ascii")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = build.DEVICE / ("f322-shadow-repro-" + stamp)
    evidence = build.ROOT / "outputs/preflight" / ("f322-shadow-repro-" + stamp)
    if final.exists() or evidence.exists():
        raise ValueError("refusing to overwrite reproducibility evidence")
    scratch_root = build.DEVICE / ".build-scratch"
    scratch_root.mkdir(exist_ok=True)
    build.restrict_acl(scratch_root, directory=True)
    scratch = Path(tempfile.mkdtemp(prefix="f322-repro-", dir=scratch_root)).resolve()
    build.restrict_acl(scratch, directory=True)
    try:
        assets, output = scratch / "assets", scratch / "build"
        assets.mkdir()
        inventory_path = scratch / "rootfs-inventory.json"
        argv = ["python3", build.wsl_path(build.ROOT / "tools/f322_shadow_rootfs_worker.py"),
                "--source", build.wsl_path(build.SOURCE / (build.SOURCE_BASE + ".rootfs.squashfs")),
                "--overlay", build.wsl_path(build.VERSION / "overlay"), "--donor-start", build.wsl_path(build.DONOR),
                "--module-dir", build.wsl_path(build.MODULES), "--helper-hashes", json.dumps(manifest["inputs"]["helper_hashes"], sort_keys=True),
                "--build-id", manifest["firmware_build_id"], "--image", build.wsl_path(assets / "rootfs-product-xz-128k.squashfs"),
                "--result", build.wsl_path(inventory_path), "--epoch", str(build.EPOCH)]
        worker = subprocess.run(["wsl.exe", "-d", args.distro, "-u", "root", "-e", "sh", "-c", shlex.join(argv)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, check=False)
        if worker.returncode:
            raise RuntimeError(worker.stderr or worker.stdout or "F322 reproducibility worker failed")
        for suffix, name in build.KERNEL_FILES.items():
            shutil.copy2(build.SOURCE / (build.SOURCE_BASE + suffix), assets / name)
        settings = {"ASSETS": assets, "OUT": output, "BASE": build.BASE,
                    "ROOTFS_WINDOW": build.ROOTFS_WINDOW, "SOURCE_DATE_EPOCH": build.EPOCH}
        saved = {name: getattr(build.compose, name) for name in settings}
        template = build.compose.f71.TEMPLATE
        log = io.StringIO()
        try:
            for name, value in settings.items():
                setattr(build.compose, name, value)
            build.compose.f71.TEMPLATE = build.SOURCE / (build.SOURCE_BASE + ".webformat.bin")
            with contextlib.redirect_stdout(log):
                code = build.compose.main()
        finally:
            build.compose.f71.TEMPLATE = template
            for name, value in saved.items():
                setattr(build.compose, name, value)
        if code:
            raise RuntimeError("F322 reproducibility Bootbase composition failed")
        rebuilt = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        comparisons = {}
        for name in ("webformat", "rootfs_squashfs", "full_slot", "kernel_lzma", "dtb", "config"):
            original, new = manifest["artifacts"][name], rebuilt["artifacts"][name]
            if original["sha256"] != new["sha256"] or original["bytes"] != new["bytes"]:
                raise ValueError("F322 reproducibility mismatch: " + name)
            comparisons[name] = {"sha256": new["sha256"], "bytes": new["bytes"], "identical": True}
        for suffix in build.KERNEL_FILES:
            if build.sha256(output / (build.BASE + suffix)) != build.sha256(sealed / (build.BASE + suffix)):
                raise ValueError("F322 kernel sidecar mismatch: " + suffix)
        if inventory_path.read_bytes() != (sealed / "rootfs-inventory.json").read_bytes():
            raise ValueError("F322 complete metadata inventory mismatch")
        if rebuilt["contracts"]["bootbase"] != "PASS" or rebuilt["contracts"]["slot_fit"] is not True:
            raise ValueError("F322 rebuilt Bootbase/slot-fit failed")
        if build.sha256(sealed_manifest) != sealed_manifest_hash:
            raise ValueError("sealed F322 manifest changed during reproducibility check")
        report = {
            "schema": "openmitrastar.f322-reproducibility/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "OFFLINE_REPRODUCIBLE_PASS_NO_GO_PHYSICAL", "hardware_actions": False,
            "candidate_eligible": False, "flash_supported": False, "release_eligible": False,
            "sealed_candidate_directory": str(sealed), "sealed_manifest_sha256": sealed_manifest_hash,
            "sealed_manifest_unchanged": True, "rebuild_directory": str(final),
            "firmware_build_id": manifest["firmware_build_id"], "ui_build_id": contract.UI_BUILD_ID,
            "source_tools_and_helpers_match_first_build": True, "source_date_epoch": build.EPOCH,
            "kernel_compilation": False, "repack_count_this_run": 1, "processors": 1,
            "artifact_comparisons": comparisons, "full_slot_crc32": rebuilt["artifacts"]["full_slot"]["crc32"],
            "full_metadata_inventory_identical": True, "bootbase": "PASS", "slot_fit": True,
            "runner_sha256": build.sha256(Path(__file__)), "physical_validation": "NOT_RUN",
        }
        (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
        shutil.copy2(inventory_path, output / "rootfs-inventory.json")
        (output / "composition.log").write_text(log.getvalue(), encoding="utf-8")
        (output / "LAYOUT.md").write_text("# F322 independent offline rebuild\n\n"
            "This directory is new reproducibility evidence, not a promoted firmware candidate.\n"
            "All firmware hashes and rootfs metadata match sealed F322. NO GO for physical execution.\n", encoding="ascii")
        (output / "SHA256SUMS").write_text("".join(f"{build.sha256(path)}  {path.name}\n" for path in sorted(output.iterdir())
                                                  if path.is_file() and path.name != "SHA256SUMS"), encoding="ascii")
        shutil.copytree(output, final)
        build.restrict_acl(final, directory=True)
        for path in final.iterdir():
            if path.is_file():
                build.restrict_acl(path, directory=False)
        for line in (final / "SHA256SUMS").read_text(encoding="ascii").splitlines():
            expected, name = line.split("  ", 1)
            if build.sha256(final / name) != expected:
                raise ValueError("copied reproducibility artifact mismatch: " + name)
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
        print(json.dumps({"report": str(evidence / "result.json"), **report}, indent=2))
    finally:
        if scratch.parent != scratch_root.resolve() or not scratch.name.startswith("f322-repro-"):
            raise RuntimeError("unsafe F322 reproducibility scratch cleanup")
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
