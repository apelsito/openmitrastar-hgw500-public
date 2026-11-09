#!/usr/bin/env python3
"""Build a versioned HGW-500BNA-QCv2 Revival firmware image.

The provider firmware is read-only input. Outputs are written under
versions/<version>/build/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib


BASE_FW = "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
SQUASHFS_OFFSET = 0x130000
RAS_OFFSET = 0x2000
UIMAGE_HEADER_LEN = 64


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{rest}"


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def patch_uimage_header(image: bytearray, ih_size: int) -> dict[str, str | int | bool]:
    header = image[:UIMAGE_HEADER_LEN]
    values = list(struct.unpack(">7I4B32s", header))
    magic = values[0]
    if magic != 0x27051956:
        raise ValueError(f"unexpected uImage magic: 0x{magic:08x}")

    ras_crc = zlib.crc32(bytes(image[RAS_OFFSET : RAS_OFFSET + ih_size])) & 0xFFFFFFFF
    values[6] = ras_crc

    header_without_hcrc = bytearray(struct.pack(">7I4B32s", *values))
    header_without_hcrc[4:8] = b"\x00\x00\x00\x00"
    header_crc = zlib.crc32(bytes(header_without_hcrc)) & 0xFFFFFFFF
    values[1] = header_crc

    image[:UIMAGE_HEADER_LEN] = struct.pack(">7I4B32s", *values)
    verify = bytearray(image[:UIMAGE_HEADER_LEN])
    verify[4:8] = b"\x00\x00\x00\x00"

    return {
        "uimage_header_crc": f"0x{header_crc:08x}",
        "uimage_header_crc_valid": (zlib.crc32(bytes(verify)) & 0xFFFFFFFF) == header_crc,
        "ras_crc32_from_0x2000": f"0x{ras_crc:08x}",
        "ih_size": ih_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="revival-0.1-readonly")
    parser.add_argument("--force", action="store_true", help="overwrite an existing build for this version")
    parser.add_argument("--keep-wsl-work", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    version_dir = root / "versions" / args.version
    overlay_dir = version_dir / "overlay"
    build_dir = version_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    out_bin = build_dir / f"{args.version}_webformat.bin"
    manifest_path = build_dir / "manifest.json"
    if not args.force and (out_bin.exists() or manifest_path.exists()):
        raise FileExistsError(
            f"build already exists for {args.version}; choose a new version or pass --force"
        )

    source_fw = root / BASE_FW
    if not source_fw.exists():
        raise FileNotFoundError(source_fw)
    if not overlay_dir.exists():
        raise FileNotFoundError(overlay_dir)

    source_data = source_fw.read_bytes()
    source_header = struct.unpack(">7I4B32s", source_data[:UIMAGE_HEADER_LEN])
    ih_size = source_header[3]
    original_rootfs_segment_size = len(source_data) - SQUASHFS_OFFSET

    squashfs_source = root / "work" / "revival" / "rootfs_original_0x130000.squashfs"
    if not squashfs_source.exists():
        squashfs_source.write_bytes(source_data[SQUASHFS_OFFSET:])

    wsl_work = f"/tmp/mitrastar-revival/{args.version}"
    wsl_rootfs = f"{wsl_work}/rootfs"
    wsl_new_sq = f"{wsl_work}/new_rootfs.squashfs"
    wsl_build_sq = wsl_path(build_dir / "rootfs_repacked.squashfs")

    delete_manifest = overlay_dir / ".openmitrastar-delete"
    delete_commands = ""
    if delete_manifest.exists():
        for raw_line in delete_manifest.read_text(encoding="utf-8").splitlines():
            relpath = raw_line.strip().replace("\\", "/")
            if not relpath or relpath.startswith("#"):
                continue
            if relpath.startswith("/") or ".." in relpath:
                raise ValueError(f"unsafe delete path in {delete_manifest}: {relpath}")
            delete_commands += f"echo 'deleting {relpath}'\nrm -rf '{wsl_rootfs}/{relpath}'\n"

    shell = f"""
