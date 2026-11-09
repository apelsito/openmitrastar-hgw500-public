#!/usr/bin/env python3
"""Build the private, RAM-only ARC/uClibc control plane for Quantenna wifi0.

The output deliberately contains no PSK.  It bundles the OEM qcsapi client,
the OEM madwifi hostapd, and their complete dynamic-loader closure so the
Linux 5.10 rescue rootfs does not need to provide ABI-compatible libraries.
"""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import re
import shutil
import struct

from elftools.elf.elffile import ELFFile


ROOT = Path(__file__).resolve().parents[1]
OEM = ROOT / "work/hgw500-rootfs-live/squashfs-root"
DEFAULT_OUTPUT = ROOT / "outputs/kernel-port/qcsapi-5g-ap36-bw80-ram-only-20260819"
KERNEL_CONFIG = (
    ROOT
    / "outputs/kernel-port/phase-a-l2-kernel"
    / "linux-5.10.260-openmitrastar-radiohw-l2-igmp-RAM-ONLY-NO-FLASH.config"
)

FILES = {
    "bin/call_qcsapi": OEM / "sbin/call_qcsapi",
    "bin/hostapd": OEM / "usr/sbin/hostapd",
    "bin/hostapd_cli": OEM / "usr/sbin/hostapd_cli",
    "lib/ld-uClibc-0.9.29.so": OEM / "lib/ld-uClibc-0.9.29.so",
    "lib/libuClibc-0.9.29.so": OEM / "lib/lib/libuClibc-0.9.29.so",
    "lib/libpthread-0.9.29.so": OEM / "lib/lib/libpthread-0.9.29.so",
    "lib/libm-0.9.29.so": OEM / "lib/lib/libm-0.9.29.so",
    "lib/libdl-0.9.29.so": OEM / "lib/lib/libdl-0.9.29.so",
    "lib/librt-0.9.29.so": OEM / "lib/lib/librt-0.9.29.so",
    "lib/libz.so.1.2.3": OEM / "lib/libz.so.1.2.3",
    "lib/libqcsapi.so.1.0.1": OEM / "lib/libqcsapi.so.1.0.1",
    "lib/libcall_qcsapi.so.1.0.1": OEM / "lib/libcall_qcsapi.so.1.0.1",
    "lib/libssl.so.1.0.0": OEM / "usr/lib/libssl.so.1.0.0",
    "lib/libcrypto.so.1.0.0": OEM / "usr/lib/libcrypto.so.1.0.0",
}

EF_ARC_OSABI_MSK = 0x00000F00
EF_ARC_OSABI_V4 = 0x00000400
EF_ARC_LEGACY_FLAGS = 0x3

