#!/usr/bin/env python3
"""F320 file-only campaign contracts. Importing this module touches no hardware."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zlib

from prepare_f320_spi_read_gate import inspect_candidate, ROOT, EXPECTED_IMAGE, EXPECTED_MODULE
from build_f320_spi_control_firmware import DEVICE
from bootbase_contract_emulator import validate_bootbase_slot

ACK = "OPENMITRASTAR_F320_MTD4_66FF3E8F"
PNP = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
VERSIONS = {
    "f314": ("lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device",
             "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11", "d6b13baa"),
    "f319": ("lyoko-foundation-6.8.3-f319-spi-owner-claim-device",
             "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9", "22d3802a"),
    "f320": ("lyoko-foundation-6.8.4-f320-spi-control-read-device", EXPECTED_IMAGE, "f7e832d9"),
}
SOURCES = [
    "tools/f320_campaign_contract.py", "tools/f320_campaign.ps1", "tools/promote_f320_mtd4.ps1",
    "tools/f320_spi_read.sh", "tools/test_f320_campaign.py", "tools/test_f320_campaign_behavior.ps1",
    "tools/qualify_f320_campaign.py", "tools/prepare_f320_spi_read_gate.py",
    "tools/build_f320_spi_control_firmware.py", "tools/f319_uart_guard.ps1", "tools/f319_recovery_guard.ps1",
    "tools/capture_topaz_uart_resilient.ps1", "tools/reboot_to_topaz_prompt_sysrq.ps1",
    "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py",
    "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1",
    "tools/tftp_serve_once.py", "tools/f319_flash_fallback.py", "tools/post_flash_f214_device_gate.py",
    "tools/bootbase_contract_emulator.py", "tools/uart_ymodem_load.py",
]
FATAL = r"kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check|MuC:.*exception|MuC has halted|EV_TLB|EV_ProtV|VFS: Unable to mount root"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_all():
    inspect_candidate()
    images = {}
    for tag, (version, expected, crc) in VERSIONS.items():
        folder = DEVICE / (tag + "-device-bound")
        stem = f"openmitrastar-linux510-{tag}-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
        image = folder / (stem + ".webformat.bin")
        data = image.read_bytes()
        if len(data) != 5292032 or sha(image) != expected:
            raise ValueError(f"{tag} exact image mismatch")
        full = data + b"\xff" * (0x7a0000 - len(data))
        if f"{zlib.crc32(full) & 0xffffffff:08x}" != crc:
            raise ValueError(f"{tag} full-slot CRC mismatch")
        if not validate_bootbase_slot(str(image), data, 0x7a0000).accepted_by_contract:
            raise ValueError(f"{tag} Bootbase contract failed")
        known_hosts = folder / ("known_hosts." + tag)
        if not known_hosts.is_file() or not known_hosts.stat().st_size:
            raise ValueError(f"{tag} missing pinned identity")
        # Pin all writer inputs as well as the webformat image. The immutable
        # offline manifest is not edited to pretend a physical acceptance.
        inputs = [folder / "manifest.json", folder / "bootbase-contract.json", known_hosts]
        inputs += [folder / (stem + suffix) for suffix in
                   (".kernel.raw.bin", ".config", ".rootfs.squashfs", ".dtb")]
        images[tag] = dict(version=version, folder=str(folder), stem=stem, path=str(image),
                           sha256=expected, bytes=len(data), full_slot_crc32=crc,
                           full_slot_sha256=hashlib.sha256(full).hexdigest(), known_hosts=str(known_hosts),
                           inputs={str(p): sha(p) for p in inputs})
    return images


def verify_qualification(path, images):
    proof = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (proof.get("schema") != "openmitrastar.f320-campaign-qualification/v1"
            or proof.get("status") != "PASS_OFFLINE" or proof.get("hardware_actions") is not False
            or proof.get("images") != images or proof.get("required_ack") != ACK):
        raise ValueError("F320 qualification does not match exact inputs")
    if proof.get("sources") != {p: sha(ROOT / p) for p in SOURCES}:
        raise ValueError("F320 executor sources changed after qualification")
    from xml.etree import ElementTree as ET
    junit = Path(path).parent / "tests.xml"
    if sha(junit) != proof.get("tests_xml_sha256"):
        raise ValueError("qualification test evidence changed")
    suites = ET.parse(junit).getroot().findall("testsuite")
    if len(suites) != 1 or any(int(suites[0].get(k, "0")) for k in ("failures", "errors", "skipped")):
        raise ValueError("qualification has failed/missing cases")
    actual_cases = {c.attrib["name"] for c in suites[0].findall("testcase")}
    required = {"test_campaign_behavior[powershell.exe]", "test_campaign_behavior[pwsh.exe]",
                "test_exact_artifacts_and_writer_dry_runs", "test_runtime_valid", "test_shell_one_load_no_retry"}
    if not required <= actual_cases or len(actual_cases) < 20:
        raise ValueError("qualification lacks required behavioral tests")
    return proof


def verify_runtime(stdout, uart, run_id):
    if not re.fullmatch(r"f320-[0-9a-f]{32}", run_id):
        raise ValueError("invalid capture ID")
    fields = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in fields:
            raise ValueError("duplicate runtime field")
        fields[key] = value
    required = dict(execute_read="Y", controller_resource_claimed="Y", controller_mapped="Y",
                    legacy_map_verified="Y", map_read_count="1", controller_read_count="1",
                    controller_write_count="0", transaction_provider_ready="N", MODULE_UNLOADED="1",
                    FATAL_BEFORE="0", FATAL_AFTER="0")
    if any(fields.get(k) != v for k, v in required.items()):
        raise ValueError("runtime invariant mismatch")
    mtd = fields.get("MTD_TABLE_HASH_BEFORE", "")
    if not re.fullmatch(r"[0-9a-f]{64}", mtd) or mtd != fields.get("MTD_TABLE_HASH_AFTER"):
        raise ValueError("MTD table changed")
    values = []
    for key in ("map_register_value", "controller_value"):
        value = fields.get(key, "")
        if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) > 0xffffffff:
            raise ValueError("invalid u32 snapshot")
        values.append(int(value))
    map_value, control = values
    if map_value & 0x60000000:
        raise ValueError("legacy map bits not clear")
    if stdout.splitlines().count("OMF320_SPI_CONTROL_PASS") != 1 or re.search(FATAL, uart, re.I):
        raise ValueError("missing PASS or fatal UART")
    number = r"(0x[0-9a-f]+|0)"
    patterns = [r"(?m)^" + re.escape(run_id) + r"_BEGIN\r?$",
                r"OMSPICTRL map-read-begin address=0xe0000004\r?$",
                r"OMSPICTRL control-read-begin address=0xe2000004 map=" + number + r"\r?$",
                r"OMSPICTRL control-read-done value=" + number + r" map_reads=1 reads=1 writes=0 provider=0\r?$",
                r"OMSPICTRL released map_reads=1 reads=1 writes=0 provider=0\r?$",
                r"(?m)^" + re.escape(run_id) + r"_END\r?$"]
    hits = [list(re.finditer(p, uart, re.M)) for p in patterns]
    if any(len(h) != 1 for h in hits) or [h[0].start() for h in hits] != sorted(h[0].start() for h in hits):
        raise ValueError("UART does not contain exactly one ordered read/unload")
    if int(hits[2][0].group(1), 0) != map_value or int(hits[3][0].group(1), 0) != control:
        raise ValueError("UART and SSH snapshots disagree")
    return dict(status="PASS", map_register_value=map_value, controller_value=control,
                map_reads=1, spi_reads=1, writes=0, provider=False, mtd_table_unchanged=True,
                uart_sequence=True, module_unloaded=True, no_fatal=True)


def verify_writer(path, tag):
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    _, expected, crc = VERSIONS[tag]
    physical = result.get("physical_write", {})
    readback = result.get("readback", {})
    if (result.get("status") != "PASS" or result.get("candidate_sha256") != expected
            or physical != dict(offset=0x7e0000, erase_size=0x5e0000, candidate_size=5292032,
                                slot_size=0x7a0000, partition="mtd4/linux_live")
            or readback.get("full_slot_crc32") != crc or readback.get("candidate_prefix_compare") != "PASS"
            or result.get("protected_partitions", {}).get("status") != "PASS"):
        raise ValueError("writer did not prove an exact completed write")
    evidence = result.get("evidence", [])
    if len(evidence) != 3:  # This campaign is TFTP-only, no alternate transports.
        raise ValueError("writer capture evidence missing")
    for row in evidence:
        if sha(ROOT / row["path"]) != row["sha256"]:
            raise ValueError("writer evidence changed")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qualification", type=Path)
    p.add_argument("--writer-result", type=Path)
    p.add_argument("--tag", choices=VERSIONS)
    p.add_argument("--runtime-dir", type=Path)
    p.add_argument("--run-id")
    args = p.parse_args()
    if args.writer_result:
        verify_writer(args.writer_result, args.tag)
        print(json.dumps({"status": "PASS"}))
    elif args.runtime_dir:
        result = verify_runtime((args.runtime_dir / "probe.stdout.log").read_text(),
                                (args.runtime_dir / "uart/uart.log").read_text(), args.run_id)
        print(json.dumps(result))
    else:
        images = inspect_all()
        if args.qualification:
            verify_qualification(args.qualification, images)
        print(json.dumps(dict(images=images, required_ack=ACK, pnp=PNP,
                              generated_at=datetime.now(timezone.utc).isoformat(),
                              qualification="PASS_OFFLINE" if args.qualification else "NOT_CHECKED")))


if __name__ == "__main__":
    main()