set -eu
rm -rf '{wsl_work}'
mkdir -p '{wsl_work}'
unsquashfs -d '{wsl_rootfs}' '{wsl_path(squashfs_source)}' >/tmp/mitrastar-revival-unsquashfs.log
{delete_commands}
(cd '{wsl_path(overlay_dir)}' && tar --exclude='./.openmitrastar-delete' -cf - .) | (cd '{wsl_rootfs}' && tar -xf -)
if [ -d '{wsl_rootfs}'/var/www ]; then
  find '{wsl_rootfs}'/var/www -type d -exec chmod 755 {{}} \\;
  find '{wsl_rootfs}'/var/www -type f -exec chmod 644 {{}} \\;
  find '{wsl_rootfs}'/var/www -type f \\( -name '*.cgi' -o -name '*.php' \\) -exec chmod 755 {{}} \\;
fi
if [ -d '{wsl_rootfs}'/var/www/revival/api ]; then
  find '{wsl_rootfs}'/var/www/revival/api -maxdepth 1 -type f -name '*.cgi' -exec chmod +x {{}} \\;
fi
if [ -d '{wsl_rootfs}'/var/www/api ]; then
  find '{wsl_rootfs}'/var/www/api -type f -exec chmod +x {{}} \\;
fi
if [ -d '{wsl_rootfs}'/etc/init.d ]; then
  find '{wsl_rootfs}'/etc/init.d -maxdepth 1 -type f -name 'S*' -exec chmod +x {{}} \\;
fi
if [ -d '{wsl_rootfs}'/etc/default ]; then
  find '{wsl_rootfs}'/etc/default -maxdepth 1 -type f -name '*.sh' -exec chmod 755 {{}} \\;
fi
if [ -d '{wsl_rootfs}'/scripts ]; then
  find '{wsl_rootfs}'/scripts -maxdepth 1 -type f -name 'openmitrastar-*' -exec chmod +x {{}} \\;
fi
mksquashfs '{wsl_rootfs}' '{wsl_new_sq}' -comp lzma -b 524288 -all-root -noappend >/tmp/mitrastar-revival-mksquashfs.log
cp '{wsl_new_sq}' '{wsl_build_sq}'
"""
    if not args.keep_wsl_work:
        shell += f"\nrm -rf '{wsl_work}'\n"

    run(["wsl", "-u", "root", "sh", "-lc", shell], cwd=root)

    new_rootfs = (build_dir / "rootfs_repacked.squashfs").read_bytes()
    if len(new_rootfs) > original_rootfs_segment_size:
        raise ValueError(
            "repacked rootfs is larger than original webformat segment: "
            f"{len(new_rootfs)} > {original_rootfs_segment_size}"
        )

    image = bytearray(source_data)
    image[SQUASHFS_OFFSET:] = b"\x00" * original_rootfs_segment_size
    image[SQUASHFS_OFFSET : SQUASHFS_OFFSET + len(new_rootfs)] = new_rootfs
    patch_meta = patch_uimage_header(image, ih_size)

    out_bin.write_bytes(image)

    manifest = {
        "version": args.version,
        "source": {
            "path": str(source_fw),
            "size": len(source_data),
            "md5": md5(source_data),
            "sha256": sha256(source_data),
            "attributes": str(source_fw.stat().st_file_attributes) if os.name == "nt" else "",
        },
        "layout": {
            "squashfs_offset": SQUASHFS_OFFSET,
            "original_rootfs_segment_size": original_rootfs_segment_size,
            "new_rootfs_size": len(new_rootfs),
            "new_rootfs_padding": original_rootfs_segment_size - len(new_rootfs),
        },
        "checksums": patch_meta,
        "output": {
            "path": str(out_bin),
            "size": len(image),
            "md5": md5(bytes(image)),
            "sha256": sha256(bytes(image)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
