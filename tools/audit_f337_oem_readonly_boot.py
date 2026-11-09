"""Offline OEM boot/rootfs analysis. Never opens a device or starts a server."""
from pathlib import Path
import argparse
import hashlib
import json
import lzma
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'outputs/flash-backups/f159-physical-new-dump-20260831T2359/current-unit'
ORIGINAL = ROOT / 'hgw500bna-qcv2-firmware-dump-verified'
OEM = ROOT / 'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'
BOOTARGS = ('console=ttyS0,115200n8 earlyprintk=1 hw_config_id=65535 '
            'root=31:0 rootfstype=squashfs ro init=/bin/sh ip=off '
            'mtdparts=spi_flash:0x670000@0x170000(oemroot)ro')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def elf_sections(data):
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    sections = [struct.unpack_from('<IIIIIIIIII', data, h[6]+i*h[11]) for i in range(h[12])]
    strings = sections[h[13]]
    names = data[strings[4]:strings[4]+strings[5]]
    return {names[s[0]:].split(b'\0', 1)[0].decode(): s for s in sections}


def observe_slot(data):
    # OEM add_mtd_partitions reads the big-endian word at header + 0x68.
    # find_rootfs_header scans erase-block boundaries for the SquashFS magic.
    offsets = [i for i in range(0, len(data), 0x10000) if data[i:i+4] == b'hsqs']
    return {'bytes': len(data), 'sha256': sha(data),
            'header_priority_be32_at_0x68': struct.unpack_from('>I', data, 0x68)[0],
            'aligned_squashfs_offsets': offsets}


