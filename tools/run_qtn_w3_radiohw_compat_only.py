#!/usr/bin/env python3
"""Verify, upload and run the signed radiohw W3 compatibility-only ladder."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/quantenna-v89-radiohw-signed-bundle-20260818"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-v89-radiohw-routed-20260818-2100/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna"
ACK = "OPENMITRASTAR_QTN_W3_COMPAT_ONLY"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    args = parser.parse_args()

    manifest = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_SIGNED_ARTIFACT.json"
    run([sys.executable, "tools/qtn_w3_artifact_gate.py", "--manifest", str(manifest), "--verify"])
    if not args.execute:
        print(f"DRY_RUN_PASS next='--execute --ack {ACK}' host={args.host}")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"refusing execution: require --ack {ACK}")

    remote_root = "/tmp/w3-qtn-radiohw/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna"
    run([sys.executable, "tools/ramssh_exec.py",
         f"rm -rf /tmp/w3-qtn-radiohw; mkdir -p {remote_root}/platform/ruby {remote_root}/platform/topaz",
         "--host", args.host, "--timeout", "20"])
    module_paths = [
        "platform/ruby/qtn_pm_qos_compat.ko",
        "platform/ruby/board_compat.ko",
        "platform/ruby/runtime_compat.ko",
        "platform/ruby/qtn_platform_support.ko",
        "platform/ruby/iputil.ko",
        "platform/ruby/dmautil.ko",
        "platform/topaz/switch_vlan.ko",
        "platform/topaz/fwt_if.ko",
    ]
    uploads = [
        (BUNDLE / "W3_RUNTIME_GATE.env", "/tmp/W3_RUNTIME_GATE.env", "0600"),
        (ROOT / "tools/qtn_w3_pre_mmio_ladder.sh", "/tmp/qtn_w3_pre_mmio_ladder.sh", "0700"),
    ] + [
        (ARTIFACT / relative, f"{remote_root}/{relative}", "0600")
        for relative in module_paths
    ]
    for source, destination, mode in uploads:
        run([sys.executable, "tools/ramssh_upload.py", str(source), destination,
             "--host", args.host, "--mode", mode])
    remote = (
        "set -eu; d=/tmp/w3-qtn-radiohw; "
        "sed -i 's/\\r$//' /tmp/W3_RUNTIME_GATE.env /tmp/qtn_w3_pre_mmio_ladder.sh; set +e; "
        "QTN_MODULE_ROOT=\"$d/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna\" "
        "W3_ALLOW_COMPAT_MODULES=OPENMITRASTAR_W3_COMPAT_ONLY "
        "sh /tmp/qtn_w3_pre_mmio_ladder.sh /tmp/W3_RUNTIME_GATE.env; rc=$?; set -e; "
        "test \"$rc\" -eq 42; echo W3_RADIOHW_COMPAT_ONLY_PASS stop_code=$rc; "
        "grep -E '^(qtn_pm_qos_compat|board_compat|runtime_compat|qtn_platform_support|iputil|dmautil|switch_vlan|fwt_if) ' /proc/modules; "
        "for m in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat; do "
        "rmmod \"$m\" || exit 43; done; "
        "if grep -Eq '^(qtn_pm_qos_compat|board_compat|runtime_compat|qtn_platform_support|iputil|dmautil|switch_vlan|fwt_if) ' /proc/modules; then exit 44; fi; "
        "echo W3_RADIOHW_COMPAT_CLEANUP_PASS"
    )
    run([sys.executable, "tools/ramssh_exec.py", remote, "--host", args.host, "--timeout", "90"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
