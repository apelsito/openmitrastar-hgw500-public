import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from f319_flash_fallback import classify, marker, record_attempt, verify_attempt

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = "0123456789abcdef0123456789abcdef"
CANDIDATE = "a" * 64
CURRENT = "d6b13baa"
KWARGS = {"attempt_id": ATTEMPT, "candidate": CANDIDATE, "current_crc": CURRENT}
ABORT = (marker(**KWARGS) + "\n").encode()
UART = b"tftpboot 0x83000000 synthetic-candidate.bin\nAbort\ntopaz>\n"


def test_only_explicit_pre_erase_failure_qualifies():
    result = classify(**KWARGS, transport="tftp", returncode=1, backend=ABORT, uart=UART)
    assert result["fallback_allowed"] is True


@pytest.mark.parametrize("changes", [
    {"returncode": 0}, {"returncode": None}, {"returncode": True}, {"transport": "uart-ymodem"},
    {"backend": b"transfer failed without phase evidence"}, {"backend": ABORT + ABORT},
    {"backend": ABORT.replace(ATTEMPT.encode(), b"f" * 32)},
    {"backend": ABORT.replace(CANDIDATE.encode(), b"b" * 64)},
    {"backend": ABORT.replace(CURRENT.encode(), b"22d3802a")},
    {"uart": None}, {"uart": b""},
    {"uart": UART + b"spi_flash erase 0x007e0000 0x005e0000\n"},
    {"backend": ABORT + b"spi_flash write 0x7e0000 0x83000000 0x50c000\n"},
    {"backend": ABORT + b"OMQ3_MTD4_BOOTBASE_READBACK_PASS=1\n"},
])
def test_ambiguous_mismatched_or_post_erase_outcomes_never_handoff(changes):
    args = {**KWARGS, "transport": "tftp", "returncode": 1, "backend": ABORT, "uart": UART, **changes}
    assert classify(**args)["fallback_allowed"] is False


def make_evidence(directory):
    (directory / "backend.log").write_bytes(ABORT)
    (directory / "bootbase-flash-uart.log").write_bytes(UART)
    record_attempt(directory, **KWARGS, transport="tftp", returncode=1)


def test_verifier_recomputes_proof_and_refuses_log_changes(tmp_path):
    make_evidence(tmp_path)
    assert verify_attempt(tmp_path, **KWARGS)["fallback_allowed"] is True
    (tmp_path / "backend.log").write_bytes(ABORT + b"late modification\n")
    with pytest.raises(ValueError): verify_attempt(tmp_path, **KWARGS)


@pytest.mark.parametrize("name", ["attempt-result.json", "backend.log", "bootbase-flash-uart.log"])
def test_missing_evidence_fails_closed(tmp_path, name):
    make_evidence(tmp_path)
    (tmp_path / name).unlink()
    with pytest.raises(ValueError): verify_attempt(tmp_path, **KWARGS)


def test_copied_old_attempt_cannot_authorize_new_attempt(tmp_path):
    make_evidence(tmp_path)
    with pytest.raises(ValueError): verify_attempt(tmp_path, **{**KWARGS, "attempt_id": "f" * 32})


def test_result_is_not_overwritten(tmp_path):
    make_evidence(tmp_path)
    with pytest.raises(FileExistsError): record_attempt(tmp_path, **KWARGS, transport="tftp", returncode=1)


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("case", ["success", "abort", "prompt-lost"])
def test_real_backend_transfer_function_with_fake_io(engine, case):
    executable = shutil.which(engine)
    assert executable, f"required engine missing: {engine}"
    result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-File",
                             str(ROOT / "tools/test_f319_fallback_backend.ps1"), "-Case", case],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["hardware_actions"] is False
    assert data["production_transfer_call_count"] == 1
    marker_present = marker(**KWARGS) in data["messages"]
    assert marker_present is (case == "abort")
    assert data["thrown"] is (case != "success")
    assert len(data["sent"]) == (3 if case == "abort" else 1)
    assert all(command.startswith("tftpboot ") for command in data["sent"])