def model_oem_choice(safety, live):
    """Documented reconstruction, not an execution of the ARC classifier."""
    # add_mtd_partitions 84a8531c..84a85382: choose the header priority first;
    # a chosen slot without a found SquashFS does not fall back to the other.
    s, l = (safety['header_priority_be32_at_0x68'], live['header_priority_be32_at_0x68'])
    if s == 0xffffffff and l == 0xffffffff:
        return None
    signed = lambda n: n if n < 0x80000000 else n-0x100000000
    chosen = live if s == 0xffffffff or (l != 0xffffffff and signed(l) >= signed(s)) else safety
    return ('live' if chosen is live else 'safety') if chosen['aligned_squashfs_offsets'] else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite previous evidence')
    current = (BACKUP/'hgw500_mtdblock3.bin').read_bytes()
    original = (ORIGINAL/'hgw500_mtdblock3.bin').read_bytes()
    official = OEM.read_bytes()
    live = (BACKUP/'hgw500_mtdblock4.bin').read_bytes()
    boot = (BACKUP/'hgw500_mtdblock0.bin').read_bytes()
    decoded = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(current[0x2000:])
    decoded_boot = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(boot[0xf34:])
    elf_path = ROOT/'work/mission-state/w3-offline/oem-b24-vmlinux.elf'
    elf = elf_path.read_bytes()
    ks = elf_sections(elf)['.kernel']
    differences = [i for i, (x, y) in enumerate(zip(current, original)) if x != y]
    header = bytearray(current[:64]); header[4:8] = b'\0'*4
    log_path = ROOT/'outputs/uart-live/boot-safety-after-recovery-20260817.log'
    log = log_path.read_text(errors='replace')
    actual_cmdline = next(line.split('Kernel command line: ', 1)[1]
                          for line in log.splitlines() if 'Kernel command line: ' in line)
    config_path = ROOT/'outputs/kernel-port/live-kernel-2.6.35.12.config'
    config = config_path.read_text()
    safety_info, live_info = observe_slot(current), observe_slot(live)
    checks = {
        'current_safety_pinned': sha(current) == 'f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1',
        'official_b24_pinned': sha(official) == 'f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f',
        'original_safety_is_official_plus_ff': original == official+b'\xff'*(0x7a0000-len(official)),
        'only_header_priority_byte_changed': differences == [0x6b] and current[0x6b] == 1 and original[0x6b] == 5,
        'all_oem_payload_bytes_preserved': current[0x2000:] == original[0x2000:],
        'uimage_header_crc_valid': zlib.crc32(header) == struct.unpack_from('>I', current, 4)[0],
        'ras_payload_crc_valid': zlib.crc32(current[0x2000:len(official)]) == struct.unpack_from('>I', current, 24)[0],
        'decoded_kernel_matches_audited_elf': decoded == elf[ks[4]:ks[4]+ks[5]],
        'decoded_kernel_matches_saved_binary': decoded == (ROOT/'work/mission-state/w3-offline/oem-b24-kernel-uncompressed.bin').read_bytes(),
        'current_bootbase_executable_matches_audited': decoded_boot == (ROOT/'work/bootbase-decoded.bin').read_bytes(),
        'logical_mtd6_is_safety_tail': (ORIGINAL/'hgw500_mtdblock6.bin').read_bytes() == original[0x130000:],
        'exact_squashfs_offset': safety_info['aligned_squashfs_offsets'] == [0x130000],
        'squashfs_inside_safety': 0x40000+0x130000 == 0x170000 and 0x170000+0x670000 == 0x7e0000,
        'historical_cmdline_no_root': not any(x.startswith('root=') for x in actual_cmdline.split()),
        'historical_root_hda2_failure': 'Cannot open root device "(null)" or unknown-block(3,2)' in log,
        'historical_no_logical_root_partition': '1f06' not in log,
        'backup_exercises_oem_no_fallback_case': safety_info['header_priority_be32_at_0x68'] == 1 and live_info['header_priority_be32_at_0x68'] == 5 and not live_info['aligned_squashfs_offsets'] and model_oem_choice(safety_info, live_info) is None,
        'new_cmdline_fits_arc_256': len(BOOTARGS.encode())+1 <= 256,
        'new_cmdline_exact_single_ro_view': BOOTARGS.count('mtdparts=') == 1 and BOOTARGS.endswith('0x670000@0x170000(oemroot)ro'),
        'new_view_avoids_oem_autoselection_names': not any(x in BOOTARGS for x in ['(linux_safety)', '(linux_live)', '(uboot)', '(data)']),
        'config_has_cmdline_parts_squashfs_lzma': all(x in config for x in ['CONFIG_MTD_CMDLINE_PARTS=y', 'CONFIG_SQUASHFS=y', 'CONFIG_SQUASHFS_LZMA=y']),
        'config_has_no_early_initramfs_or_ip_autoconfig': all(x in config for x in ['# CONFIG_BLK_DEV_INITRD is not set', '# CONFIG_IP_PNP is not set', '# CONFIG_DEVTMPFS is not set']),
        'generic_ramdisk_fallback_not_supported': '# CONFIG_MTD_RAM is not set' in config and 'CONFIG_BLK_DEV_RAM_SIZE=2048' in config,
    }
    result = {
        'schema': 'openmitrastar.f337-oem-readonly-plan/v1',
        'status': 'PASS_OFFLINE_ANALYSIS_ONLY' if all(checks.values()) else 'FAIL_OFFLINE_CHECK',
        'hardware_actions': [], 'hardware_boot_pass': False, 'recovery_acceptance': False,
        'checks': checks,
        'current_safety_backup': safety_info,
        'historical_f159_live_backup': live_info,
        'root_selection_model_scope': 'Reconstructed from exact OEM disassembly; F159 backup reproduces failure condition. Exact mtd4 bytes at the August 17 panic were not established.',
        'image_difference': {'offset': '0x6b', 'original': 5, 'current': 1, 'interpretation': 'Low byte of big-endian priority field at 0x68; not a kernel/rootfs corruption'},
        'provenance': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in [elf_path, config_path, log_path, OEM]},
        'decompressed_kernel_sha256': sha(decoded), 'decompressed_bootbase_sha256': sha(decoded_boot),
        'proposed_bootargs': BOOTARGS, 'bootargs_bytes_with_nul': len(BOOTARGS)+1,
        'proposed_bootbase_commands_for_review_only': [
            'spi_flash read 0x00040000 0x83000000 0x007a0000',
            'iminfo 0x83000000',
            'setenv bootargs '+BOOTARGS,
            'bootm 0x83000000'],
        'physical_meaning': 'Only a volatile read-only MTD view at physical SPI 0x170000..0x7e0000. Linux mtd0 in this proposed boot is NOT physical baseline mtd0/uboot.',
        'remaining_gates': ['fresh exact F321/Bootbase/protected hashes and lease', 'continuous UART and independent bounded recovery', 'PID1 shell and actual mounts/MTD flags', 'no OEM init services or networking', 'return exact F321 and protected-partition equality'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'checks_pass': sum(checks.values()), 'checks_total': len(checks), 'output': str(args.output)}))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
