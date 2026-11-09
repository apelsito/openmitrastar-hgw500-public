#!/usr/bin/env python3
"""Build an offline .62.1 -> .89 Quantenna qdrv ABI difference matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
OEM_QDRV = ROOT / "work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/qdrv/qdrv.ko"
PORT_QDRV = ROOT / "outputs/kernel-port/quantenna-linux510/rootfs/lib/modules/5.10.260-openmitrastar-radio/extra/quantenna/qdrv/qdrv.ko"
OEM_WLAN = ROOT / "work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/wlan/wlan.ko"
PORT_WLAN = ROOT / "outputs/kernel-port/quantenna-linux510/rootfs/lib/modules/5.10.260-openmitrastar-radio/extra/quantenna/wlan/wlan.ko"
OEM_SOC_DISASM = ROOT / "work/mission-state/w3-offline/oem89-qdrv_soc_init.disasm.txt"
OEM_AUC_DISASM = ROOT / "work/mission-state/w3-offline/oem89-qdrv_auc_init.disasm.txt"
OEM_STATS_DISASM = ROOT / "work/mission-state/w3-offline/oem89-qdrv_auc_stats_setup.disasm.txt"
OEM_CCA_DISASM = ROOT / "work/mission-state/w3-offline/oem89-qdrv_async_cca_read.disasm.txt"
OEM_MUC_DECOMP = ROOT / "outputs/radio-re/decompiled/firmware/qtn_driver.qtn_ruby.0.bin.named.decompiled.c"
OEM_DSP_DECOMP = ROOT / "outputs/radio-re/decompiled/firmware/rdsp_driver.0.bin.decompiled.c"
OEM_WLAN_DECOMP = ROOT / "outputs/radio-re/decompiled/full/wlan.ko.decompiled.c"
OEM_QDRV_FULL_DISASM = ROOT / "work/mission-state/w3-offline/oem89-qdrv-full.disasm.txt"
PORT_BLD = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_bld.h"
RUNTIME_GATE = ROOT / "work/mission-state/w3-offline/W3_RUNTIME_GATE.env"


class AbiDiffError(ValueError):
    pass


@dataclass(frozen=True)
class StructDiff:
    item: str
    v62: int | str
    v89: int | str
    delta: int | str
    status: str
    evidence: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def elf_sections(data: bytes) -> dict[str, tuple[int, int, int, int]]:
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x01\x01":
        raise AbiDiffError("expected ELF32 little-endian")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    shoff, shentsize, shnum, shstrndx = header[5], header[10], header[11], header[12]
    if not shoff or shentsize != 40 or shstrndx >= shnum:
        raise AbiDiffError("invalid ELF32 section table")
    headers = [struct.unpack_from("<IIIIIIIIII", data, shoff + index * shentsize) for index in range(shnum)]
    shstr = headers[shstrndx]
    names = data[shstr[4] : shstr[4] + shstr[5]]
    result: dict[str, tuple[int, int, int, int]] = {}
    for section in headers:
        name_end = names.find(b"\0", section[0])
        name = names[section[0] : name_end].decode("ascii") if name_end >= 0 else ""
        result[name] = (section[4], section[5], section[6], section[9])
    return result


def section_bytes(data: bytes, name: str) -> bytes:
    offset, size, _, _ = elf_sections(data)[name]
    return data[offset : offset + size]


def c_string_at(path: Path, section: str, offset: int) -> str:
    payload = section_bytes(path.read_bytes(), section)
    if offset < 0 or offset >= len(payload):
        raise AbiDiffError(f"{path}: string offset 0x{offset:x} outside {section}")
    end = payload.find(b"\0", offset)
    if end < 0:
        raise AbiDiffError(f"{path}: unterminated string at {section}+0x{offset:x}")
    return payload[offset:end].decode("ascii")


def exports(path: Path) -> list[str]:
    payload = section_bytes(path.read_bytes(), "__ksymtab_strings")
    return sorted(value.decode("ascii") for value in payload.split(b"\0") if value)


def modinfo(path: Path) -> dict[str, list[str]]:
    payload = section_bytes(path.read_bytes(), ".modinfo")
    result: dict[str, list[str]] = {}
    for raw in payload.split(b"\0"):
        if not raw or b"=" not in raw:
            continue
        key, value = raw.decode("ascii").split("=", 1)
        result.setdefault(key, []).append(value)
    return result


def global_symbols(path: Path) -> tuple[list[str], list[str]]:
    data = path.read_bytes()
    sections = elf_sections(data)
    sym_off, sym_size, str_index, sym_entsize = sections[".symtab"]
    if sym_entsize != 16:
        raise AbiDiffError("unexpected ELF32 symbol size")
    # Section linkage is an index, so recover the linked string table by order.
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    shoff, shentsize = header[5], header[10]
    str_header = struct.unpack_from("<IIIIIIIIII", data, shoff + str_index * shentsize)
    strings = data[str_header[4] : str_header[4] + str_header[5]]
    defined: set[str] = set()
    undefined: set[str] = set()
    for offset in range(sym_off, sym_off + sym_size, sym_entsize):
        name_off, _, _, info, _, shndx = struct.unpack_from("<IIIBBH", data, offset)
        bind = info >> 4
        if bind not in (1, 2) or name_off >= len(strings):
            continue
        end = strings.find(b"\0", name_off)
        name = strings[name_off:end].decode("ascii") if end >= 0 else ""
        if not name:
            continue
        (undefined if shndx == 0 else defined).add(name)
    return sorted(defined), sorted(undefined)


def find_private_table(path: Path) -> list[dict[str, int | str]]:
    data = path.read_bytes()
    needle = b"setparam\0"
    cursor = 0
    start = None
    while True:
        position = data.find(needle, cursor)
        if position < 0:
            break
        candidate = position - 8
        if candidate >= 0 and struct.unpack_from("<IHH", data, candidate) == (0x8BE0, 0x4802, 0):
            start = candidate
            break
        cursor = position + 1
    if start is None:
        raise AbiDiffError(f"private ioctl table not found in {path}")
    records: list[dict[str, int | str]] = []
    for index in range(1024):
        offset = start + index * 24
        if offset + 24 > len(data):
            break
        cmd, set_args, get_args = struct.unpack_from("<IHH", data, offset)
        raw_name = data[offset + 8 : offset + 24]
        if b"\0" not in raw_name:
            break
        name_bytes = raw_name.split(b"\0", 1)[0]
        if any(byte < 0x20 or byte > 0x7E for byte in name_bytes):
            break
        if cmd > 0xFFFF or set_args > 0x7FFF or get_args > 0x7FFF:
            break
        records.append(
            {"cmd": cmd, "set_args": set_args, "get_args": get_args, "name": name_bytes.decode("ascii")}
        )
    return records


def require_markers(path: Path, markers: Sequence[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise AbiDiffError(f"{path}: missing disassembly markers {missing}")


def structure_matrix() -> list[StructDiff]:
    return [
        StructDiff("sizeof(shared_params)", 384, 400, 16, "PROVEN", "txbf allocation starts 0x180 vs 0x190"),
        StructDiff("shared_params.fw_no_mu", "absent", 76, "inserted 4B", "PROVEN", "OEM param-table offset 0x3a4 -> qcb load -> shared+0x4c -> 3/4 AuC SRAM banks"),
        StructDiff("shared_params.txbf_mbox_lhost", 76, 80, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.txbf_mbox_bus", 80, 84, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.muc_dsp_mbox_lhost", 84, 88, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.muc_dsp_mbox_bus", 88, 92, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.bb_mutex_lhost", 92, 96, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.vdev_lhost", 172, 176, 4, "PROVEN", "qdrv_soc_init stores"),
        StructDiff("shared_params.vlan_info", 184, 196, 12, "PROVEN", "qdrv_soc_init stores; added intervening fields"),
        StructDiff("shared_params.hardware_id", 228, 232, 4, "PROVEN", "qtn_get_hw_config_id store"),
        StructDiff("shared_params.fw_version", 240, 244, 4, "STRONG", "hardware/min/max sequence and memcpy base"),
        StructDiff("shared_params.auc", 276, 280, 4, "PROVEN", "auc_config store word 69 vs 70"),
        StructDiff("shared_params_auc.node_stats", 52, 52, 0, "PROVEN", "absolute shared offsets 328 vs 332 minus auc base"),
        StructDiff("shared_params_auc.vap_stats", 56, 56, 0, "PROVEN", "absolute shared offsets 332 vs 336 minus auc base"),
        StructDiff("sizeof(shared_params_auc)", 80, 80, 0, "PROVEN", "cca_adjusting_flag remains immediately after auc at byte 360"),
        StructDiff("sizeof(qtn_shared_node_stats_t)", 56, 56, 0, "PROVEN", "OEM ioremap 0x1c00 / 128 nodes"),
        StructDiff("sizeof(qtn_shared_vap_stats_t)", 44, 44, 0, "PROVEN", "OEM ioremap 704 / 16 VAPs"),
        StructDiff("sizeof(qtn_txbf_mbox)", 4512, 4528, 16, "PROVEN", "allocation offsets 0x180->0x1320 vs 0x190->0x1340"),
        StructDiff("qtn_txbf.ranking_algorithm_to_use", 4492, 4496, 4, "PROVEN", "DSP .89 initializes mbox+0x1190 to MU_ALGORITHM_AUTO"),
        StructDiff("qtn_txbf.precoding_algorithm_to_use", 4496, 4500, 4, "PROVEN", "DSP .89 initializes mbox+0x1194 to MU_ALGORITHM_PROJECTION"),
        StructDiff("qtn_txbf.rank_criteria_to_use", 4500, 4504, 4, "PROVEN", "DSP initializes 0x1198 to 0xf; OEM Lhost prints same offset as mu rank criteria"),
        StructDiff("qtn_txbf.mu_prec_cache_max_time", 4504, 4508, 4, "PROVEN", "DSP default 0x50 and MuC sounding-period update at 0x119c"),
        StructDiff("qtn_txbf.mu_rank_tolerance", 4508, 4512, 4, "PROVEN", "DSP default 5 and MuC rank-tolerance update at 0x11a0"),
        StructDiff("qtn_txbf.opaque_extension", "absent", 4516, "12B", "PROVEN BOUNDARY", "known controls end 0x11a4; mailbox ends 0x11b0"),
        StructDiff("qtn_txbf.dsp_stats.opaque_word", "absent", 0x1074, "4B", "PROVEN ZERO-INERT", "whole OEM allocation is zeroed before MuC/DSP start; no Lhost/MuC/RDSP access"),
        StructDiff("qtn_txbf.dsp_stats.dsp_sram_qmat_num", 0x1074, 0x1078, 4, "PROVEN", "OEM qdrv DSP stats print load"),
        StructDiff("qtn_txbf.dsp_stats.dsp_err_neg_qmat_num", 0x1078, 0x107C, 4, "PROVEN", "OEM qdrv DSP stats print load"),
        StructDiff("qtn_txbf.dsp_stats.dsp_flag", 0x107C, 0x1080, 4, "PROVEN", "OEM qdrv DSP stats print load"),
        StructDiff("sizeof(qtn_muc_dsp_mbox)", 2080, 2144, 64, "PROVEN", "allocation offsets 0x1320->0x1b40 vs 0x1340->0x1ba0"),
        StructDiff("qtn_muc_dsp_mbox.ring_count", 32, 32, 0, "PROVEN", "MuC wraps normal index after 31"),
        StructDiff("qtn_muc_dsp_mbox.special_slot", "absent", 0x820, "64B", "PROVEN", "MuC uses base+0x820 and publishes index 0xff; DSP consumes same branch"),
        StructDiff("sizeof(qtn_samp_chan_info)", 156, 160, 4, "PROVEN", "allocation member boundaries"),
        StructDiff("sizeof(qtn_scan_chan_info)", 168, 172, 4, "PROVEN", "allocation member boundaries"),
        StructDiff("qtn_scan.opaque_at_0x14", "absent", 20, "4B", "PROVEN BOUNDARY", "Lhost and MuC skip bytes 20..23; all following descriptors shift by four"),
        StructDiff("qtn_scan.start_txdesc_host", 20, 24, 4, "PROVEN", "OEM Lhost reads/stores byte 24"),
        StructDiff("qtn_scan.prbreq_txdesc_host", 32, 36, 4, "PROVEN", "OEM Lhost reads/stores byte 36"),
        StructDiff("qtn_scan.finish_txdesc_host", 44, 48, 4, "PROVEN", "OEM Lhost descriptor sequence"),
        StructDiff("qtn_scan.tsf", 56, 60, 4, "PROVEN", "OEM Lhost passes byte 60 to hal_get_tsf"),
        StructDiff("sizeof(qtn_scs_info_set)", 14420, 18800, 4380, "PROVEN", "allocation member boundaries"),
        StructDiff("qtn_scs.oc_info_count", 32, 32, 0, "PROVEN", "MuC OC loop uses stride 0x30 and stops after index 31"),
        StructDiff("sizeof(qtn_scs_oc_info)", 36, 48, 12, "PROVEN", "MuC adds cca_pri/sec/sec40 at 0x24/0x28/0x2c"),
        StructDiff("qtn_scs.history_count", 32, 43, 11, "PROVEN", "OEM WLAN compares index to 0x2a and uses 0x18-byte history stride"),
        StructDiff("sizeof(qtn_scs_info)", 1340, 1736, 396, "PROVEN", "OEM Lhost copies 0x6c8 with two-entry stride 0x1b2 words"),
        StructDiff("sizeof(qtn_scs_scan_info)", 40, 52, 12, "PROVEN", "OEM Lhost channel copy stride and length 0x34"),
        StructDiff("qtn_scs_scan_info.cca_pri", "absent", 24, "new u32", "PROVEN", "MuC producer and Lhost SCS field mapping"),
        StructDiff("qtn_scs_scan_info.cca_sec", "absent", 28, "new u32", "PROVEN", "MuC producer and Lhost SCS field mapping"),
        StructDiff("qtn_scs_scan_info.cca_sec40", "absent", 32, "new u32", "PROVEN", "MuC producer and Lhost SCS field mapping"),
        StructDiff("qtn_scs_scan_info.lpre_err", 32, 44, 12, "PROVEN", "OEM randomness/scaling path reads byte 0x2c"),
        StructDiff("qtn_scs_scan_info.spre_err", 36, 48, 12, "PROVEN", "OEM randomness/scaling path reads byte 0x30"),
        StructDiff("qtn_scs_info_set.scan_info", 2684, 3476, 792, "PROVEN", "OEM channel copy base +0xd94"),
        StructDiff("sizeof(qtn_scs_stats_history)", 1536, 2064, 528, "PROVEN LAYOUT", "container tail 0x4160..0x4970 = 0x810 = 2 x 43 x 24"),
        StructDiff("qtn_scs_info_set.stats_history", 12884, 16736, 3852, "PROVEN LAYOUT", "scan base 0xd94 + 255 x 0x34 = 0x4160"),
        StructDiff("sizeof(qtn_remain_chan_info)", 36, 40, 4, "PROVEN", "allocation member boundaries"),
        StructDiff("sizeof(qtn_ocac_info)", 72, 72, 0, "PROVEN", "allocation member boundaries"),
        StructDiff("sizeof(qtn_meas_chan_info)", 56, 56, 0, "PROVEN", "allocation member boundaries"),
        StructDiff("shared_params.free_airtime", 380, 384, 4, "PROVEN", "fw_no_mu insertion shifts existing tail"),
        StructDiff("shared_params.nac_mon_info_lhost", "absent", 388, "new pointer", "PROVEN", "OEM qdrv_soc_init and nac_mon_info debug string"),
        StructDiff("shared_params.nac_mon_info_bus", "absent", 392, "new pointer", "PROVEN", "OEM qdrv_soc_init and nac_mon_info debug string"),
        StructDiff("sizeof(qtn_nac_mon_entry_v89)", "absent", 20, "new", "PROVEN", "128-entry print loop stride and field accesses"),
        StructDiff("sizeof(qtn_nac_mon_info_v89)", "absent", 2596, "new", "PROVEN SIZE", "allocation 0x6d7c->0x77a0"),
        StructDiff("qtn_nac_mon_info.config_value0", "absent", 0, "new u16", "PROVEN OFFSET", "MuC writes default 100 and runtime-derived value"),
        StructDiff("qtn_nac_mon_info.config_value1", "absent", 2, "new u16", "PROVEN OFFSET", "MuC writes default 1000 and raw high16 configuration"),
        StructDiff("qtn_nac_mon_info.enabled", "absent", 4, "new u16", "PROVEN", "MuC writes zero on reset and one on enable"),
        StructDiff("qtn_nac_mon_info.entries", "absent", 8, "128 x 20B", "PROVEN", "OEM print starts shared pointer +8"),
        StructDiff("qtn_nac_mon_info.opaque_tail", "absent", 2568, "28B", "PROVEN BOUNDARY", "allocation ends at shared+0x77a0"),
        StructDiff("qtn_nac_mon_entry.valid", "absent", 0, "new u8", "PROVEN", "OEM print skips entries when byte zero"),
        StructDiff("qtn_nac_mon_entry.rssi_db", "absent", 1, "new s8", "PROVEN", "OEM sign-extends byte for Rssi(dB)"),
        StructDiff("qtn_nac_mon_entry.channel", "absent", 2, "new u8", "PROVEN", "OEM print Channel argument"),
        StructDiff("qtn_nac_mon_entry.packet_type", "absent", 3, "new u8", "PROVEN", "0 Control, 1 Data, other Management"),
        StructDiff("qtn_nac_mon_entry.timestamp", "absent", 4, "new u64", "PROVEN", "two adjacent words passed to %llu"),
        StructDiff("qtn_nac_mon_entry.mac_addr", "absent", 12, "6B", "PROVEN", "ether_sprintf receives entry+12"),
        StructDiff("sizeof(qtn_bmps_info)", 28, 16, -12, "PROVEN", "allocation member boundaries"),
        StructDiff("qtn_samp.freq_band", 28, 0, -28, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_samp.samp_channel", 32, 4, -28, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_samp.duration_msecs", 36, 8, -28, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_samp.status", 48, 12, -36, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_samp.control_flags", "absent", 16, "new u16", "PROVEN", "Lhost stores 0x10; MuC tests bits 0, 4 and 5 as a u16"),
        StructDiff("qtn_samp.start_tsf", 40, 20, -20, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_samp.result", 0, 28, 28, "PROVEN", "MuC writes unchanged 28-byte out_cca_info at offsets 28..55"),
        StructDiff("qtn_samp.type", 52, 56, 4, "PROVEN", "paired async CCA stores"),
        StructDiff("qtn_remain.flags", "absent", 12, "new u32", "PROVEN", "OEM Lhost stores the remain-on-channel flags argument at byte 12"),
        StructDiff("qtn_remain.start_tsf", 16, 16, 0, "PROVEN", "Lhost stores and MuC reads the 64-bit start TSF at bytes 16..23"),
        StructDiff("qtn_remain.duration_usecs", 12, 24, 12, "PROVEN", "Lhost store and MuC scheduler divide-by-1000 read at byte 24"),
        StructDiff("qtn_remain.status", 24, 28, 4, "PROVEN", "Lhost HOST_IOCTL_SENT store and MuC state transitions at byte 28"),
        StructDiff("qtn_remain.peer_mac", 28, 32, 4, "PROVEN", "OEM Lhost six-byte memcpy destination byte 32"),
        StructDiff("sizeof(_shared_params_alloc)", 23552, 30624, 7072, "PROVEN", "dma allocation 0x5c00 vs 0x77a0"),
        StructDiff("sizeof(host_ioctl)", 32, 32, 0, "PROVEN", "OEM ioctl pool stride and memset"),
        StructDiff("sizeof(qtn_vap_args)", 24, 24, 0, "PROVEN", "both .62.1 source and .89 disassembly allocate 25 transport bytes but initialize/send a 24-byte payload"),
        StructDiff("sizeof(qtn_node_args)", 312, 312, 0, "PROVEN", "OEM coherent allocation immediate 312"),
    ]


def build_report() -> dict[str, object]:
    require_markers(OEM_SOC_DISASM, ("mov_s\tr1,0x77a0", "add3\tr3,r13,0x32", "st\tr0,[r13,232]"))
    require_markers(OEM_AUC_DISASM, ("st.as\tr3,[r2,70]", "ld_s\tr2,[r2,0x4c]", "mov_s\tr1,0x40000"))
    require_markers(OEM_STATS_DISASM, ("ld.as\tr0,[r13,83]", "ld.as\tr2,[r13,84]", "mov_s\tr1,0x1c00"))
    require_markers(OEM_CCA_DISASM, ("st\tr5,[r13,20]", "sth\tr2,[r13,16]", "st\tr3,[r13,56]"))
    require_markers(OEM_MUC_DECOMP, (
        "*(ushort *)(param_2 + 0x10) & 0x10",
        "*(undefined4 *)(param_2 + 0x24)",
        "*(undefined4 *)(param_2 + 0x34)",
        "*(undefined4 *)(param_2 + 0x80)",
    ))
    require_markers(OEM_QDRV_FULL_DISASM, (
        "st\tr20,[r17,12]",
        "st\tr19,[r17,24]",
        "add\tr0,r17,0x20",
        "st\tr3,[r17,28]",
        "mov_s\tr1,0x19",
        "mov_s\tr2,0x18",
        "stb_s\tr2,[r13,0x11]",
        "add\tr0,r13,0x12",
        "ld.as\tr3,[r2,97]",
        "add\tr13,r3,0x8",
        "add\tr13,r13,0x14",
        "brne\tr14,0x80",
        "add\tr2,r21,0x1070",
        "add\tr2,r21,0x1078",
        "add\tr2,r21,0x107c",
        "add\tr2,r21,0x1080",
    ))
    require_markers(OEM_MUC_DECOMP, (
        "*(uint *)(param_2 + 0x10)",
        "*(uint *)(param_2 + 0x14)",
        "*(uint *)(param_2 + 0x18) / 1000",
        "*(undefined4 *)(param_2 + 0x1c) = 2",
        "puVar6 = *(undefined2 **)(uVar4 + 0x188)",
        "puVar6[2] = 0",
        "*puVar6 = 100",
        "puVar3[2] = 1",
        "*(uint *)(iVar15 + 0x119c) = (uint)((int)pcVar16 * 9) / 10",
        "*(undefined4 *)(iVar15 + 0x11a0) = uVar19",
        "piVar4 = piVar5 + DAT_ram_0018c0cc * 0x10 + 8;",
        "if (0x1f < DAT_ram_0018c0cc + 1)",
        "piVar1[0x208] = 0xb;",
        "piVar1[0x213] = 0xff;",
        "FUN_ram_000ed004(piVar1 + 0x208,0x40);",
    ))
    require_markers(OEM_DSP_DECOMP, (
        "+ 0x1194) = 1",
        "+ 0x1190) = 0",
        "+ 0x1198) = 0xf",
        "+ 0x119c) = 0x50",
        "+ 0x11a0) = 5",
        "+ 0x119c);",
        "+ 0x11a0);",
        "if (param_2 == 0xff)",
        "param_1 + 0x820",
        "param_1 + 0x20 + param_2 * 0x40",
    ))
    require_markers(OEM_WLAN_DECOMP, (
        "memcpy(param_3,(void *)(iVar3 + param_2 * 0x34 + 0xd94),0x34);",
        "*(undefined4 *)((int)param_3 + 0x14) = 0;",
        "*(undefined4 *)((int)param_3 + 0x2c)",
        "*(undefined4 *)((int)param_3 + 0x30)",
        "* 0x1b2 + 1,0x6c8);",
        "puVar31[0x18b]",
        "puVar31[0x18c]",
    ))

    oem_exports = exports(OEM_QDRV)
    port_exports = exports(PORT_QDRV)
    oem_defined, oem_undefined = global_symbols(OEM_QDRV)
    port_defined, port_undefined = global_symbols(PORT_QDRV)
    oem_ioctl = find_private_table(OEM_WLAN)
    port_ioctl = find_private_table(PORT_WLAN)
    oem_ioctl_tuples = {(row["cmd"], row["set_args"], row["get_args"], row["name"]) for row in oem_ioctl}
    port_ioctl_tuples = {(row["cmd"], row["set_args"], row["get_args"], row["name"]) for row in port_ioctl}
    oem_info = modinfo(OEM_QDRV)
    port_info = modinfo(PORT_QDRV)
    build_header = PORT_BLD.read_text(encoding="utf-8")
    host_name = re.search(r'QDRV_BLD_NAME\s+"([^"]+)"', build_header)
    host_ver = re.search(r"QDRV_BLD_VER\s+\(0x([0-9a-fA-F]+)\)", build_header)
    gate_values = dict(
        line.split("=", 1)
        for line in RUNTIME_GATE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    nac_strings = {
        "heading": c_string_at(OEM_QDRV, ".rodata.str1.4", 0xBDE4),
        "control": c_string_at(OEM_QDRV, ".rodata.str1.4", 0xBE24),
        "data": c_string_at(OEM_QDRV, ".rodata.str1.4", 0xBE2C),
        "management": c_string_at(OEM_QDRV, ".rodata.str1.4", 0xBE34),
        "format": c_string_at(OEM_QDRV, ".rodata.str1.4", 0xBE40),
    }
    return {
        "gate": "QDRV_ABI_62_TO_89",
        "artifacts": {
            "oem_qdrv": {"path": str(OEM_QDRV), "sha256": sha256(OEM_QDRV)},
            "port_qdrv": {"path": str(PORT_QDRV), "sha256": sha256(PORT_QDRV)},
        },
        "versions": {
            "port_name": host_name.group(1) if host_name else None,
            "port_encoded": int(host_ver.group(1), 16) if host_ver else None,
            "oem_encoded": 0x25040059,
            "fwinfo_status": "MISMATCH_STOP",
        },
        "structures": [asdict(row) for row in structure_matrix()],
        "module_parameters": {
            "oem": sorted(oem_info.get("parmtype", [])),
            "port": sorted(port_info.get("parmtype", [])),
            "equal": sorted(oem_info.get("parmtype", [])) == sorted(port_info.get("parmtype", [])),
        },
        "exports": {
            "oem_count": len(oem_exports),
            "port_count": len(port_exports),
            "oem_only": sorted(set(oem_exports) - set(port_exports)),
            "port_only": sorted(set(port_exports) - set(oem_exports)),
            "common": sorted(set(oem_exports) & set(port_exports)),
        },
        "global_symbols": {
            "oem_defined_count": len(oem_defined),
            "port_defined_count": len(port_defined),
            "oem_undefined_count": len(oem_undefined),
            "port_undefined_count": len(port_undefined),
            "oem_only_undefined": sorted(set(oem_undefined) - set(port_undefined)),
            "port_only_undefined": sorted(set(port_undefined) - set(oem_undefined)),
        },
        "private_ioctls": {
            "oem_count": len(oem_ioctl),
            "port_count": len(port_ioctl),
            "oem_only": [dict(cmd=a, set_args=b, get_args=c, name=d) for a, b, c, d in sorted(oem_ioctl_tuples - port_ioctl_tuples)],
            "port_only": [dict(cmd=a, set_args=b, get_args=c, name=d) for a, b, c, d in sorted(port_ioctl_tuples - oem_ioctl_tuples)],
            "common_count": len(oem_ioctl_tuples & port_ioctl_tuples),
        },
        "nac_contract": {
            "classification": "PROVEN_LAYOUT_OPAQUE_TAIL",
            "shared_lhost_offset": 388,
            "shared_bus_offset": 392,
            "allocation_offset": 0x6D7C,
            "allocation_size": 2596,
            "header_size": 8,
            "entry_count": 128,
            "entry_size": 20,
            "entries_offset": 8,
            "opaque_tail_offset": 2568,
            "opaque_tail_size": 28,
            "packet_type_values": {"0": "Control", "1": "Data", "other": "Management"},
            "oem_strings": nac_strings,
            "runtime_publisher": "-EOPNOTSUPP",
        },
        "txbf_algo_tail_contract": {
            "classification": "PROVEN_SUBBLOCK_OPAQUE_EXTENSION",
            "mailbox_size": 0x11B0,
            "tail_offset": 0x1190,
            "tail_size": 32,
            "ranking_algorithm_offset": 0x1190,
            "precoding_algorithm_offset": 0x1194,
            "rank_criteria_offset": 0x1198,
            "prec_cache_max_time_offset": 0x119C,
            "rank_tolerance_offset": 0x11A0,
            "opaque_extension_offset": 0x11A4,
            "opaque_extension_size": 12,
            "rank_criteria_label": c_string_at(OEM_QDRV, ".rodata.str1.4", 0x1D04),
            "runtime_publisher": "-EOPNOTSUPP",
            "full_mailbox_closed": False,
        },
        "txbf_dsp_stats_contract": {
            "classification": "PROVEN_ZERO_INITIALIZED_OPAQUE_BYTES",
            "qmat_invalid_offset": 0x1070,
            "opaque_word_offset": 0x1074,
            "sram_qmat_num_offset": 0x1078,
            "full_stats_closed": False,
        },
        "txbf_full_contract": {
            "classification": "PROVEN_COMPLETE_WIRE_LAYOUT_ZERO_INERT_OPAQUE_BYTES",
            "mailbox_size": 0x11B0,
            "legacy_head_size": 0x1070,
            "opaque_qmat_offset": 0x1074,
            "opaque_qmat_size": 4,
            "algorithm_tail_offset": 0x1190,
            "opaque_tail_offset": 0x11A4,
            "opaque_tail_size": 12,
            "host_allocation_zeroed_before_uc_start": True,
            "maximum_observed_lhost_muc_rdsp_offset": 0x11A0,
            "opaque_bytes_have_producer": False,
            "opaque_bytes_have_consumer": False,
            "layout_approved": True,
            "runtime_publisher_integrated": True,
            "w3_pair_decision": "PAIR_SIGNED_HARDWARE_ACTIVE_NO_GO",
        },
        "muc_dsp_mbox_contract": {
            "classification": "PROVEN_RING32_PLUS_SPECIAL_SLOT",
            "mailbox_size": 0x860,
            "header_size": 0x20,
            "entry_size": 0x40,
            "ring_count": 32,
            "ring_offset": 0x20,
            "special_slot_offset": 0x820,
            "special_index": 0xFF,
            "runtime_publisher": "-EOPNOTSUPP",
        },
        "scs_info_set_contract": {
            "classification": "PROVEN_COMPLETE_LAYOUT",
            "container_size": 0x4970,
            "oc_info_count": 32,
            "oc_info_size": 48,
            "scs_info_size": 0x6C8,
            "scs_info_count": 2,
            "scan_info_offset": 0xD94,
            "scan_info_count": 255,
            "scan_info_size": 0x34,
            "scan_cca_pri_offset": 0x18,
            "scan_cca_sec_offset": 0x1C,
            "scan_cca_sec40_offset": 0x20,
            "stats_history_offset": 0x4160,
            "stats_history_size": 0x810,
            "history_count": 43,
            "runtime_publisher": "-EOPNOTSUPP",
        },
        "scan_chan_contract": {
            "classification": "PROVEN_LAYOUT_OPAQUE_EXTENSION",
            "size": 172,
            "opaque_offset": 20,
            "opaque_size": 4,
            "start_txdesc_host_offset": 24,
            "prbreq_txdesc_host_offset": 36,
            "finish_txdesc_host_offset": 48,
            "tsf_offset": 60,
            "runtime_publisher": "-EOPNOTSUPP",
        },
        "shared_publisher_contract": {
            "classification": "COMPILE_CLOSED_STAGED_NOT_PRODUCTION_ROUTED",
            "allocation_size": 0x77A0,
            "shared_size": 400,
            "txbf_offset": 0x190,
            "muc_dsp_offset": 0x1340,
            "scs_offset": 0x1D24,
            "nac_offset": 0x6D7C,
            "default_host_version": 0x2504003E,
            "gated_host_version": 0x25040059,
            "explicit_gate_magic": 0x56383947,
            "production_qdrv_soc_init_integrated": True,
            "w3_pair_approved": True,
        },
        "compatible_changes": [
            "FWINFO two-pass fail-closed pre-scan",
            "additive qdrv_async_cca_read export alias while preserving qtn_async_cca_read",
            "additive fw_no_mu qdrv control-plane input retained host-local until v89 shared layout is complete",
            "retain port-only maccmd private ioctl because all 134 OEM entries remain byte-identical",
            "versioned compile-only qtn_samp_chan_info_v89 contract; runtime publisher returns -EOPNOTSUPP",
            "versioned compile-only qtn_remain_chan_info_v89 contract; runtime publisher returns -EOPNOTSUPP",
            "qtn_vap_args remains 24 bytes; the 25th coherent byte is transport slack, not a shared field",
            "versioned compile-only qtn_nac_mon_info_v89 contract; 28-byte tail remains opaque and runtime publisher returns -EOPNOTSUPP",
            "versioned compile-only qtn_txbf algorithm-control tail; 12-byte extension remains opaque and runtime publisher returns -EOPNOTSUPP",
            "versioned compile-only qtn_muc_dsp_mbox v89 contract; preserves ring[32] and appends the index-0xff special slot; runtime publisher returns -EOPNOTSUPP",
            "versioned compile-only qtn_scs_info_set v89 contract; 32 widened OC records, 255 scan records and 43-entry history arrays; runtime publisher returns -EOPNOTSUPP",
            "versioned compile-only qtn_scan_chan_info v89 layout; byte range 20..23 remains explicitly opaque and runtime publisher returns -EOPNOTSUPP",
            "complete qtn_txbf_mbox v89 wire contract; inserted 4 bytes and appended 12 bytes are zero-initialized and unconsumed by the exact OEM binaries",
        ],
        "blocked_changes": [
            "Do not advertise QDRV_BLD_VER 0x25040059 yet",
            "Do not mutate production shared_params with unnamed padding",
            "Publish fw_no_mu at shared+0x4c only after the complete v89 layout is implemented",
            "Do not approve W3_PAIR until qdrv_soc_init allocates/publishes the complete v89 shared container and all host modules consume the v89 layouts",
            "Do not advertise QDRV_BLD_VER 0x25040059 while the production shared publisher remains the .62.1 struct _shared_params_alloc",
        ],
        "runtime_gate": gate_values,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report()
    except (OSError, KeyError, struct.error, AbiDiffError) as exc:
        print(f"ERROR: {exc}")
        return 2
    rendered = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    if args.json:
        print(rendered, end="")
    else:
        print("QDRV_ABI_DIFF")
        print(f"STRUCT_DIFFS={sum(row['v62'] != row['v89'] for row in report['structures'])}")
        print(f"EXPORT_OEM_ONLY={report['exports']['oem_only']}")
        print(f"IOCTL_OEM_ONLY={report['private_ioctls']['oem_only']}")
        print(f"RUNTIME_APPROVED={report['runtime_gate'].get('W3_PAIR_APPROVED')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
