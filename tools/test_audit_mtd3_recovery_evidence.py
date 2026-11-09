from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/audit_mtd3_recovery_evidence.py"
OUT = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"


def test_audit_is_read_only_and_precise() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in ("RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE", "VFS: Unable to mount root fs", "0x00040000", '"flash_written_by_audit": False'):
        assert marker in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "saveenv", "SerialPort"):
        assert forbidden not in text


def test_existing_evidence_classification() -> None:
    proc = subprocess.run(["python", str(SCRIPT)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(OUT.read_text(encoding="ascii"))
    assert payload["recovery_ready"] is False
    assert payload["checks"]["mtd3_hash_matches_f170_attestation"] is True
    assert payload["checks"]["uimage_crc_pass"] is True
    assert payload["checks"]["oem_kernel_started"] is True
    assert payload["checks"]["rootfs_mount_failed"] is True