def test_transition_is_guarded_in_promotion_and_rollback():
    for filename in ("promote_f319_mtd4_direct.ps1", "rollback_f319_to_f314_mtd4.ps1"):
        source = (ROOT / "tools" / filename).read_text()
        assert "--evidence-dir $tftpAttemptDir --attempt-id $tftpAttemptId" in source
        assert source.index("f319_flash_fallback.py") < source.index("--transport uart-ymodem")
        assert "pre-erase TFTP failure is not proven" in source
    backend = (ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1").read_text()
    assert backend.count("OMLYOKO_TFTP_PRE_ERASE_ABORT=1") == 1
    assert backend.index("        Receive-CandidateTftp\n") < backend.index('("spi_flash erase ')


@pytest.mark.parametrize("target,sha,current_crc,current_sha,ack", [
    ("f319", "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9", "d6b13baa",
     "bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989", "OPENMITRASTAR_F319_MTD4_E33D8511"),
    ("f314", "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11", "22d3802a",
     "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601", "OPENMITRASTAR_F319_ROLLBACK_TO_F314_A0C7350A"),
])
def test_complete_real_artifact_chain_in_local_dry_run(tmp_path, target, sha, current_crc, current_sha, ack):
    build = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware" / (target + "-device-bound")
    stem = f"openmitrastar-linux510-{target}-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
    environment = {**os.environ,
        "OM_Q3_FLASH_ACK": ack, "OM_Q3_FLASH_BUILD_DIR": str(build),
        "OM_Q3_FLASH_CANDIDATE": str(build / (stem + ".webformat.bin")),
        "OM_Q3_FLASH_BOOTBASE_CONTRACT": str(build / "bootbase-contract.json"),
        "OM_Q3_FLASH_MANIFEST": str(build / "manifest.json"),
        "OM_Q3_FLASH_INITRAMFS": str(build / (stem + ".kernel.raw.bin")),
        "OM_Q3_FLASH_KCONFIG": str(build / (stem + ".config")),
        "OM_Q3_FLASH_LAYOUT_MODE": "squashfs-split",
        "OM_Q3_FLASH_ROOTFS_IMAGE": str(build / (stem + ".rootfs.squashfs")),
        "OM_Q3_FLASH_DTB": str(build / (stem + ".dtb")),
        "OM_Q3_FLASH_ROOTFS_OFFSET": "0x180000", "OM_Q3_FLASH_EXPECTED_SHA256": sha,
        "OM_Q3_FLASH_EXPECTED_BYTES": "5292032", "OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32": current_crc,
        "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256": current_sha,
        "OM_Q3_FLASH_POWERSHELL_BACKEND": str(ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1"),
    }
    evidence = tmp_path / "must-not-be-created"
    result = subprocess.run([sys.executable, str(ROOT / "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"),
                             "--transport", "tftp", "--skip-reboot", "--uart-attach-topaz", "--timeout", "1800",
                             "--erase-bytes", "0x5e0000", "--attempt-id", ATTEMPT, "--evidence-dir", str(evidence)],
                            env=environment, cwd=ROOT, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    plan, _ = json.JSONDecoder().raw_decode(result.stdout)
    assert plan["mode"] == "dry-run" and plan["flash_ready"] is False
    assert plan["candidate_sha256"] == sha and plan["candidate_bytes"] == 5292032
    assert plan["current_live_sha256"] == current_sha and plan["current_live_crc32"] == current_crc
    assert plan["physical_write"]["partition"] == "mtd4/linux_live"
    assert plan["physical_write"]["erase_size"] == "0x005e0000"
    assert plan["forbidden_physical_writes"] == ["mtd0/uboot", "mtd1/env", "mtd2/env_bak", "mtd3/linux_safety", "mtd5/data"]
    assert not evidence.exists()
