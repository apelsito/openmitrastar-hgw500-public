#!/usr/bin/env python3
"""Plan and simulate bounded Lyoko mtd4 store transactions without hardware I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


SLOT_SIZE = 0x7A0000
FIRMWARE_LIMIT = 0x5E0000
STORE_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000
ERASE_SIZE = 0x10000
PAGE_SIZE = 0x100
PHYSICAL_MTD4_OFFSET = 0x7E0000
JFFS2_MAGIC_LE = b"\x85\x19"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_hash(data: bytes, expected: str, label: str) -> None:
    actual = sha256_bytes(data)
    if actual != expected.lower():
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected.lower()}, got {actual}")


def slot_from_firmware(firmware: bytes) -> bytes:
    if not firmware or len(firmware) > FIRMWARE_LIMIT:
        raise ValueError("firmware must fit entirely before lyoko_store")
    return firmware + b"\xff" * (SLOT_SIZE - len(firmware))


def eraseblock_plan(offset: int, length: int) -> list[dict[str, int | str]]:
    if offset % ERASE_SIZE or length % ERASE_SIZE:
        raise ValueError("transaction range must be eraseblock aligned")
    if offset < 0 or length <= 0 or offset + length > SLOT_SIZE:
        raise ValueError("transaction range escapes mtd4")
    return [
        {
            "index": index,
            "mtd4_offset": f"0x{block:06x}",
            "physical_flash_offset": f"0x{PHYSICAL_MTD4_OFFSET + block:06x}",
            "bytes": ERASE_SIZE,
        }
        for index, block in enumerate(range(offset, offset + length, ERASE_SIZE))
    ]


def initialize_store(current_slot: bytes, store_image: bytes) -> tuple[bytes, dict[str, object]]:
    if len(current_slot) != SLOT_SIZE:
        raise ValueError("current mtd4 slot must be exactly 0x7a0000 bytes")
    if len(store_image) != STORE_SIZE:
        raise ValueError("store image must be exactly 0x1c0000 bytes")
    if store_image[:2] != JFFS2_MAGIC_LE:
        raise ValueError("store image is not little-endian JFFS2")
    before_store = current_slot[STORE_OFFSET:]
    if any(value != 0xFF for value in before_store):
        raise ValueError("lyoko_store is not erased; initialization refuses overwrite")
    after = current_slot[:STORE_OFFSET] + store_image
    checks = {
        "slot_size_exact": len(after) == SLOT_SIZE,
        "firmware_prefix_preserved": after[:STORE_OFFSET] == current_slot[:STORE_OFFSET],
        "store_exact": after[STORE_OFFSET:] == store_image,
        "range_inside_mtd4": STORE_OFFSET + STORE_SIZE == SLOT_SIZE,
        "eraseblock_aligned": STORE_OFFSET % ERASE_SIZE == 0 and STORE_SIZE % ERASE_SIZE == 0,
    }
    if not all(checks.values()):
        raise ValueError("store initialization invariant failed")
    return after, {
        "operation": "initialize-store",
        "write_offset": f"0x{STORE_OFFSET:06x}",
        "write_bytes": STORE_SIZE,
        "eraseblocks": eraseblock_plan(STORE_OFFSET, STORE_SIZE),
        "checks": checks,
    }


def update_firmware(current_slot: bytes, firmware: bytes) -> tuple[bytes, dict[str, object]]:
    if len(current_slot) != SLOT_SIZE:
        raise ValueError("current mtd4 slot must be exactly 0x7a0000 bytes")
    if not firmware or len(firmware) > FIRMWARE_LIMIT:
        raise ValueError("firmware must fit entirely before lyoko_store")
    prefix = firmware + b"\xff" * (FIRMWARE_LIMIT - len(firmware))
    store = current_slot[STORE_OFFSET:]
    after = prefix + store
    checks = {
        "slot_size_exact": len(after) == SLOT_SIZE,
        "new_firmware_exact": after[: len(firmware)] == firmware,
        "unused_prefix_erased": all(value == 0xFF for value in after[len(firmware):STORE_OFFSET]),
        "store_preserved": after[STORE_OFFSET:] == store,
        "range_inside_mtd4": FIRMWARE_LIMIT <= SLOT_SIZE,
        "eraseblock_aligned": FIRMWARE_LIMIT % ERASE_SIZE == 0,
    }
    if not all(checks.values()):
        raise ValueError("firmware update invariant failed")
    return after, {
        "operation": "update-firmware",
        "write_offset": "0x000000",
        "write_bytes": FIRMWARE_LIMIT,
        "eraseblocks": eraseblock_plan(0, FIRMWARE_LIMIT),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("initialize-store", "update-firmware"))
    parser.add_argument("--current-slot", type=Path)
    parser.add_argument("--current-firmware", type=Path)
    parser.add_argument("--new-firmware", type=Path)
    parser.add_argument("--store-image", type=Path)
    parser.add_argument("--expected-current-sha256", required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if bool(args.current_slot) == bool(args.current_firmware):
        raise SystemExit("provide exactly one of --current-slot or --current-firmware")
    if args.current_slot:
        current = args.current_slot.read_bytes()
    else:
        current = slot_from_firmware(args.current_firmware.read_bytes())
    require_hash(current, args.expected_current_sha256, "current slot")

    if args.operation == "initialize-store":
        if not args.store_image or args.new_firmware:
            raise SystemExit("initialize-store requires --store-image only")
        transaction_input = args.store_image.read_bytes()
        require_hash(transaction_input, args.expected_input_sha256, "store image")
        after, plan = initialize_store(current, transaction_input)
    else:
        if not args.new_firmware or args.store_image:
            raise SystemExit("update-firmware requires --new-firmware only")
        transaction_input = args.new_firmware.read_bytes()
        require_hash(transaction_input, args.expected_input_sha256, "new firmware")
        after, plan = update_firmware(current, transaction_input)

    result = {
        "schema": "openmitrastar.lyoko-store-transaction/v1",
        "classification": "OFFLINE_SIMULATION_NO_HARDWARE_WRITES",
        "mode": "execute" if args.execute else "dry-run",
        "physical_partition": "mtd4/linux_live",
        "physical_mtd4_offset": f"0x{PHYSICAL_MTD4_OFFSET:06x}",
        "slot_bytes": SLOT_SIZE,
        "firmware_limit": f"0x{FIRMWARE_LIMIT:06x}",
        "store_offset": f"0x{STORE_OFFSET:06x}",
        "store_bytes": STORE_SIZE,
        "erase_size": ERASE_SIZE,
        "page_size": PAGE_SIZE,
        "before_sha256": sha256_bytes(current),
        "after_sha256": sha256_bytes(after),
        "input_sha256": sha256_bytes(transaction_input),
        "plan": plan,
        "protected": {
            "mtd0": True,
            "mtd1": True,
            "mtd2": True,
            "mtd3": True,
            "mtd5": True,
            "boot_environment": True,
        },
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    print(json.dumps(result, indent=2))
    if not args.execute:
        return 0

    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    artifact = output / "mtd4-after-analysis-only.bin"
    artifact.write_bytes(after)
    result["artifact"] = {
        "file": artifact.name,
        "bytes": artifact.stat().st_size,
        "sha256": sha256_bytes(after),
        "flash_authorized": False,
    }
    transaction_path = output / "transaction.json"
    transaction_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    input_copy = output / "transaction-input.bin"
    shutil.copy2(args.store_image if args.operation == "initialize-store" else args.new_firmware, input_copy)
    (output / "SHA256SUMS").write_text(
        f"{sha256_bytes(artifact.read_bytes())}  {artifact.name}\n"
        f"{sha256_bytes(input_copy.read_bytes())}  {input_copy.name}\n"
        f"{sha256_bytes(transaction_path.read_bytes())}  {transaction_path.name}\n",
        encoding="ascii",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
