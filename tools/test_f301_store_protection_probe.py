from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/f301_store_protection_probe.ps1"
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-store-protection-observer/qtn-topaz-store-protection-observer.c"
MODULE_DIR = ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904"
MODULE = MODULE_DIR / "qtn-topaz-store-protection-observer.ko"
MODULE_MANIFEST = MODULE_DIR / "manifest.json"
EXPECTED_FIRMWARE = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
EXPECTED_FIRMWARE_SHA256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
EXPECTED_MODULE_SHA256 = "2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke_dry_run(output: Path, state: Path, lock: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-OutputDir",
            str(output),
            "-CampaignStateRoot",
            str(state),
            "-SharedLockDir",
            str(lock),
            "-SkipProcessInventory",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    plan_path = output / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="ascii")) if plan_path.is_file() else {}
    return proc, plan


def test_powershell_parses() -> None:
    command = (
        "$errors=$null;$tokens=$null;"
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}',[ref]$tokens,[ref]$errors);"
        "if($errors.Count){$errors|%{$_.ToString()};exit 1}"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout


def test_runner_pins_f301_and_the_exact_observer() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        EXPECTED_FIRMWARE,
        EXPECTED_FIRMWARE_SHA256,
        EXPECTED_MODULE_SHA256,
        "5.10.260-openmitrastar-radiohw mod_unload ARC700",
        "known_hosts.f301",
        "OPENMITRASTAR_F301_STORE_PROTECTION_READONLY_2F00A2DB",
        "run_f301_sequential_dual_radio_soak[.]py",
        "run_f301_multicast_igmp_physical[.]py",
        "f301-physical-radio.lock",
    ):
        assert marker in source


def test_exact_module_contract_has_no_mutation_path() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    manifest = json.loads(MODULE_MANIFEST.read_text(encoding="ascii"))
    assert sha256(MODULE) == EXPECTED_MODULE_SHA256
    assert manifest["artifact"]["sha256"] == EXPECTED_MODULE_SHA256
    assert manifest["kernel_contract"]["vermagic"] == "5.10.260-openmitrastar-radiohw mod_unload ARC700"
    assert manifest["safety"] == {
        "erase": False,
        "flash_window_mapping": False,
        "module_autoload": False,
        "mtd_registration": False,
        "program": False,
        "protection_mutation": False,
        "read_commands_only": True,
        "write_enable": False,
    }
    assert source.count("qtn_spi_read_command(ctrl,") == 2
    for required in ("SPI_READ_ID", "SPI_READ_STATUS", "SPI_READ_SCUR", "SPI_READ_DPB"):
        assert required in source
    for forbidden in (
        "SPI_WRITE_ENABLE",
        "SPI_WRITE_DISABLE",
        "SPI_PAGE_PROGRAM",
        "SPI_SECTOR_ERASE",
        "SPI_WRITE_DPB",
        "mtd_device_register",
        "mtd_device_unregister",
        "memcpy_toio",
        "writeb(",
    ):
        assert forbidden not in source


def test_remote_probe_is_read_only_and_cleans_up() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    remote = source.split("$remoteCommand = @'", 1)[1].split("'@", 1)[0]
    for marker in (
        "sha256sum \"/dev/mtdblock$n\"",
        "cmp -s \"$tmp/mtd.before\" \"$tmp/mtd.after\"",
        "cmp -s \"$tmp/hashes.before\" \"$tmp/hashes.after\"",
        "insmod \"$module\"",
        "rmmod \"$name\"",
        "MODULE_UNLOADED=1",
        "OBSERVER_DISABLED=1",
        "MTD_REGISTRATION_ABSENT=1",
        "store_dpb_scan_count",
        "security_register",
        "status_register",
    ):
        assert marker in remote
    for forbidden in (
        "flash_erase",
        "nandwrite",
        "mtd_debug",
        "flashcp",
        "dd of=/dev/mtd",
        "eraseall",
        "fw_setenv",
    ):
        assert forbidden not in remote


def test_dry_run_is_offline_and_ready_with_clear_guards(tmp_path: Path) -> None:
    output = tmp_path / "dry-run"
    state = tmp_path / "state"
    lock = tmp_path / "locks/f301-physical-radio.lock"
    state.mkdir()
    proc, plan = invoke_dry_run(output, state, lock)
    assert proc.returncode == 0, proc.stdout
    assert plan["mode"] == "dry-run"
    assert plan["required_firmware"] == EXPECTED_FIRMWARE
    assert plan["candidate_sha256"] == EXPECTED_FIRMWARE_SHA256
    assert plan["module_sha256"] == EXPECTED_MODULE_SHA256
    assert plan["local_preflight_pass"] is True
    assert plan["campaign_guard"]["active"] is False
    assert plan["execute_allowed_now"] is True
    assert plan["hardware_actions_performed"] is False
    assert plan["hardware_preflight"] == "DEFERRED_UNTIL_EXECUTE"
    assert plan["persistent_writes"] is False
    assert plan["mtd_writes"] is False


def test_dry_run_blocks_in_progress_soak_checkpoint(tmp_path: Path) -> None:
    state = tmp_path / "state"
    checkpoint = state / "soak/f301-sequential-dual-radio-test/checkpoint.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(
        json.dumps(
            {
                "schema": "openmitrastar.f301-sequential-dual-radio-soak-checkpoint/v1",
                "status": "IN_PROGRESS",
                "updated_at": "2026-09-04T12:53:50+00:00",
                "cycles_completed": 2,
            }
        ),
        encoding="ascii",
    )
    proc, plan = invoke_dry_run(tmp_path / "output", state, tmp_path / "lock")
    assert proc.returncode == 0, proc.stdout
    assert plan["campaign_guard"]["active"] is True
    assert len(plan["campaign_guard"]["in_progress_checkpoints"]) == 1
    assert plan["execute_allowed_now"] is False
    assert plan["hardware_actions_performed"] is False


def test_dry_run_blocks_multicast_shared_lock(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock = tmp_path / "locks/f301-physical-radio.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps(
            {
                "schema": "openmitrastar.f301-physical-radio-lock/v1",
                "owner": "f301-multicast-igmp",
                "pid": 1234,
            }
        ),
        encoding="ascii",
    )
    proc, plan = invoke_dry_run(tmp_path / "output", state, lock)
    assert proc.returncode == 0, proc.stdout
    assert plan["campaign_guard"]["active"] is True
    assert plan["campaign_guard"]["shared_lock_present"] is True
    assert plan["campaign_guard"]["shared_lock_owner"]["owner"] == "f301-multicast-igmp"
    assert plan["execute_allowed_now"] is False


def test_execute_refuses_guard_path_overrides_before_hardware(tmp_path: Path) -> None:
    output = tmp_path / "execute-refused"
    state = tmp_path / "state"
    state.mkdir()
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Execute",
            "-Ack",
            "OPENMITRASTAR_F301_STORE_PROTECTION_READONLY_2F00A2DB",
            "-OutputDir",
            str(output),
            "-CampaignStateRoot",
            str(state),
            "-SharedLockDir",
            str(tmp_path / "lock"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    assert proc.returncode != 0
    assert "refuses campaign-state or lock-path overrides" in proc.stdout
    plan = json.loads((output / "plan.json").read_text(encoding="ascii"))
    assert plan["hardware_actions_performed"] is False
