#!/usr/bin/env python3
"""Guarded Realtek iteration loop for OpenMitraStar.

Default behavior is a read-only dry-run.  Offline compilation/bundling and
volatile RAM hardware execution require separate explicit flags.  Flash and
persistent writes are intentionally not implemented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT
    / "outputs"
    / "kernel-port"
    / "realtek-loop"
    / "current-RAM-ONLY-NO-FLASH"
)
BUILD_HELPER = ROOT / "tools" / "build_realtek_8192ee_incremental.sh"
RAM_HELPER = ROOT / "tools" / "run_realtek_ram_probe.ps1"
ACK = "OPENMITRASTAR_RAM_ONLY_NO_FLASH"


class LoopError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def windows_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive or not re.fullmatch(r"[a-z]", drive):
        raise LoopError(f"cannot translate path to WSL: {resolved}")
    tail = resolved.as_posix().split(":", 1)[1].lstrip("/")
    return f"/mnt/{drive}/{tail}"


def load_and_validate_bundle(bundle: Path) -> dict[str, Any]:
    allowed = ROOT / "outputs" / "kernel-port" / "realtek-loop"
    if not path_within(bundle, allowed):
        raise LoopError(f"bundle must remain below {allowed}")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise LoopError(f"bundle manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "RAM-ONLY-NO-FLASH":
        raise LoopError("bundle classification is not RAM-ONLY-NO-FLASH")
    if manifest.get("candidate_eligible") is not False:
        raise LoopError("bundle unexpectedly marks itself candidate eligible")
    safety = manifest.get("safety", {})
    forbidden = (
        safety.get("network_used"),
        safety.get("uart_used"),
        safety.get("router_accessed"),
        safety.get("flash_supported"),
        safety.get("persistent_writes_supported"),
    )
    if any(forbidden):
        raise LoopError("offline bundle manifest reports a forbidden side effect")

    artifact_names: set[str] = set()
    for artifact in manifest.get("artifacts", []):
        relative = Path(artifact["path"])
        candidate = (bundle / relative).resolve()
        if not path_within(candidate, bundle) or not candidate.is_file():
            raise LoopError(f"missing/escaping artifact: {relative}")
        if candidate.stat().st_size != int(artifact["bytes"]):
            raise LoopError(f"size mismatch: {relative}")
        if sha256(candidate) != artifact["sha256"]:
            raise LoopError(f"SHA-256 mismatch: {relative}")
        artifact_names.add(relative.as_posix())

    expected = {
        "ram_insmod",
        "modules/ctr.ko",
        "modules/ccm.ko",
        "modules/cmac.ko",
        "modules/cfg80211.ko",
        "modules/libarc4.ko",
        "modules/mac80211.ko",
        "modules/rtlwifi.ko",
        "modules/btcoexist.ko",
        "modules/rtl_pci.ko",
        "modules/rtl8192ee.ko",
        "firmware/regulatory.db",
        "firmware/rtlwifi/rtl8192eefw.bin",
    }
    if artifact_names != expected:
        raise LoopError(
            "bundle artifact set differs from the narrow Realtek runtime set: "
            f"missing={sorted(expected - artifact_names)} "
            f"extra={sorted(artifact_names - expected)}"
        )

    upload_manifest = bundle / "UPLOAD_SHA256SUMS"
    if not upload_manifest.is_file():
        raise LoopError("UPLOAD_SHA256SUMS missing")
    upload_names: set[str] = set()
    for line in upload_manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line)
        if not match:
            raise LoopError(f"malformed upload hash line: {line!r}")
        expected_hash, relative_text = match.groups()
        relative = Path(relative_text)
        candidate = bundle / relative
        if not candidate.is_file() or sha256(candidate) != expected_hash:
            raise LoopError(f"upload manifest mismatch: {relative_text}")
        upload_names.add(relative.as_posix())
    if upload_names != expected:
        raise LoopError("UPLOAD_SHA256SUMS does not cover the exact artifact set")

    regulatory = manifest.get("regulatory_database", {})
    if regulatory != {
        "path": "firmware/regulatory.db",
        "sha256": "e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393",
        "install_before_module": "cfg80211.ko",
        "force_reg_after_load": False,
    }:
        raise LoopError("regulatory database pre-cfg80211 contract mismatch")

    base = manifest.get("base_ram_image", {})
    base_path = (ROOT / base.get("path", "")).resolve()
    if base.get("classification") != "RAM-ONLY" or not base_path.is_file():
        raise LoopError("base RAM image is missing or incorrectly classified")
    if base_path.stat().st_size != int(base["bytes"]):
        raise LoopError("base RAM image size changed")
    if sha256(base_path) != base["sha256"]:
        raise LoopError("base RAM image hash changed")
    return manifest


def run_offline(args: argparse.Namespace, bundle: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "TOPAZ_KERNEL_SRC": args.kernel_source,
            "TOPAZ_BUILD_ROOT": args.build_root,
            "TOPAZ_RADIOHW_BUILD": f"{args.build_root.rstrip('/')}/radiohw-probe",
            "TOPAZ_JOBS": str(args.jobs),
            "REALTEK_SKIP_BUILD": "1" if args.skip_build else "0",
            "REALTEK_BUNDLE_DIR": windows_to_wsl(bundle),
        }
    )
    command = [
        "wsl.exe",
        "-d",
        args.distro,
        "-u",
        args.wsl_user,
        "-e",
        "env",
    ]
    command.extend(f"{key}={env[key]}" for key in (
        "TOPAZ_KERNEL_SRC",
        "TOPAZ_BUILD_ROOT",
        "TOPAZ_RADIOHW_BUILD",
        "TOPAZ_JOBS",
        "REALTEK_SKIP_BUILD",
        "REALTEK_BUNDLE_DIR",
    ))
    command.extend(["sh", windows_to_wsl(BUILD_HELPER)])
    print("REALTEK_LOOP_OFFLINE_START")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise LoopError(f"offline build/bundle failed with exit={completed.returncode}")
    load_and_validate_bundle(bundle)
    print(f"REALTEK_LOOP_OFFLINE_PASS bundle={bundle}")


def run_ram(args: argparse.Namespace, bundle: Path) -> None:
    if args.ack_ram_only != ACK:
        raise LoopError(f"--execute-ram requires exact --ack-ram-only {ACK}")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RAM_HELPER),
        "-ExecuteRam",
        "-Acknowledge",
        ACK,
        "-Bundle",
        str(bundle),
        "-Port",
        args.uart_port,
        "-ServerIp",
        args.server_ip,
        "-ClientIp",
        args.client_ip,
        "-LoadAddress",
        args.load_address,
        "-CaptureSeconds",
        str(args.capture_seconds),
        "-TimeoutSeconds",
        str(args.timeout_seconds),
    ]
    if args.skip_boot:
        command.append("-SkipBoot")
    print("REALTEK_LOOP_RAM_START classification=RAM-ONLY-NO-FLASH")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise LoopError(f"RAM hardware loop failed with exit={completed.returncode}")
    print("REALTEK_LOOP_RAM_PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Incremental Realtek build/static/bundle/RAM-probe loop. "
            "With no execution flags it is a dry-run."
        )
    )
    parser.add_argument("--execute-offline", action="store_true")
    parser.add_argument("--execute-ram", action="store_true")
    parser.add_argument("--ack-ram-only", default="")
    parser.add_argument("--skip-build", action="store_true",
                        help="re-run static gates/bundling without invoking make")
    parser.add_argument(
        "--skip-boot",
        action="store_true",
        help="reuse an already-live matching RAM kernel; still validates and uploads the bundle",
    )
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--wsl-user", default="root")
    parser.add_argument(
        "--kernel-source", default="/home/user/mitrastar-linux-5.10.260"
    )
    parser.add_argument("--build-root", default="/home/user/openmitrastar-build")
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--uart-port", default="COM3")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--client-ip", default="192.168.1.200")
    parser.add_argument("--load-address", default="0x83000000")
    parser.add_argument("--capture-seconds", type=int, default=75)
    parser.add_argument("--timeout-seconds", type=int, default=480)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.jobs < 1 or args.jobs > 32:
        raise LoopError("--jobs must be between 1 and 32")
    if not re.fullmatch(r"COM[0-9]+", args.uart_port, re.IGNORECASE):
        raise LoopError("--uart-port must look like COM3")
    if not re.fullmatch(r"0x[0-9a-fA-F]+", args.load_address):
        raise LoopError("--load-address must be hexadecimal")
    if args.skip_build and not args.execute_offline:
        raise LoopError("--skip-build is meaningful only with --execute-offline")
    if args.skip_boot and not args.execute_ram:
        raise LoopError("--skip-boot requires --execute-ram")

    bundle = args.bundle.resolve()
    plan = {
        "schema": "openmitrastar.realtek-loop-plan/v1",
        "mode": (
            "OFFLINE_AND_RAM"
            if args.execute_offline and args.execute_ram
            else "OFFLINE_ONLY"
            if args.execute_offline
            else "RAM_ONLY"
            if args.execute_ram
            else "DRY_RUN"
        ),
        "bundle": str(bundle),
        "stages": [
            "incremental module build (offline, existing Kbuild cache)",
            "ARC/vermagic/alias/firmware/unaligned-source static gates",
            "RAM-only bundle plus SHA-256 manifests",
            "explicitly gated RAM boot/TFTP/upload/UART/targeted probe",
        ],
        "safety": {
            "default_dry_run": True,
            "network_fetch_supported": False,
            "flash_supported": False,
            "persistent_writes_supported": False,
            "hardware_requires_flag": "--execute-ram",
            "hardware_requires_ack": ACK,
        },
    }
    print(json.dumps(plan, indent=2, sort_keys=True))

    if not args.execute_offline and not args.execute_ram:
        if (bundle / "manifest.json").is_file():
            load_and_validate_bundle(bundle)
            print("REALTEK_LOOP_DRY_RUN_BUNDLE_VALID=1")
        else:
            print("REALTEK_LOOP_DRY_RUN_BUNDLE_VALID=0 reason=not-built")
        print("REALTEK_LOOP_DRY_RUN_PASS=1")
        return 0

    if args.execute_offline:
        run_offline(args, bundle)
    else:
        load_and_validate_bundle(bundle)
    if args.execute_ram:
        run_ram(args, bundle)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LoopError as exc:
        print(f"REALTEK_LOOP_REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
