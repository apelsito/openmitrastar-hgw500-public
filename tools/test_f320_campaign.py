"""F320 executor qualification: real file/lock behavior, synthetic hardware only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
import f320_campaign_contract as gate


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
def test_campaign_behavior(engine, tmp_path):
    binary = shutil.which(engine)
    assert binary, f"Required engine missing: {engine}"
    p = subprocess.run([binary, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(gate.ROOT / "tools/test_f320_campaign_behavior.ps1"), "-Scope", str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    report = json.loads(p.stdout)
    assert report["status"] == "PASS" and report["hardware_actions"] is False
    assert len(report["cases"]) >= 60


def writer_environment(images, target, current):
    image, previous = images[target], images[current]
    folder, stem = Path(image["folder"]), image["stem"]
    env = os.environ.copy()
    # No backend override, execution flag, SSH or network operations in this test.
    env.update(OM_Q3_FLASH_ACK=gate.ACK, OM_Q3_FLASH_BUILD_DIR=str(folder),
               OM_Q3_FLASH_CANDIDATE=image["path"], OM_Q3_FLASH_BOOTBASE_CONTRACT=str(folder / "bootbase-contract.json"),
               OM_Q3_FLASH_MANIFEST=str(folder / "manifest.json"),
               OM_Q3_FLASH_INITRAMFS=str(folder / (stem + ".kernel.raw.bin")),
               OM_Q3_FLASH_KCONFIG=str(folder / (stem + ".config")), OM_Q3_FLASH_LAYOUT_MODE="squashfs-split",
               OM_Q3_FLASH_ROOTFS_IMAGE=str(folder / (stem + ".rootfs.squashfs")),
               OM_Q3_FLASH_DTB=str(folder / (stem + ".dtb")), OM_Q3_FLASH_ROOTFS_OFFSET="0x180000",
               OM_Q3_FLASH_EXPECTED_SHA256=image["sha256"], OM_Q3_FLASH_EXPECTED_BYTES="5292032",
               OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32=previous["full_slot_crc32"],
               OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256=previous["full_slot_sha256"],
               OM_Q3_F45_REQUIRE_BACKUP_LIVE_SLOT_MATCH="0",
               OM_Q3_FLASH_POWERSHELL_BACKEND=str(gate.ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1"))
    return env


def test_exact_artifacts_and_writer_dry_runs():
    images = gate.inspect_all()
    writer = gate.ROOT / "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
    for target, current in [("f320", "f319"), ("f314", "f320")]:
        # Absence of --execute returns after file-only validate_local_inputs().
        p = subprocess.run([sys.executable, str(writer), "--erase-bytes", "0x5e0000"],
                           env=writer_environment(images, target, current), capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "DRY_RUN_PASS=1 ready=1 flash=0" in p.stdout
        assert images[target]["sha256"] in p.stdout
        assert images[current]["full_slot_crc32"] in p.stdout


def runtime_fixture():
    run = "f320-" + "a" * 32
    text = "\n".join([
        "execute_read=Y", "controller_resource_claimed=Y", "controller_mapped=Y", "legacy_map_verified=Y",
        "map_register_value=4", "map_read_count=1", "controller_value=64", "controller_read_count=1",
        "controller_write_count=0", "transaction_provider_ready=N", "MTD_TABLE_HASH_BEFORE=" + "a" * 64,
        "MTD_TABLE_HASH_AFTER=" + "a" * 64, "FATAL_BEFORE=0", "FATAL_AFTER=0", "MODULE_UNLOADED=1",
        "OMF320_SPI_CONTROL_PASS", ""])
    uart = "\n".join([run + "_BEGIN", "[ 21.0] OMSPICTRL map-read-begin address=0xe0000004",
        "[ 21.1] OMSPICTRL control-read-begin address=0xe2000004 map=0x4",
        "[ 21.2] OMSPICTRL control-read-done value=0x40 map_reads=1 reads=1 writes=0 provider=0",
        "[ 21.3] OMSPICTRL released map_reads=1 reads=1 writes=0 provider=0", run + "_END", ""])
    return text, uart, run


def test_runtime_valid():
    result = gate.verify_runtime(*runtime_fixture())
    assert result["status"] == "PASS" and result["spi_reads"] == 1 and result["writes"] == 0


@pytest.mark.parametrize("old,new", [
    ("execute_read=Y", "execute_read=N"), ("controller_resource_claimed=Y", "controller_resource_claimed=N"),
    ("controller_mapped=Y", "controller_mapped=N"), ("legacy_map_verified=Y", "legacy_map_verified=N"),
    ("map_read_count=1", "map_read_count=2"), ("controller_read_count=1", "controller_read_count=0"),
    ("controller_read_count=1", "controller_read_count=2"), ("controller_write_count=0", "controller_write_count=1"),
    ("transaction_provider_ready=N", "transaction_provider_ready=Y"), ("MODULE_UNLOADED=1", "MODULE_UNLOADED=0"),
    ("FATAL_BEFORE=0", "FATAL_BEFORE=1"), ("FATAL_AFTER=0", "FATAL_AFTER=1"),
    ("map_register_value=4", "map_register_value=536870912"), ("controller_value=64", "controller_value=65"),
    ("controller_value=64", "controller_value=4294967296"), ("controller_value=64", "controller_value=-1"),
    ("MTD_TABLE_HASH_AFTER=" + "a" * 64, "MTD_TABLE_HASH_AFTER=" + "b" * 64),
    ("OMF320_SPI_CONTROL_PASS", ""), ("controller_read_count=1", "controller_read_count=1\ncontroller_read_count=1"),
])
def test_runtime_rejects_wrong_snapshot(old, new):
    text, uart, run = runtime_fixture()
    with pytest.raises(ValueError):
        gate.verify_runtime(text.replace(old, new), uart, run)


@pytest.mark.parametrize("change", ["fatal", "second_read", "missing_end", "wrong_run", "alias", "map_disagrees", "order"])
def test_runtime_rejects_wrong_uart(change):
    text, uart, run = runtime_fixture()
    if change == "fatal": uart += "Machine Check\n"
    if change == "second_read": uart += "OMSPICTRL map-read-begin address=0xe0000004\n"
    if change == "missing_end": uart = uart.replace(run + "_END", "")
    if change == "wrong_run": uart = uart.replace(run, "f320-" + "b" * 32)
    if change == "alias": uart = uart.replace("0xe2000004", "0xe4030004")
    if change == "map_disagrees": uart = uart.replace("map=0x4", "map=0x8")
    if change == "order": uart = "\n".join(reversed(uart.splitlines()))
    with pytest.raises(ValueError): gate.verify_runtime(text, uart, run)


def test_shell_one_load_no_retry():
    shell = (gate.ROOT / "tools/f320_spi_read.sh").read_text()
    assert shell.count("\ninsmod ") == 1
    assert 'insmod "$module" execute_read=1' in shell
    assert shell.index('test "$fatal_before" = 0') < shell.index("\ninsmod ")
    for forbidden in ("/dev/mem", "spi_flash", "flashcp", "reboot", "while ", "sleep "):
        assert forbidden not in shell


def test_runtime_capture_precedes_only_probe_and_timeout_keeps_rx():
    source = (gate.ROOT / "tools/f320_campaign.ps1").read_text()
    probe = source.split("function Invoke-F320Probe", 1)[1].split("function Restore-F320ExactF314", 1)[0]
    assert probe.index("Wait-F319UartCaptureReady") < probe.index("$Context.ProbeAttempted = $true")
    assert probe.index("$Context.ProbeAttempted = $true") < probe.index("$result = Invoke-F320Ssh")
    assert probe.count("$result = Invoke-F320Ssh") == 1
    assert probe.index("$uart.Handle") < probe.index("Wait-F319UartCaptureReady")
    assert probe.index("$captureDeadline = [DateTime]::UtcNow.AddSeconds(70)") < probe.index("$result = Invoke-F320Ssh")
    assert probe.index("$uart.WaitForExit([Math]::Min(30000") < probe.index("$uart.Kill()")
    assert "-CaptureExitCode $uart.ExitCode" in probe
    assert "Invoke-F320Bootbase" not in probe


def test_qualification_requires_unchanged_sources(tmp_path):
    images = {"synthetic": True}
    proof = dict(schema="openmitrastar.f320-campaign-qualification/v1", status="PASS_OFFLINE",
                 hardware_actions=False, images=images, required_ack=gate.ACK,
                 sources={p: gate.sha(gate.ROOT / p) for p in gate.SOURCES})
    proof["sources"]["tools/f320_campaign.ps1"] = "0" * 64
    path = tmp_path / "result.json"
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="sources changed"):
        gate.verify_qualification(path, images)


def test_writer_rejects_absent_completion(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"status": "PASS", "candidate_sha256": gate.EXPECTED_IMAGE}))
    with pytest.raises(ValueError, match="completed write"):
        gate.verify_writer(path, "f320")


def test_entrypoint_old_authority_rejected_before_output_dir(tmp_path):
    destination = tmp_path / ("must-not-exist-" + uuid.uuid4().hex)
    p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(gate.ROOT / "tools/promote_f320_mtd4.ps1"), "-Execute", "-Ack", "OPENMITRASTAR_F319_MTD4_E33D8511",
                        "-OutputDir", str(destination)], capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and not destination.exists()
    assert "F319 authority is not reusable" in p.stderr
