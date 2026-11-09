"""Compose an immutable Linux7.3 candidate using typed SRAM DMA ownership.

Uses a separately source-verified pool adapter; never maps SRAM or loads modules.
All originals remain unchanged. The kernel/board reservation is a separate gate.
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
    parser.add_argument('--pool-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Use a new candidate output'
    proof = json.loads((args.parent / 'result.json').read_text())
    for stored, digest in proof['files'].items():
        assert sha(args.parent / stored.replace('\\', '/')) == digest, stored
    assert sha(args.parent / 'Kbuild') == proof['kbuild_sha256']
    shutil.copytree(args.parent, args.output)
    pool = json.loads((args.pool_source / 'result.json').read_text())
    for stored, digest in pool['source_files'].items():
        if stored == 'Kbuild':
            continue
        source = args.pool_source / stored.replace('\\', '/')
        assert sha(source) == digest
        destination = args.output / 'providers/sram73' / stored.replace('\\', '/')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    relative = 'source/platform/ruby/dmautil.c'
    path = args.output / relative
    text = path.read_text()
    text = text.replace('#include <linux/log2.h>',
                        '#include <linux/log2.h>\n#include <om73_sram_backend.h>', 1)
    text = text.replace('\tbool is_sram;\n};',
                        '\tbool is_sram;\n\tstruct om73_sram_allocation sram;\n};', 1)
    start = text.index('static void om_dma_release(')
    end = text.index('\nint dmautil_aligned_dma_desc_alloc(', start)
    old_release = text[start:end]
    assert 'heap_sram_free(record->raw)' in old_release
    text = text[:start] + '''static void om_dma_release(struct om_dma_allocation *record)
{
\tif (record->is_sram && record->sram.io_map) {
\t\t/* The pool owns the mapping and translates bus/physical addresses.
\t\t * Keep the private owner alive if it refuses a corrupted free. */
\t\tif (WARN_ON_ONCE(om73_sram_free(record)))
\t\t\treturn;
\t} else {
\t\tif (record->mapped)
\t\t\tiounmap(record->mapped);
\t\tif (record->raw)
\t\t\tkfree(record->raw);
\t}
\tkfree(record);
}
''' + text[end:]
    text = text.replace('\tunsigned long flags;\n\n\tif (!d',
                        '\tunsigned long flags;\n\tint ret;\n\n\tif (!d', 1)
    start = text.index('\trecord->raw = is_sram ? heap_sram_alloc(')
    end = text.index('\tallocated.descs = record->mapped;', start)
    end += len('\tallocated.descs = record->mapped;')
    original = text[start:end]
    assert 'virt_to_bus' in original and 'ioremap_nocache' in original
    dram = original.replace('record->raw = is_sram ? heap_sram_alloc(alloc_size) : kmalloc(alloc_size, GFP_KERNEL);',
                            'record->raw = kmalloc(alloc_size, GFP_KERNEL);')
    dram = '\n'.join('\t' + line if line else line for line in dram.splitlines())
    text = text[:start] + '''\tif (is_sram) {
\t\t/* Align the physical SRAM offset, not the vmalloc alias. This request
\t\t * has its own private key until the descriptor owner is committed. */
\t\tret = om73_sram_alloc(record, remap_size, align, &record->sram);
\t\tif (ret) {
\t\t\tom_dma_release(record);
\t\t\treturn ret;
\t\t}
\t\tallocated.desc_count = desc_count;
\t\tallocated.unaligned_vdescs = (unsigned long)record->sram.io_map;
\t\tallocated.aligned_vdescs = (unsigned long)record->sram.io_map;
\t\tallocated.descs_dma_addr = record->sram.bus;
\t\trecord->mapped = record->sram.io_map;
\t\tallocated.descs = record->sram.io_map;
\t} else {
''' + dram + '''
\t}''' + text[end:]
    text = text.replace('\tmemset(allocated.descs, 0, remap_size);',
                        '\tif (is_sram)\n\t\tmemset_io(allocated.descs, 0, remap_size);\n\telse\n\t\tmemset(allocated.descs, 0, remap_size);', 1)
    assert 'heap_sram_alloc(' not in text and 'heap_sram_free(' not in text
    path.write_text(text, newline='\n')
    build = (args.output / 'Kbuild').read_text()
    build += '\nccflags-y += -I$(src)/providers/sram73\nom73_sram-y := providers/sram73/om_sram_core.o providers/sram73/om73_sram_backend.o\nobj-m += om73_sram.o\n'
    (args.output / 'Kbuild').write_text(build, newline='\n')
    result = dict(proof)
    result.update(status='SOURCE_ONLY_LINUX73_TYPED_SRAM_DMA_POOL_PENDING_BUILD_AND_BOARD_RESERVATION',
                  hardware_accessed=False, firmware_eligible=False,
                  parent=str(args.parent), parent_result_sha256=sha(args.parent / 'result.json'),
                  pool_result_sha256=sha(args.pool_source / 'result.json'),
                  reconstruction_tool_sha256=sha(Path(__file__)),
                  typed_sram_dma=True, board_reservation_registered=False,
                  driver_load_accepted=False,
                  changed_sources={relative: sha(path)},
                  files={p.relative_to(args.output).as_posix(): sha(p)
                         for group in ('source', 'headers', 'providers', 'kernel-overlay')
                         for p in (args.output / group).rglob('*') if p.is_file()},
                  kbuild_sha256=sha(args.output / 'Kbuild'),
                  limits=['Source integration only. No physical address conversion from vmalloc SRAM alias.',
                          'Physical SRAM map/resource and firmware runtime occupancy still require an owned board contract.',
                          'Pool remains closed until a kernel board caller registers that verified reservation.',
                          'R20 records and wire descriptor layout preserved; no new functional/RF/physical acceptance.'])
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'files': len(result['files']),
                      'changed_dma_sha256': sha(path), 'hardware_accessed': False}))


if __name__ == '__main__':
    main()
