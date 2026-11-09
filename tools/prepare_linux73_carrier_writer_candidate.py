"""Bind exact recovered firmware identities to a serialized SRAM writer lease.

Creates a new source candidate. No firmware bytes are copied or installed.
Kernel occupancy, runtime writers and hardware reservation remain separate gates.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--writer-source', type=Path, required=True)
    parser.add_argument('--carrier-contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    parent = json.loads((args.parent / 'result.json').read_text())
    for rel, digest in parent['files'].items():
        assert sha(args.parent / rel.replace('\\', '/')) == digest
    provider = json.loads((args.writer_source / 'result.json').read_text())
    contract = json.loads(args.carrier_contract.read_text())
    assert len(contract['profiles']) == 3
    shutil.copytree(args.parent, args.output)
    for rel, digest in provider['source_files'].items():
        if rel == 'Kbuild':
            continue
        source = args.writer_source / rel
        assert sha(source) == digest
        destination = args.output / 'providers/sram73' / rel
        shutil.copyfile(source, destination)
    profile = ['/* SPDX-License-Identifier: GPL-2.0-only */',
               '/* Exact selected OEM carriers. Update through a new reviewed source',
               ' * revision; these hashes prove identity, not authenticity or RF safety. */',
               '#ifndef OM73_FW_PROFILES_H', '#define OM73_FW_PROFILES_H',
               'struct om73_fw_profile { size_t bytes; u8 sha256[32]; };',
               'static const struct om73_fw_profile om73_fw_profiles[] = {']
    for entry in contract['profiles']:
        digest = bytes.fromhex(entry['sha256'])
        assert len(digest) == 32
        profile.append('    { ' + str(entry['carrier_bytes']) + ', { ' +
                       ', '.join('0x%02x' % b for b in digest) + ' } }, /* ' + entry['role'] + ' */')
    profile += ['};', '#endif', '']
    (args.output / 'source/qdrv/om73_fw_profiles.h').write_text('\n'.join(profile), newline='\n')
    path = args.output / 'source/qdrv/qdrv_fw.c'
    text = path.read_text()
    text = text.replace('#include <linux/errno.h>',
                        '#include <linux/errno.h>\n#include <crypto/sha2.h>\n#include <om73_sram_backend.h>\n#include "om73_fw_profiles.h"', 1)
    marker = '\nstatic int qdrv_fw_install_segment('
    assert text.count(marker) == 1
    offset = text.index(marker)
    text = text[:offset] + r'''
/* Identity and the full structural/address plan are checked while the pool's
 * lifecycle lease is held. Thus acquire/close cannot change the arena between
 * exclusion of destinations and the final segment write. Metadata and DSP X/Y
 * skips retain their OEM meaning. This is not proof of indirect writer bounds. */
static int qdrv_fw_writer_preflight(const char *data, size_t size,
                                   enum qdrv_fw_cpu cpu,
                                   const struct om73_sram_writer_token *writer)
{
    Elf32_Ehdr header;
    Elf32_Phdr phdr;
    size_t cursor;
    unsigned long address;
    u8 digest[SHA256_DIGEST_SIZE];
    u32 i;
    int ret;
    if (!data || cpu < qdrv_fw_muc || cpu > qdrv_fw_dsp ||
        size != om73_fw_profiles[cpu].bytes)
        return -EKEYREJECTED;
    sha256((const u8 *)data, size, digest);
    if (memcmp(digest, om73_fw_profiles[cpu].sha256, sizeof(digest)))
        return -EKEYREJECTED;
    ret = qdrv_fw_preflight(data, size, cpu, &header);
    if (ret)
        return ret;
    cursor = sizeof(header) + (size_t)header.e_phnum * sizeof(phdr);
    for (i = 0; i < header.e_phnum; i++) {
        memcpy(&phdr, data + sizeof(header) + i * sizeof(phdr), sizeof(phdr));
        ret = qdrv_fw_check_info(&phdr, data + cursor);
        if (!ret) {
            ret = qdrv_fw_segment_address(&phdr, cpu, &address);
            if (!ret) {
                ret = om73_sram_writer_check(writer, address, phdr.p_memsz);
                if (ret)
                    return ret;
            } else if (ret < 0) {
                return ret;
            }
        }
        cursor += phdr.p_filesz;
    }
    return 0;
}
''' + text[offset:]
    start = text.index('int qdrv_fw_load(struct device *dev,')
    end = text.index('\nint qdrv_fw_load_muc(', start)
    old = text[start:end]
    assert 'request_firmware' in old and 'release_firmware' in old
    new = '''int qdrv_fw_load(struct device *dev,
\t\tchar *firmware,
\t\tuint32_t *start_addr,
\t\tenum qdrv_fw_cpu cpu)
{
\tconst struct firmware *fw;
\tstruct om73_sram_writer_token writer;
\tu32 loaded_entry;
\tint ret, end_ret;

\tif (!start_addr || !firmware || cpu < qdrv_fw_muc || cpu > qdrv_fw_dsp)
\t\treturn -EINVAL;
\tret = request_firmware(&fw, firmware, dev);
\tif (ret)
\t\treturn ret;
\tret = om73_sram_writer_begin(cpu, &writer);
\tif (ret)
\t\tgoto release;
\tret = qdrv_fw_writer_preflight((const char *)fw->data, fw->size, cpu, &writer);
\tif (!ret)
\t\tret = qdrv_fw_install((const char *)fw->data, fw->size, &loaded_entry, cpu);
\tend_ret = om73_sram_writer_end(&writer);
\tif (ret > 0 && end_ret)
\t\tret = end_ret;
\tif (ret > 0)
\t\t*start_addr = loaded_entry;
release:
\trelease_firmware(fw);
\treturn ret;
}
'''
    text = text[:start] + new + text[end:]
    path.write_text(text, newline='\n')
    result = dict(parent)
    result.update(status='SOURCE_ONLY_LINUX73_EXACT_CARRIER_WRITER_LEASE_PENDING_VERIFICATION',
                  parent=str(args.parent), parent_result_sha256=sha(args.parent / 'result.json'),
                  writer_provider_result_sha256=sha(args.writer_source / 'result.json'),
                  carrier_contract_sha256=sha(args.carrier_contract),
                  reconstruction_tool_sha256=sha(Path(__file__)),
                  files={p.relative_to(args.output).as_posix(): sha(p)
                         for group in ('source', 'headers', 'providers', 'kernel-overlay')
                         for p in (args.output / group).rglob('*') if p.is_file()},
                  hardware_accessed=False, firmware_eligible=False,
                  exact_carrier_identities=True, writer_lease_connected=True,
                  limits=['Identity hashing and destinations are verified under a shared pool lifecycle lease.',
                          'Fixed source hashes require a new reviewed profile for future firmware updates.',
                          'No automatic board reservation, runtime writer exclusion, reset quiescence or RF proof.',
                          'A map failure can leave preceding writes; no firmware entry is published on failure.'])
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'files': len(result['files']),
                      'loader_sha256': sha(path), 'hardware_accessed': False}))


if __name__ == '__main__':
    main()
