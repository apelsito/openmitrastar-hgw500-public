#!/usr/bin/env python3
"""Split and certify an exact 16 MiB HGW physical NOR read-only image."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LAYOUT = (
    (0, "uboot", 0x000000, 0x020000),
    (1, "uboot_env", 0x020000, 0x010000),
    (2, "uboot_env_bak", 0x030000, 0x010000),
    (3, "linux_safety", 0x040000, 0x7A0000),
    (4, "linux_live", 0x7E0000, 0x7A0000),
    (5, "data", 0xF80000, 0x080000),
)
FLASH_SIZE = 0x1000000


def hash_file(path: Path) -> dict[str, object]:
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block); md5.update(block); size += len(block)
    return {"size": size, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physical-image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path)
    args = parser.parse_args()
    physical = args.physical_image.resolve()
    output = args.output_dir.resolve()
    physical_hash = hash_file(physical)
    if physical_hash["size"] != FLASH_SIZE:
        raise SystemExit(f"physical image size={physical_hash['size']} expected={FLASH_SIZE}")
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    with physical.open("rb") as source:
        for index, name, offset, size in LAYOUT:
            source.seek(offset)
            blob = source.read(size)
            if len(blob) != size:
                raise SystemExit(f"short physical read for mtd{index}")
            path = output / f"hgw500_mtdblock{index}.bin"
            path.write_bytes(blob)
            evidence = hash_file(path)
            entry: dict[str, object] = {
                "index": index, "name": name, "offset": offset, "size": size,
                "file": path.name, "sha256": evidence["sha256"], "md5": evidence["md5"],
                "exact_size": evidence["size"] == size,
            }
            if args.baseline_dir:
                baseline = args.baseline_dir.resolve() / path.name
                if baseline.is_file():
                    old = hash_file(baseline)
                    entry["baseline"] = {
                        "file": str(baseline), **old,
                        "byte_identical": old["size"] == size and old["sha256"] == evidence["sha256"],
                    }
            entries.append(entry)
            print(f"SPLIT_PARTITION_PASS mtd={index} name={name} sha256={evidence['sha256']}")
    manifest = {
        "schema": "openmitrastar.physical-flash-backup/v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_capture": "Linux 5.10 /dev/omspiro over authenticated SSH",
        "read_only_capture": True,
        "physical_layout": "mtd0..mtd5 contiguous, exactly 16 MiB",
        "mtd6_included": False,
        "mtd6_reason": "logical rootfs view inside linux_live; not physical flash",
        "partitions": entries,
        "physical_image": {"file": str(physical), **physical_hash},
        "validation": {
            "all_partition_sizes_exact": all(item["exact_size"] for item in entries),
            "all_physical_partitions_present": len(entries) == 6,
            "physical_size_exact": physical_hash["size"] == FLASH_SIZE,
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sums = [f"{item['sha256']}  {item['file']}" for item in entries]
    sums.append(f"{physical_hash['sha256']}  {physical.name}")
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    print(f"PHYSICAL_SPLIT_PASS manifest={manifest_path} sha256={physical_hash['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
