#!/usr/bin/env python3

"""Offline verifier for the HGW500 5 GHz LED post-baseline artifact.

This runner intentionally has no execute, serial, network, TFTP or flash mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "outputs/kernel-port/hgw500-controls-5g-postbaseline-20260819"
BASELINE = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-sequential-20260819"
BASELINE_QDRV = BASELINE / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
BASELINE_QDRV_SHA = "32956592ad32a6eadf12632e84495acaa18dd668184959c23acee0b8d0e31000"
BASELINE_MANIFEST_SHA = "2cbafb7ca596db1a35b21191f40df7a2404f5af53647a9424091bf218e9f8ac8"


class GateError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: pathlib.Path, expected: str) -> None:
    if not path.is_file():
        raise GateError(f"missing file: {path}")
    actual = sha256(path)
    if actual != expected:
        raise GateError(f"hash mismatch: {path}: expected={expected} actual={actual}")


def parse_module_manifest(path: pathlib.Path) -> dict[str, str]:
    rows = path.read_text(encoding="utf-8").splitlines()
    if not rows or not rows[0].startswith("module\tsha256\t"):
        raise GateError(f"invalid module manifest: {path}")
    result: dict[str, str] = {}
    for row in rows[1:]:
        fields = row.split("\t")
        if len(fields) < 2:
            raise GateError(f"invalid module row: {row}")
        result[fields[0]] = fields[1]
    return result


def verify_sha256sums(artifact: pathlib.Path) -> int:
    sums = artifact / "SHA256SUMS"
    if not sums.is_file():
        raise GateError("SHA256SUMS missing")
    checked = 0
    for row in sums.read_text(encoding="utf-8").splitlines():
        expected, rel = row.split(None, 1)
        rel = rel.lstrip("* ")
        require_hash(artifact / rel, expected)
        checked += 1
    if checked < 10:
        raise GateError(f"insufficient checksum coverage: {checked}")
    return checked


def run_gate(artifact: pathlib.Path) -> dict[str, object]:
    artifact = artifact.resolve()
    if artifact == BASELINE.resolve():
        raise GateError("post-baseline artifact must not alias the approved baseline")

    require_hash(BASELINE_QDRV, BASELINE_QDRV_SHA)
    require_hash(BASELINE / "module-manifest.tsv", BASELINE_MANIFEST_SHA)

    manifest_path = artifact / "manifest.json"
    if not manifest_path.is_file():
        raise GateError(f"manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "openmitrastar.hgw500-wlan5g-controls-postbaseline/v1":
        raise GateError("unexpected manifest schema")
    if manifest.get("classification") != "OFFLINE-POSTBASELINE-NO-HARDWARE-NO-FLASH":
        raise GateError("artifact is not classified offline/no-flash")

    execution = manifest.get("execution", {})
    expected_execution = {
        "hardware_executed": False,
        "com3_opened": False,
        "network_mutated": False,
        "flash_writes": 0,
    }
    if execution != expected_execution:
        raise GateError(f"unsafe execution record: {execution}")

    baseline = manifest.get("baseline", {})
    if baseline.get("qdrv_sha256") != BASELINE_QDRV_SHA or not baseline.get("immutable"):
        raise GateError("approved qdrv baseline identity not preserved")

    post = manifest.get("postbaseline", {})
    if post.get("non_qdrv_module_delta") != 0:
        raise GateError("post-baseline artifact changes non-qdrv modules")
    if (post.get("led_gpio"), post.get("led_active_high"), post.get("led_interface")) != (1, True, "wifi0"):
        raise GateError("GPIO1/wifi0 LED contract mismatch")

    for rel, metadata in manifest.get("artifacts", {}).items():
        path = artifact / rel
        if path.stat().st_size != metadata["size"]:
            raise GateError(f"size mismatch: {rel}")
        require_hash(path, metadata["sha256"])

    patch = artifact / "controls/openmitrastar-wlan5g-led-carrier.patch"
    checked = subprocess.run(
        ["git", "apply", "--check", "--whitespace=error-all", str(patch)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if checked.returncode:
        raise GateError(f"patch preimage/apply check failed: {checked.stdout.strip()}")

    baseline_modules = parse_module_manifest(BASELINE / "module-manifest.tsv")
    post_modules = parse_module_manifest(artifact / "module-manifest.tsv")
    if set(baseline_modules) != set(post_modules) or len(post_modules) != 25:
        raise GateError("module inventory changed")
    changed = [name for name in post_modules if post_modules[name] != baseline_modules[name]]
    if changed != ["qdrv/qdrv.ko"]:
        raise GateError(f"unexpected module delta: {changed}")

    qdrv = artifact / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
    qdrv_data = qdrv.read_bytes()
    for marker in (
        b"OMQDRVHR stage=deferred reason=no-vap",
        b"OMQDRVLED stage=vnet-start carrier=off",
        b"OMQDRVLED stage=ap-state carrier=%s",
    ):
        if marker not in qdrv_data:
            raise GateError(f"qdrv marker missing: {marker!r}")
    if sha256(qdrv) == BASELINE_QDRV_SHA:
        raise GateError("post-baseline qdrv did not change")

    archive = artifact / "quantenna-rootfs-overlay.tar.gz"
    with tarfile.open(archive, "r:gz") as bundle:
        member = bundle.extractfile(
            "./lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
        )
        if member is None:
            raise GateError("qdrv missing from deterministic rootfs archive")
        archived_qdrv_sha = hashlib.sha256(member.read()).hexdigest()
    if archived_qdrv_sha != sha256(qdrv):
        raise GateError("rootfs archive still contains the baseline qdrv")

    checksum_count = verify_sha256sums(artifact)
    return {
        "pass": True,
        "classification": manifest["classification"],
        "baseline_qdrv_sha256": BASELINE_QDRV_SHA,
        "postbaseline_qdrv_sha256": sha256(qdrv),
        "module_delta": changed,
        "checksum_files": checksum_count,
        "hardware_executed": False,
        "flash_writes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=pathlib.Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = run_gate(args.artifact)
    except (GateError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"W1_LED5G_CONTROLS_POSTBASELINE_DRY_RUN_PASS=0 error={exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    print("W1_LED5G_CONTROLS_POSTBASELINE_DRY_RUN_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
