#!/usr/bin/env python3
"""Compose F172 from the F171 rootfs and NAPI-128 EMAC kernel."""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import subprocess
from pathlib import Path

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs/kernel-port/f172-emac-napi128-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f172-emac-napi128-from-f171/build"
BASE = "openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH"
F171_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build"
F171_BASE = "openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_binary_napi_weight(vmlinux: Path) -> dict[str, object]:
    vmlinux_wsl = "/workspace/user-home/Desktop/MitraStar/" + vmlinux.relative_to(ROOT).as_posix()
    objdump = "/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump"
    command = (
        f'"{objdump}" -dr "{vmlinux_wsl}" | '
        "sed -n '/<qtn_emac_probe>/,/^$/p'"
    )
    proc = subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    lines = proc.stdout.splitlines()
    call_index = next((i for i, line in enumerate(lines) if "<netif_napi_add>" in line), None)
    if call_index is None:
        raise SystemExit("F172 binary contract missing netif_napi_add call")
    window = lines[max(0, call_index - 16):call_index + 2]
    if not any(re.search(r"\bmov_s\s+r3,0x80\b", line) for line in window):
        raise SystemExit("F172 binary contract missing ARC r3=0x80 NAPI weight")
    report = {
        "schema": "openmitrastar.f172-napi-binary-contract/v1",
        "result": "PASS",
        "function": "qtn_emac_probe",
        "callee": "netif_napi_add",
        "arc_argument_register": "r3",
        "immediate": "0x80",
        "decimal": 128,
        "evidence": window,
    }
    path = OUT / "napi128-binary-contract.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


@contextlib.contextmanager
def variant_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    with variant_context():
        rc = engine.main()
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source_manifest = F171_BUILD / "manifest.json"
    source = json.loads(source_manifest.read_text(encoding="ascii"))
    source_rootfs = F171_BUILD / f"{F171_BASE}.rootfs.squashfs"
    output_rootfs = OUT / f"{BASE}.rootfs.squashfs"
    output_vmlinux = OUT / f"{BASE}.vmlinux"
    if sha256(source_rootfs) != sha256(output_rootfs):
        raise SystemExit("F172 rootfs differs from F171")
    binary_contract = verify_binary_napi_weight(output_vmlinux)

    manifest.update({
        "schema": "openmitrastar.f172-emac-napi128-from-f171/v1",
        "classification": "F172_EMAC_NAPI128_OFFLINE_FLASH_CANDIDATE_UNVALIDATED",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "firmware": "F171 offline candidate; F170 currently installed",
            "build_dir": str(F171_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest),
            "rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
            "kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
        },
        "hypothesis": {
            "claim": "64-packet NAPI service leaves burst backlog on the 128-descriptor RX ring, allowing NO_RX_DESC starvation before the next softirq pass",
            "physical_evidence": {
                "dma_no_rx_desc_samples_delta": 617,
                "irq_no_rx_desc_delta": 15,
                "napi_budget_exhaustions_delta": 133,
                "rx_restart_reason_no_desc_delta": 2,
                "rx_alloc_failures_delta": 0,
                "dma_rx_stopped_samples_delta": 0,
                "dma_rx_missed_samples_delta": 0,
            },
            "oem_reference": "board_napi_budget() returns 128; OEM RX ring is 1024 descriptors",
        },
        "change_scope": {
            "single_variable": "qtn-topaz-emac NAPI weight 64 -> 128",
            "rx_ring": "unchanged at 128 descriptors",
            "rx_buffers": "unchanged at 2048 bytes",
            "poll_demand": "unchanged",
            "restart_threshold_cooldown": "unchanged at 16 pokes / 10000 ms",
            "rootfs": "byte-identical to F171",
            "radios_tqe_bridge_security": "byte-identical to F171/F170/F167",
            "mtd_layout": "unchanged",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "three matched 32 MiB 2.4 GHz down/up runs plus one simultaneous dual-radio run, correlated with EMAC counter deltas",
            "evaluator": "tools/evaluate_f172_emac_napi128_result.py",
        },
        "binary_contract": binary_contract,
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after fresh explicit authorization",
            "rollback": "preserved mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs_live view; never a physical write target",
            "offline_builder_hardware_actions": "none",
        },
    })
    manifest["contracts"]["hardware_boot"] = "NOT_RUN"
    manifest["contracts"]["flash"] = False
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    (OUT / "LAYOUT.md").write_text(
        "# F172 EMAC NAPI-128 SquashFS layout\n\n"
        "- Source rootfs: byte-identical F171 Lyoko Foundation health candidate.\n"
        "- Kernel-only variable: qtn-topaz-emac NAPI weight `64 -> 128`.\n"
        "- RX ring, buffers, poll-demand and restart policy: unchanged.\n"
        f"- Candidate bytes: `{manifest['artifacts']['webformat']['bytes']}`.\n"
        f"- Candidate SHA-256: `{manifest['artifacts']['webformat']['sha256']}`.\n"
        f"- Full-slot CRC32: `{manifest['artifacts']['full_slot']['crc32']}`.\n"
        "- Bootbase and slot-fit contracts: PASS.\n"
        "- Hardware boot/traffic: NOT_RUN. No performance improvement is claimed.\n"
        "- Any promoted write may target only mtd4 after fresh explicit authorization; mtd3 remains rollback.\n",
        encoding="ascii",
    )
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
