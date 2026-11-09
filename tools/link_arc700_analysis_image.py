"""Resolve internal module relocations for REA without changing OEM/module bytes.

Creates an ANALYSIS_ONLY ET_EXEC with synthetic external symbol addresses.
Never load, boot, package or flash this derived file. External addresses are
not runtime addresses; they preserve names while internal calls become usable.
"""
import argparse
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

TOOLCHAIN = Path('/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin')
PREFIX = TOOLCHAIN / 'arc-snps-linux-uclibc-'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--entry', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source_sha = sha(args.input)
    undefined = subprocess.check_output([str(PREFIX) + 'nm', '-u', str(args.input)], text=True)
    symbols = sorted(set(line.split()[-1] for line in undefined.splitlines() if line.strip()))
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in symbols):
        raise ValueError('unexpected undefined-symbol spelling')
    external = {name: 0x0f000000 + i * 16 for i, name in enumerate(symbols)}
    target = args.output / (args.input.stem + '-ANALYSIS_ONLY-NOT_FIRMWARE.elf')
    # Lay out every allocated section explicitly; the default ARC userland
    # script overlaps the module's Linux note when -Ttext is supplied alone.
    data = args.input.read_bytes()
    shoff = struct.unpack_from('<I', data, 32)[0]
    shsize, shnum, stridx = struct.unpack_from('<HHH', data, 46)
    sections = [struct.unpack_from('<10I', data, shoff + i * shsize) for i in range(shnum)]
    strings_section = sections[stridx]
    strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
    names = []
    for row in sections:
        if row[2] & 2:
            start = row[0]
            name = strings[start:strings.index(0, start)].decode('ascii')
            if not re.fullmatch(r'[.A-Za-z0-9_-]+', name):
                raise ValueError('unsupported section name ' + name)
            names.append(name)
    script = args.output / 'analysis.ld'
    script.write_text('SECTIONS {\n . = 0x10000;\n' + ''.join(
        ' . = ALIGN(16); ' + name + ' : { *(' + name + ') }\n' for name in names) + '}\n')
    listing = subprocess.check_output([str(PREFIX) + 'nm', str(args.input)], text=True)
    entry_rows = [line.split() for line in listing.splitlines()
                  if line.split()[-1] == args.entry]
    if len(entry_rows) != 1 or len(entry_rows[0]) != 3:
        raise ValueError('entry symbol not uniquely defined')
    # Local static symbols cannot serve as ld's symbolic ELF entry.
    entry_address = 0x10000 + int(entry_rows[0][0], 16)
    command = [str(PREFIX) + 'ld', '-T', str(script), '-e', hex(entry_address),
               '--build-id=none', '-o', str(target)]
    command.extend('--defsym=' + name + '=' + hex(address) for name, address in external.items())
    command.append(str(args.input))
    proc = subprocess.run(command, capture_output=True)
    (args.output / 'link.stdout').write_bytes(proc.stdout)
    (args.output / 'link.stderr').write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError('analysis link failed; inspect ' + str(args.output))
    for command_name, file in [('readelf', 'layout.txt'), ('nm', 'symbols.txt')]:
        flags = ['-h', '-S', '-r'] if command_name == 'readelf' else ['-n']
        result = subprocess.check_output([str(PREFIX) + command_name, *flags, str(target)])
        (args.output / file).write_bytes(result)
    manifest = {'schema': 'openmitrastar.arc700-analysis-image/v1',
                'classification': 'ANALYSIS_ONLY_NEVER_LOAD_OR_FLASH',
                'source': {'path': str(args.input), 'sha256': source_sha},
                'derived': {'path': str(target), 'sha256': sha(target), 'bytes': target.stat().st_size},
                'source_unchanged': sha(args.input) == source_sha,
                'synthetic_external_symbols': {name: hex(addr) for name, addr in external.items()},
                'linker': {'path': str(PREFIX) + 'ld', 'sha256': sha(str(PREFIX) + 'ld')},
                'text_address': '0x10000', 'entry': args.entry,
                'limitations': ['External symbols have synthetic addresses, never measured runtime values.',
                                'Linking changes relocation bytes in this derived artifact only.',
                                'Static decoding must be verified against the pinned ARC toolchain.',
                                'No load, firmware, RF, client, traffic or recovery acceptance.'],
                'hardware_accessed': False}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('classification', 'derived', 'source_unchanged')}))

if __name__ == '__main__':
    main()