ALIASES = {
    "ld-uClibc.so.0": "ld-uClibc-0.9.29.so",
    "libc.so.0": "libuClibc-0.9.29.so",
    "libpthread.so.0": "libpthread-0.9.29.so",
    "libm.so.0": "libm-0.9.29.so",
    "libdl.so.0": "libdl-0.9.29.so",
    "librt.so.0": "librt-0.9.29.so",
    "libz.so.1": "libz.so.1.2.3",
    "libqcsapi.so.1": "libqcsapi.so.1.0.1",
    "libcall_qcsapi.so.1": "libcall_qcsapi.so.1.0.1",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_elf(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        elf = ELFFile(handle)
        interpreter = None
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_INTERP":
                interpreter = segment.get_interp_name()
        needed: list[str] = []
        dynamic = elf.get_section_by_name(".dynamic")
        if dynamic is not None:
            needed = [
                tag.needed
                for tag in dynamic.iter_tags()
                if tag.entry.d_tag == "DT_NEEDED"
            ]
        return {
            "elf_class": elf.elfclass,
            "little_endian": elf.little_endian,
            "machine": elf["e_machine"],
            "flags": int(elf["e_flags"]),
            "interpreter": interpreter,
            "needed": needed,
        }


def patch_arc_osabi_v4(path: Path) -> tuple[int, int]:
    raw = bytearray(path.read_bytes())
    old_flags = struct.unpack_from("<I", raw, 36)[0]
    new_flags = (old_flags & ~EF_ARC_OSABI_MSK) | EF_ARC_OSABI_V4
    struct.pack_into("<I", raw, 36, new_flags)
    path.write_bytes(raw)
    return old_flags, new_flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--osabi-v4",
        action="store_true",
        help="Patch copied ARC ELF e_flags OSABI bits to EF_ARC_OSABI_V4 (0x403).",
    )
    args = parser.parse_args()
    output = args.output
    runtime = output / "runtime"

    for relative, source in FILES.items():
        if not source.is_file():
            raise SystemExit(f"missing OEM runtime input: {relative}: {source}")
    config = KERNEL_CONFIG.read_text(encoding="ascii")
    required_config = (
        "CONFIG_MMU=y",
        "CONFIG_ISA_ARCOMPACT=y",
        "CONFIG_ARC_MMU_V2=y",
        "CONFIG_ARC_PAGE_SIZE_8K=y",
        "CONFIG_BINFMT_ELF=y",
    )
    for line in required_config:
        if line not in config.splitlines():
            raise SystemExit(f"Linux 5.10 ABI prerequisite absent: {line}")

    if output.exists():
        shutil.rmtree(output)
    for relative, source in FILES.items():
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if args.osabi_v4:
            patch_arc_osabi_v4(destination)

    reports: dict[str, dict[str, object]] = {}
    expected_flags = (EF_ARC_LEGACY_FLAGS & ~EF_ARC_OSABI_MSK) | EF_ARC_OSABI_V4 if args.osabi_v4 else EF_ARC_LEGACY_FLAGS
    provided = {Path(relative).name for relative in FILES}
    provided.update(ALIASES)
    missing_needed: set[str] = set()
    for relative in sorted(FILES):
        path = runtime / relative
        info = inspect_elf(path)
        if (
            info["elf_class"] != 32
            or info["little_endian"] is not True
            or info["machine"] != "EM_ARC_COMPACT"
            or info["flags"] != expected_flags
        ):
            raise SystemExit(f"ARC700 ABI mismatch: {relative}: {info}")
        if relative.startswith("bin/") and info["interpreter"] != "/lib/ld-uClibc.so.0":
            raise SystemExit(f"uClibc interpreter mismatch: {relative}: {info['interpreter']}")
        missing_needed.update(set(info["needed"]) - provided)
        reports[relative] = info
    if missing_needed:
        raise SystemExit("incomplete dynamic closure: " + ", ".join(sorted(missing_needed)))

    manifest_lines = []
    for path in sorted(p for p in runtime.rglob("*") if p.is_file()):
        manifest_lines.append(f"{sha256(path)}  {path.relative_to(runtime).as_posix()}")
    manifest = runtime / "manifest.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="ascii", newline="\n")

    report = {
        "artifact": output.name,
        "scope": "RAM-only; no flash; no bundled credentials",
        "kernel_release": "5.10.260-openmitrastar-radiohw",
        "kernel_abi_prerequisites": list(required_config),
        "userspace_abi": (
            "ELF32 little-endian ARCompact ARC700 OSABI V4 flags=0x403"
            if args.osabi_v4
            else "ELF32 little-endian ARCompact ARC700 legacy flags=0x3"
        ),
        "osabi_v4_patched": args.osabi_v4,
        "libc": "uClibc 0.9.29 from the same HGW-500BNA OEM rootfs",
        "dynamic_closure_complete": True,
        "aliases_created_on_target": ALIASES,
        "elf": reports,
        "runtime_manifest_sha256": sha256(manifest),
        "psk_bundled": False,
    }
    (output / "abi-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    secret_pattern = re.compile(rb"(?i)(wpa_passphrase|wpa_psk|psk|passphrase)\s*=\s*\S+")
    for path in (p for p in output.rglob("*") if p.is_file()):
        payload = path.read_bytes()
        # ELF programs legitimately contain parser/help strings such as
        # ``wpa_passphrase=``.  Credential scanning applies to generated text
        # and configuration; the bundle intentionally contains no config.
        if not payload.startswith(b"\x7fELF") and secret_pattern.search(payload):
            raise SystemExit(f"credential-like assignment found in artifact: {path}")

    print(f"artifact={output}")
    print(f"runtime_manifest_sha256={sha256(manifest)}")
    print("W3_QCSAPI_RUNTIME_ABI_STATIC_PASS=1 arc=ARC700 libc=uClibc-0.9.29 closure=complete")
    print("W3_QCSAPI_RUNTIME_SECRET_SCAN_PASS=1 psk_bundled=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
