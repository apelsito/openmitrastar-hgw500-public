from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/lyoko_store_transaction.py"
SPEC = importlib.util.spec_from_file_location("lyoko_store_transaction", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_initialize_store_changes_only_reserved_tail() -> None:
    firmware = b"F" * 1024
    before = MODULE.slot_from_firmware(firmware)
    store = MODULE.JFFS2_MAGIC_LE + b"S" * (MODULE.STORE_SIZE - 2)
    after, plan = MODULE.initialize_store(before, store)
    assert after[: MODULE.STORE_OFFSET] == before[: MODULE.STORE_OFFSET]
    assert after[MODULE.STORE_OFFSET :] == store
    assert len(plan["eraseblocks"]) == 28
    assert plan["eraseblocks"][0]["physical_flash_offset"] == "0xdc0000"
    assert plan["eraseblocks"][-1]["physical_flash_offset"] == "0xf70000"


def test_initialize_store_refuses_existing_data() -> None:
    before = bytearray(MODULE.slot_from_firmware(b"F" * 1024))
    before[MODULE.STORE_OFFSET] = 0
    store = MODULE.JFFS2_MAGIC_LE + b"S" * (MODULE.STORE_SIZE - 2)
    with pytest.raises(ValueError, match="not erased"):
        MODULE.initialize_store(bytes(before), store)


def test_update_firmware_preserves_store_exactly() -> None:
    store = MODULE.JFFS2_MAGIC_LE + bytes(range(256)) * ((MODULE.STORE_SIZE - 2) // 256) + b"X" * ((MODULE.STORE_SIZE - 2) % 256)
    before = MODULE.slot_from_firmware(b"A" * 2048)[: MODULE.STORE_OFFSET] + store
    firmware = b"B" * 4096
    after, plan = MODULE.update_firmware(before, firmware)
    assert after[: len(firmware)] == firmware
    assert after[MODULE.STORE_OFFSET :] == store
    assert len(plan["eraseblocks"]) == 94
    assert plan["eraseblocks"][0]["physical_flash_offset"] == "0x7e0000"
    assert plan["eraseblocks"][-1]["physical_flash_offset"] == "0xdb0000"


def test_rejects_oversized_firmware_and_bad_store() -> None:
    with pytest.raises(ValueError, match="fit entirely"):
        MODULE.slot_from_firmware(b"X" * (MODULE.FIRMWARE_LIMIT + 1))
    with pytest.raises(ValueError, match="JFFS2"):
        MODULE.initialize_store(MODULE.slot_from_firmware(b"F"), b"X" * MODULE.STORE_SIZE)


def test_cli_materializes_self_checking_analysis_bundle(tmp_path: Path) -> None:
    firmware = tmp_path / "firmware.bin"
    store = tmp_path / "store.jffs2"
    output = tmp_path / "out"
    firmware.write_bytes(b"F" * 4096)
    store.write_bytes(MODULE.JFFS2_MAGIC_LE + b"S" * (MODULE.STORE_SIZE - 2))
    current = MODULE.slot_from_firmware(firmware.read_bytes())
    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "initialize-store",
            "--current-firmware", str(firmware),
            "--store-image", str(store),
            "--expected-current-sha256", hashlib.sha256(current).hexdigest(),
            "--expected-input-sha256", hashlib.sha256(store.read_bytes()).hexdigest(),
            "--output-dir", str(output),
            "--execute",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    transaction = json.loads((output / "transaction.json").read_text(encoding="ascii"))
    assert transaction["artifact"]["flash_authorized"] is False
    assert (output / "SHA256SUMS").is_file()
    assert len((output / "mtd4-after-analysis-only.bin").read_bytes()) == MODULE.SLOT_SIZE
