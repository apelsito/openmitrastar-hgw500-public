"""Bind reviewed Bootbase erase/write branches to the preserved actual image.

This is a static, file-only audit. It does not execute a bootloader or access a
device. Its scope is the exact dispatcher branches and helpers listed below.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import lzma
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x88014000
EXPECTED = '20ab45412b973478aa49a3daa31851a49f0deeaa09d07213479b0c3ee7af5f07'
RANGES = {
    'erase': (0x88022734, 0x88022880),
    'write': (0x88022a1c, 0x88022b2c),
    'dispatch_prologue': (0x88022fdc, 0x88023052),
    'separate_unlock_hw_branch': (0x880235dc, 0x88023640),
    'bitmap_lock_unlock': (0x88022548, 0x88022650),
    'bounds_ready': (0x88022650, 0x88022698),
    'status_and_id': (0x88022430, 0x880224e8),
    'cache_and_wait': (0x880226cc, 0x88022734),
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    binary = ROOT/'work/bootbase-decoded.bin'
    disasm = ROOT/'work/bootbase-decoded.disasm.txt'
    backup = ROOT/'outputs/flash-backups/f159-physical-new-dump-20260831T2359/current-unit/hgw500_mtdblock0.bin'
    writer = ROOT/'tools/f321_mtd4_bootbase_flash.ps1'
    data = binary.read_bytes()
    lines = disasm.read_text(encoding='utf-8').splitlines()
    slices = {}
    for name, (start, end) in RANGES.items():
        selected = []
        for line in lines:
            m = re.match(r'([0-9a-fA-F]{8}):', line)
            if m and start <= int(m[1], 16) < end:
                selected.append(line)
        slices[name] = '\n'.join(selected)+'\n'
    def string(address):
        offset = address-BASE
        return data[offset:data.index(b'\0', offset)].decode('ascii')
    checks = {
        'actual_binary_sha': sha(binary) == EXPECTED,
        'decoded_from_protected_backup': lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(backup.read_bytes()[0xf34:]) == data,
        'disassembly_base': '88014000 <.data>:' in lines,
        'hardware_unlock_selector': string(0x88033dec) == 'unlock_hw',
        'software_unlock_selector': string(0x88033dc8) == 'unlock',
        'hardware_unlock_guard': 'brne.d\tr0,0,88\t;0x88023640' in slices['separate_unlock_hw_branch'],
        'separate_hardware_unlock_opcode': '0xe2009800' in slices['separate_unlock_hw_branch'],
        'nonzero_erase_start_excludes_bulk_path': 'brne\tr14,0,136\t;0x88022850' in slices['erase'],
        'sector_erase_path': '0xe200d800' in slices['erase'],
        'page_program_path': '0xe2000200' in slices['write'],
        'write_enable_in_both_routes': all('0xe2000600' in slices[k] for k in ('erase', 'write')),
        'commit_register_in_write': '0xe2000000' in slices['write'],
        'selected_io_routes_no_protection_literals': not re.search(r'0xe200(?:6800|2f00|9800|7e00|e100|e300|e400)', slices['erase']+slices['write']),
        'dispatcher_prologue_has_no_spi_aperture_literal': 'e200' not in slices['dispatch_prologue'],
        'reference_writer_no_hardware_unlock_command': 'unlock_hw' not in writer.read_text(encoding='utf-8'),
    }
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/preflight'/('f346-bootbase-paths-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    for name, text in slices.items():
        (out/(name+'.disasm.txt')).write_text(text, encoding='utf-8')
    result = {
        'schema': 'openmitrastar.f346-reviewed-bootbase-paths/v1',
        'status': 'PASS_STATIC_BOUND_REVIEW' if all(checks.values()) else 'FAIL_STATIC_BINDING',
        'hardware_actions': False, 'checks': checks,
        'binary_runtime_base': hex(BASE),
        'normal_write_scope': {'offset': '0x007e0000', 'erase_bytes': '0x005e0000', 'writer_source': str(writer)},
        'reviewed_findings': [
            'Erase/write use write-enable and bounded sector/page operations with ready polling, ID/CS completion, cache handling and the software lock bitmap.',
            'The chip-erase branch requires a zero start; the reviewed nonzero live-slot operation branches directly to the sector loop.',
            'The hardware gang-unlock implementation belongs to a separate dispatcher branch selected by unlock_hw, not ordinary write/erase.',
            'The common dispatcher prologue initializes a RAM bitmap; it is not hardware block protection.',
        ],
        'limits': [
            'This is reviewed static branch evidence plus exact binary binding, not a claim about every Bootbase command or board-startup path.',
            'Literal checks support the recorded review; absence of a literal alone is not a complete general MMIO proof.',
            'A future caller must allow only the exact reviewed read/erase/write strings and addresses; unrelated five-argument dispatcher input must not be accepted.',
            'Fresh device/UART binding, backups, watchdog inactivity, protected CRCs and full readback remain required for an actual installation.',
        ],
        'sources': {str(p): sha(p) for p in (binary, disasm, backup, writer, Path(__file__))},
        'slices': {p.name: sha(p) for p in out.glob('*.disasm.txt')},
    }
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'result': str(out/'result.json'), 'status': result['status'], 'checks': checks}, indent=2))
    return int(not all(checks.values()))


if __name__ == '__main__':
    raise SystemExit(main())
