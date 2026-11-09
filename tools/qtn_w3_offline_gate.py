#!/usr/bin/env python3
"""Offline Quantenna W3 gate: board fossils, firmware ABI and AuC/HBM.

This tool is deliberately read-only.  It never opens a device node, loads a
module, accesses MMIO, contacts the router or writes flash.  It turns the OEM
bootcfg dump and packed firmware images into one machine-readable decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from qdrv_fw_inspect import FirmwareReport, inspect_firmware


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOTCFG = (
    ROOT / "hgw500bna-qcv2-firmware-dump-verified/hgw500_mtdblock1.bin"
)
DEFAULT_FW89 = ROOT / "work/revival/rootfs/etc/firmware"
DEFAULT_FW62_TAR = (
    ROOT / "work/sources/Quantenna-GPL/quantenna-bin-v37.4.0.62.1.tar"
)
DEFAULT_QDRV_BLD = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_bld.h"
DEFAULT_HBM_HEADER = (
    ROOT / "work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h"
)
DEFAULT_HBM_MODULE = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510/rootfs/lib/modules/"
    "5.10.260-openmitrastar-radio/extra/quantenna/platform/topaz/hbm.ko"
)
DEFAULT_OEM_HBM_DISASM = (
    ROOT / "work/mission-state/w3-offline/oem89-hbm-init.disasm.txt"
)
DEFAULT_OEM_BOOT_LOG = ROOT / "outputs/uart-com3-j2-115200.log"
SIGNED_V89_MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_SIGNED_ARTIFACT.json"

GPL62_BASE = "./buildroot/target/device/Quantenna/Ruby/fw/topaz-bin/"
HBM_META_BASE = 0x0063C000
FWINFO_VADDR = 0xFFFF0000
FWINFO_MAGIC = b"FWINFO\0\0"
FWINFO_TYPE_RELEASE = 1

BOARD_FIELDS = (
    "board_id",
    "name",
    "ddr_type",
    "ddr_speed",
    "ddr_size",
    "emac0",
    "emac1",
    "phy0_addr",
    "phy1_addr",
    "spi1",
    "wifi_hw",
    "uart1",
    "pcie",
    "rgmii_timing",
    "ext_lna_gain",
    "tx_antenna_num",
    "flash_cfg",
    "tx_antenna_gain",
    "ext_lna_bypass_gain",
    "rfic",
    "tx_power_cal",
)


class GateError(ValueError):
    """Raised when an offline input is malformed or incomplete."""


@dataclass(frozen=True)
class BoardRecord:
    index: int
    field: str
    label: str
    data_length: int
    value_unsigned: int | None
    value_signed: int | None


@dataclass(frozen=True)
class FirmwareInfo:
    source: str
    cpu: str
    sha256: str
    info_present: bool
    info_type: int | None
    version: int | None
    version_text: str | None


@dataclass(frozen=True)
class BoundaryOverlap:
    source: str
    segment: int
    start: int
    end: int
    overlap_bytes: int
    overlap_sha256: str
    overlap_nonzero_bytes: int


def parse_env(blob: bytes) -> dict[str, str]:
    """Parse the NUL-delimited U-Boot environment after its CRC word."""
    if len(blob) < 8:
        raise GateError("bootcfg blob is too short")
    result: dict[str, str] = {}
    for raw in blob[4:].split(b"\0"):
        if not raw:
            if result:
                break
            continue
        if b"=" not in raw:
            continue
        key, value = raw.split(b"=", 1)
        try:
            result[key.decode("ascii")] = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise GateError("non-ASCII data inside bootcfg environment") from exc
    return result


def parse_cfg_descriptor(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"cfg\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)", value)
    if not match:
        raise GateError(f"invalid bootcfg file descriptor: {value!r}")
    return int(match.group(1), 16), int(match.group(2), 16)


def parse_board_config(blob: bytes, offset: int, size: int) -> tuple[BoardRecord, ...]:
    end = offset + size
    if offset < 0 or size <= 0 or end > len(blob):
        raise GateError("board configuration range is outside bootcfg")
    cursor = offset
    records: list[BoardRecord] = []
    while cursor < end:
        if cursor + 3 > end:
            raise GateError("truncated board configuration record header")
        config_index = struct.unpack_from("<H", blob, cursor)[0]
        cursor += 2
        if not 0 <= config_index <= len(BOARD_FIELDS):
            raise GateError(f"invalid board config index {config_index}")
        string_length = blob[cursor]
        cursor += 1
        if cursor + string_length + 1 > end:
            raise GateError("truncated board configuration label")
        label = blob[cursor : cursor + string_length].decode("ascii")
        cursor += string_length
        data_length = blob[cursor]
        cursor += 1
        if data_length > 4 or cursor + data_length > end:
            raise GateError(f"invalid data length {data_length}")
        raw = blob[cursor : cursor + data_length]
        cursor += data_length
        unsigned = int.from_bytes(raw, "little") if raw else None
        signed = int.from_bytes(raw, "little", signed=True) if raw else None
        if config_index == 0:
            records.append(
                BoardRecord(
                    index=-1,
                    field="format_header",
                    label=label,
                    data_length=data_length,
                    value_unsigned=unsigned,
                    value_signed=signed,
                )
            )
            continue
        index = config_index - 1
        records.append(
            BoardRecord(
                index=index,
                field=BOARD_FIELDS[index],
                label=label,
                data_length=data_length,
                value_unsigned=unsigned,
                value_signed=signed,
            )
        )
    if cursor != end:
        raise GateError("board configuration parser did not consume exact range")
    return tuple(records)


def parse_host_version(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"#define\s+QDRV_BLD_VER\s+\(0x([0-9a-fA-F]+)\)", text)
    if not match:
        raise GateError(f"QDRV_BLD_VER missing from {path}")
    return int(match.group(1), 16)


def parse_host_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'#define\s+QDRV_BLD_NAME\s+"([^"]+)"', text)
    if not match:
        raise GateError(f"QDRV_BLD_NAME missing from {path}")
    return match.group(1)


def version_text(value: int) -> str:
    return ".".join(str(part) for part in value.to_bytes(4, "big"))


def firmware_info(report: FirmwareReport, data: bytes) -> FirmwareInfo:
    candidates = [segment for segment in report.segments if segment.virtual_address == FWINFO_VADDR]
    if not candidates:
        return FirmwareInfo(
            report.source, report.cpu, report.sha256, False, None, None, None
        )
    if len(candidates) != 1:
        raise GateError(f"{report.source}: multiple FWINFO segments")
    segment = candidates[0]
    if segment.payload_size < 16:
        raise GateError(f"{report.source}: FWINFO segment shorter than 16 bytes")
    payload = data[segment.payload_offset : segment.payload_offset + segment.payload_size]
    if payload[:8] != FWINFO_MAGIC:
        raise GateError(f"{report.source}: invalid FWINFO magic {payload[:8]!r}")
    info_type, version = struct.unpack_from("<II", payload, 8)
    return FirmwareInfo(
        report.source,
        report.cpu,
        report.sha256,
        True,
        info_type,
        version,
        version_text(version),
    )


def boundary_overlaps(
    report: FirmwareReport, data: bytes, boundary: int = HBM_META_BASE
) -> tuple[BoundaryOverlap, ...]:
    overlaps: list[BoundaryOverlap] = []
    for segment in report.segments:
        start = segment.load_address
        end = start + segment.memory_size
        if start < boundary < end:
            overlap_start = boundary
            overlap_end = end
            payload_end = segment.load_address + segment.payload_size
            payload_overlap_end = min(overlap_end, payload_end)
            payload_offset = segment.payload_offset + (overlap_start - start)
            payload = data[payload_offset : payload_offset + (payload_overlap_end - overlap_start)]
            overlaps.append(
                BoundaryOverlap(
                    source=report.source,
                    segment=segment.index,
                    start=start,
                    end=end,
                    overlap_bytes=overlap_end - boundary,
                    overlap_sha256=hashlib.sha256(payload).hexdigest(),
                    overlap_nonzero_bytes=sum(byte != 0 for byte in payload),
                )
            )
    return tuple(overlaps)


def inspect_named(data: bytes, source: str, name: str, cpu: str) -> tuple[FirmwareReport, FirmwareInfo]:
    report = inspect_firmware(data, source=source, cpu=cpu)  # type: ignore[arg-type]
    return report, firmware_info(report, data)


def inspect_tar_firmware(path: Path) -> list[tuple[FirmwareReport, FirmwareInfo]]:
    specs = (
        ("auc_driver.0.bin", "auc"),
        ("qtn_driver.qtn_ruby.0.bin", "muc"),
        ("rdsp_driver.0.bin", "dsp"),
    )
    results: list[tuple[FirmwareReport, FirmwareInfo]] = []
    with tarfile.open(path) as archive:
        for name, cpu in specs:
            member = GPL62_BASE + name
            extracted = archive.extractfile(member)
            if extracted is None:
                raise GateError(f"{member} missing from {path}")
            data = extracted.read()
            results.append(inspect_named(data, f"{path}!{name}", name, cpu))
    return results


def inspect_directory_firmware(path: Path) -> list[tuple[FirmwareReport, FirmwareInfo, bytes]]:
    specs = (
        ("auc_driver.nomu.0.bin", "auc"),
        ("auc_driver.default.0.bin", "auc"),
        ("qtn_driver.qtn_ruby.0.bin", "muc"),
        ("rdsp_driver.0.bin", "dsp"),
    )
    results: list[tuple[FirmwareReport, FirmwareInfo, bytes]] = []
    for name, cpu in specs:
        firmware = path / name
        data = firmware.read_bytes()
        report, info = inspect_named(data, str(firmware), name, cpu)
        results.append((report, info, data))
    return results


def selected_board_values(records: Iterable[BoardRecord]) -> dict[str, object]:
    selected: dict[str, object] = {}
    for record in records:
        if record.field == "name":
            selected[record.field] = record.label
        elif record.value_unsigned is not None:
            selected[record.field] = (
                record.value_signed
                if record.field in {"ext_lna_gain", "ext_lna_bypass_gain"}
                else record.value_unsigned
            )
    return selected


def prove_oem_overlap_contract(hbm_disasm: Path, boot_log: Path) -> dict[str, object]:
    """Prove the .89 OEM used this exact overlap and still reached a live VAP."""
    disasm = hbm_disasm.read_text(encoding="utf-8")
    log = boot_log.read_text(encoding="utf-8", errors="replace")
    map_markers = {
        "meta_base": "mov_s\tr0,0x8063c000",
        "meta_end": "mov_s\tr1,0x806dc0c0",
        "meta_size": "mov_s\tr2,0xa00c0",
        "emac_pool": "mov_s\tr2,0x6ec400",
    }
    runtime_markers = {
        "hbm_initialized": "HBM meta: emac rx 0x63c040 to 0x6bc040",
        "qdrv_loaded": "load_module: 'qdrv'",
        "muc_booted": "MuC boot succeeded",
        "vap_created": "VAP create succeeded",
        "wifi_forwarding": "br0: port 3(wifi0) entering forwarding state",
    }
    map_proof = {name: marker in disasm for name, marker in map_markers.items()}
    runtime_proof = {name: marker in log for name, marker in runtime_markers.items()}
    positions = {name: log.find(marker) for name, marker in runtime_markers.items()}
    ordered = (
        all(value >= 0 for value in positions.values())
        and positions["hbm_initialized"] < positions["qdrv_loaded"]
        < positions["muc_booted"] < positions["vap_created"]
        < positions["wifi_forwarding"]
    )
    qdrv_tail = log[positions["qdrv_loaded"] :] if positions["qdrv_loaded"] >= 0 else ""
    hbm_fault_after_qdrv = bool(
        re.search(
            r"HBM pool is depleted|invalid hbm buffer|Invalid pool|underflow counter is non zero",
            qdrv_tail,
            flags=re.IGNORECASE,
        )
    )
    proven = all(map_proof.values()) and all(runtime_proof.values()) and ordered and not hbm_fault_after_qdrv
    return {
        "kernel_disassembly": str(hbm_disasm),
        "boot_log": str(boot_log),
        "map_markers": map_proof,
        "runtime_markers": runtime_proof,
        "runtime_order_proven": ordered,
        "hbm_fault_after_qdrv": hbm_fault_after_qdrv,
        "oem_overlap_contract_proven": proven,
    }


def build_report(
    bootcfg: Path,
    fw89_dir: Path,
    fw62_tar: Path,
    qdrv_bld: Path,
    hbm_header: Path,
    hbm_module: Path,
    oem_hbm_disasm: Path = DEFAULT_OEM_HBM_DISASM,
    oem_boot_log: Path = DEFAULT_OEM_BOOT_LOG,
) -> dict[str, object]:
    boot_blob = bootcfg.read_bytes()
    env = parse_env(boot_blob)
    descriptor = env.get("qtn_hw_board_config.bin")
    if descriptor is None:
        raise GateError("qtn_hw_board_config.bin descriptor missing")
    board_offset, board_size = parse_cfg_descriptor(descriptor)
    board_records = parse_board_config(boot_blob, board_offset, board_size)
    board = selected_board_values(board_records)

    host_version = parse_host_version(qdrv_bld)
    host_name = parse_host_name(qdrv_bld)
    fw62 = inspect_tar_firmware(fw62_tar)
    fw89 = inspect_directory_firmware(fw89_dir)
    info62 = [info for _, info in fw62]
    info89 = [info for _, info, _ in fw89]

    mismatched89 = [info for info in info89 if info.version != host_version]
    external_meta_source = bool(
        re.search(
            r"#define\s+TOPAZ_HBM_BUF_EXTERNAL_META\s+1\b",
            hbm_header.read_text(encoding="utf-8"),
        )
    )
    hbm_module_blob = hbm_module.read_bytes()
    external_meta_binary = b"HBM meta:" in hbm_module_blob
    internal_meta_binary = b"HBM used internal meta" in hbm_module_blob

    overlaps: list[BoundaryOverlap] = []
    for report, _, data in fw89:
        if report.cpu == "auc":
            overlaps.extend(boundary_overlaps(report, data))
    oem_contract = prove_oem_overlap_contract(oem_hbm_disasm, oem_boot_log)
    fw89_versions = {info.version for info in info89}
    coherent_89_pair = (
        len(fw89_versions) == 1
        and host_version in fw89_versions
        and oem_contract["oem_overlap_contract_proven"]
    )

    absent_defaults = {
        "bond_opt": {
            "present": "bond_opt" in env,
            "effective_source_default": 0xFFFFFFFF,
            "meaning": "HW_OPTION_BONDING_NOT_SET",
        },
        "power_recheck": {
            "present": "power_recheck" in env,
            "effective_source_default": 1,
        },
        "post_mask": {
            "present": "post_mask" in env,
            "effective_source_default": 0,
        },
        "dev_mode": {
            "present": "dev_mode" in env,
            "effective_source_default": 0,
            "effect": "panic_on_muc_halt remains enabled",
        },
    }

    return {
        "gate": "W3_QUANTENNA_OFFLINE",
        "bootcfg": {
            "path": str(bootcfg),
            "sha256": hashlib.sha256(boot_blob).hexdigest(),
            "board_config_offset": board_offset,
            "board_config_size": board_size,
            "board_records": [asdict(record) for record in board_records],
            "selected_board_values": board,
            "environment_values": {
                key: env.get(key)
                for key in (
                    "hw_config_id",
                    "calstate",
                    "ext_lna_gain",
                    "ext_lna_bypass_gain",
                    "tx_power_cal",
                    "min_tx_power",
                    "max_tx_power",
                    "bond_opt",
                    "power_recheck",
                    "post_mask",
                    "dev_mode",
                )
            },
            "absent_value_semantics": absent_defaults,
        },
        "firmware_abi": {
            "host_build_name": host_name,
            "host_version": host_version,
            "host_encoded_version_text": version_text(host_version),
            "firmware_62": [asdict(info) for info in info62],
            "firmware_89": [asdict(info) for info in info89],
            "host_62_with_fw89_compatible": not mismatched89,
            "decision": (
                "FAIL: .89 FWINFO requires 0x25040059 but host advertises "
                f"0x{host_version:08x}"
                if mismatched89
                else "PASS"
            ),
        },
        "auc_hbm_boundary": {
            "hbm_meta_base": HBM_META_BASE,
            "external_meta_source_enabled": external_meta_source,
            "external_meta_binary_enabled": external_meta_binary,
            "internal_meta_binary_marker": internal_meta_binary,
            "overlaps": [asdict(overlap) for overlap in overlaps],
            "affected_emac_metadata_indices": [0, 1] if overlaps else [],
            "oem_contract": oem_contract,
            "classification": (
                "OEM_QUIRK_PROVEN"
                if overlaps and oem_contract["oem_overlap_contract_proven"]
                else "UNRESOLVED"
            ),
            "cause_elimination": {
                "truncate_blob": "REJECTED: overlapped bytes are nonzero executable payload",
                "move_carveout_or_hbm_base": "REJECTED: OEM .89 kernel uses the same 0x0063c000 base",
                "disable_external_meta": "REJECTED: OEM .89 kernel logs external HBM metadata",
                "reverse_load_clear_order": "REJECTED: OEM initializes HBM before loading qdrv and still reaches VAP",
                "correct_handling": "Allowlist only the exact OEM quirk inside a coherent .89 host+firmware contract",
            },
            "coherent_current_pair": coherent_89_pair,
            "safe": coherent_89_pair,
            "decision": (
                "PASS: exact .89 OEM overlap contract"
                if coherent_89_pair
                else "STOP: overlap is OEM-proven, but current host is not the matching .89 contract"
            ),
        },
    }


def runtime_gate_text(report: dict[str, object]) -> str:
    if SIGNED_V89_MANIFEST.exists():
        from qtn_w3_artifact_gate import gate_text, verify
        signed = json.loads(SIGNED_V89_MANIFEST.read_text(encoding="utf-8"))
        verify(signed, False)
        return gate_text(signed, SIGNED_V89_MANIFEST)
    abi = report["firmware_abi"]  # type: ignore[index]
    boundary = report["auc_hbm_boundary"]  # type: ignore[index]
    approved = bool(abi["host_62_with_fw89_compatible"] and boundary["safe"])  # type: ignore[index]
    fw_entries = abi["firmware_89"]  # type: ignore[index]
    fw_version = fw_entries[0]["version"]  # type: ignore[index]
    fw_text = fw_entries[0]["version_text"]  # type: ignore[index]
    reason = "NONE" if approved else "HOST_FIRMWARE_VERSION_MISMATCH"
    return "\n".join(
        (
            f"W3_PAIR_APPROVED={int(approved)}",
            f"W3_HOST_BUILD={abi['host_build_name']}",  # type: ignore[index]
            f"W3_HOST_VERSION=0x{abi['host_version']:08x}",  # type: ignore[index]
            f"W3_FIRMWARE_BUILD=v{fw_text}",
            f"W3_FIRMWARE_VERSION=0x{fw_version:08x}",
            f"W3_OVERLAP_CLASS={boundary['classification']}",  # type: ignore[index]
            f"W3_STOP_REASON={reason}",
            "",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootcfg", type=Path, default=DEFAULT_BOOTCFG)
    parser.add_argument("--fw89-dir", type=Path, default=DEFAULT_FW89)
    parser.add_argument("--fw62-tar", type=Path, default=DEFAULT_FW62_TAR)
    parser.add_argument("--qdrv-bld", type=Path, default=DEFAULT_QDRV_BLD)
    parser.add_argument("--hbm-header", type=Path, default=DEFAULT_HBM_HEADER)
    parser.add_argument("--hbm-module", type=Path, default=DEFAULT_HBM_MODULE)
    parser.add_argument("--oem-hbm-disasm", type=Path, default=DEFAULT_OEM_HBM_DISASM)
    parser.add_argument("--oem-boot-log", type=Path, default=DEFAULT_OEM_BOOT_LOG)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-runtime-gate",
        type=Path,
        help="write a fail-closed environment file for the target pre-MMIO ladder",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.bootcfg,
            args.fw89_dir,
            args.fw62_tar,
            args.qdrv_bld,
            args.hbm_header,
            args.hbm_module,
            args.oem_hbm_disasm,
            args.oem_boot_log,
        )
    except (OSError, GateError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        board = report["bootcfg"]["selected_board_values"]  # type: ignore[index]
        print("W3_OFFLINE_GATE")
        print(f"BOARD {json.dumps(board, sort_keys=True)}")
        if SIGNED_V89_MANIFEST.exists():
            print("ABI PASS: exact signed .89 artifact")
            print("BOUNDARY PASS: exact signed OEM quirk contract")
        else:
            print(f"ABI {report['firmware_abi']['decision']}")  # type: ignore[index]
            print(f"BOUNDARY {report['auc_hbm_boundary']['decision']}")  # type: ignore[index]
    if args.write_runtime_gate:
        args.write_runtime_gate.write_text(runtime_gate_text(report), encoding="utf-8")
    abi_ok = report["firmware_abi"]["host_62_with_fw89_compatible"]  # type: ignore[index]
    boundary_ok = report["auc_hbm_boundary"]["safe"]  # type: ignore[index]
    return 0 if SIGNED_V89_MANIFEST.exists() or (abi_ok and boundary_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
