#!/usr/bin/env python3
"""Build the deterministic read-only Bootbase wifiaddr producer artifact."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/om_bootenv_wifiaddr_nolibc.c"
OUTPUT = ROOT / "outputs/kernel-port/q3-bootenv-wifiaddr-readonly"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
KERNEL_SOURCE = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/radiohw-probe"
TOOLCHAIN = "/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    required = (
        '"mitrastar,hgw-500bna-qcv2"',
        'om_find_mtd(om_proc_mtd',
        'om_crc32(raw + 4, OM_ENV_CRC_END - 4)',
        'redundant-wifiaddr-mismatch',
        'source=mtd1+mtd2-redundant-readonly',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f"producer contract marker missing: {marker}")
    for forbidden in ("flash_erase", "MEMERASE", "saveenv", "/dev/omspiro"):
        if forbidden in text:
            raise SystemExit(f"producer contains forbidden path: {forbidden}")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    binary = OUTPUT / "om-bootenv-readonly"
    binary_wsl = "/workspace/user-home/Desktop/MitraStar/outputs/kernel-port/q3-bootenv-wifiaddr-readonly/om-bootenv-readonly"
    source_wsl = "/workspace/user-home/Desktop/MitraStar/tools/om_bootenv_wifiaddr_nolibc.c"
    compile_result = subprocess.run([
        "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-lc",
        f"set -e; {TOOLCHAIN}gcc -Os -mno-atomic -fno-stack-protector -fno-builtin -fno-pic -fno-pie -no-pie "
        f"-ffreestanding -nostdlib -static -Wl,-e,_start -Wl,--build-id=none -s "
        f"{source_wsl} -o {binary_wsl}; "
        f"{TOOLCHAIN}strip {binary_wsl}; chmod 0755 {binary_wsl}",
    ], cwd=ROOT, capture_output=True, text=True)
    if compile_result.returncode:
        raise SystemExit(compile_result.stdout + compile_result.stderr)
    digest = sha(binary)

    if os.name == "nt":
        source_wsl = "/workspace/user-home/Desktop/MitraStar/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
        build = subprocess.run([
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-lc",
            f"set -e; cp {source_wsl} {KERNEL_SOURCE}/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts; "
            f"touch {KERNEL_SOURCE}/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts; "
            f"make -s -C {KERNEL_SOURCE} O={KERNEL_OUT} ARCH=arc CROSS_COMPILE={TOOLCHAIN} topaz_mitrastar_ramssh.dtb",
        ], cwd=ROOT, capture_output=True, text=True)
        if build.returncode:
            raise SystemExit(build.stdout + build.stderr)
        dtb_read = subprocess.run([
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "cat",
            f"{KERNEL_OUT}/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb",
        ], cwd=ROOT, capture_output=True)
        if dtb_read.returncode:
            raise SystemExit(dtb_read.stderr.decode("utf-8", "replace"))
        dtb_data = dtb_read.stdout
    else:
        subprocess.run([
            "make", "-s", "-C", KERNEL_SOURCE, f"O={KERNEL_OUT}", "ARCH=arc",
            f"CROSS_COMPILE={TOOLCHAIN}", "topaz_mitrastar_ramssh.dtb",
        ], check=True)
        dtb_data = Path(KERNEL_OUT, "arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb").read_bytes()
    dtb = OUTPUT / "topaz_mitrastar_ramssh.dtb"
    dtb.write_bytes(dtb_data)
    shutil.copyfile(DTS, OUTPUT / "topaz_mitrastar_ramssh.dts")
    manifest = {
        "schema": "openmitrastar.bootenv-wifiaddr-producer/v1",
        "source": "mtd1+mtd2-redundant-readonly",
        "primary_label": "uboot_env",
        "backup_label": "uboot_env_bak",
        "partition_size": 0x10000,
        "logical_env_size": 0x6000,
        "crc32": "stored-little-endian-over-bytes-4-through-0x5fff",
        "key": "wifiaddr",
        "copies_must_match": True,
        "read_only": True,
        "writes_flash": False,
        "compatible": "mitrastar,hgw-500bna-qcv2",
        "mtd_type": "rom",
        "output": "/run/openmitrastar/bootenv/wifiaddr",
        "output_mode": "0600",
        "binary_sha256": digest,
        "source_sha256": sha(SOURCE),
        "runtime": "arc700-syscall-only-no-libc-no-tls-no-atomics",
        "compiler_flags": [
            "-Os", "-mno-atomic", "-fno-stack-protector", "-fno-builtin", "-fno-pic",
            "-fno-pie", "-no-pie", "-ffreestanding", "-nostdlib", "-static",
            "-Wl,-e,_start", "-Wl,--build-id=none", "-s"
        ],
        "dts_sha256": sha(OUTPUT / "topaz_mitrastar_ramssh.dts"),
        "dtb_sha256": sha(dtb),
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT / "SHA256SUMS").write_text(
        f"{digest}  om-bootenv-readonly\n"
        f"{sha(OUTPUT / 'topaz_mitrastar_ramssh.dts')}  topaz_mitrastar_ramssh.dts\n"
        f"{sha(dtb)}  topaz_mitrastar_ramssh.dtb\n"
        f"{sha(OUTPUT / 'manifest.json')}  manifest.json\n",
        encoding="ascii",
    )
    print(f"Q3_BOOTENV_WIFIADDR_BUILD_PASS binary_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
