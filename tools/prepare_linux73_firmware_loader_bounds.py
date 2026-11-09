"""Add bounded, side-effect-free firmware preflight to a new Linux7.3 candidate.

Preserves the selected OEM packed payload format, FWINFO semantics and comments.
No firmware installation, mapping, device access or original-file changes.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


VALIDATION = r'''
/* The shipping carriers pack their program table directly after Ehdr and
 * concatenate payloads. BSS-only p_offset may refer to an earlier payload;
 * no data is read for those entries. Preserve that format, but validate every
 * byte/range before the first map/copy or publishing a start address. */
static int qdrv_fw_physical_range(unsigned long address, u32 bytes,
                                 enum qdrv_fw_cpu cpu)
{
    unsigned long end;
    if (!bytes || address > U32_MAX - (bytes - 1))
        return -ERANGE;
    end = address + bytes - 1;
    if (__in_mem_range(address, RUBY_SRAM_BEGIN, RUBY_SRAM_SIZE) &&
        __in_mem_range(end, RUBY_SRAM_BEGIN, RUBY_SRAM_SIZE))
        return 0;
    if (__in_mem_range(address, RUBY_DRAM_BEGIN, RUBY_MAX_DRAM_SIZE) &&
        __in_mem_range(end, RUBY_DRAM_BEGIN, RUBY_MAX_DRAM_SIZE))
        return 0;
    if (cpu == qdrv_fw_auc &&
        ((__in_mem_range(address, TOPAZ_AUC_IMEM_ADDR, TOPAZ_AUC_IMEM_SIZE) &&
          __in_mem_range(end, TOPAZ_AUC_IMEM_ADDR, TOPAZ_AUC_IMEM_SIZE)) ||
         (__in_mem_range(address, TOPAZ_AUC_DMEM_ADDR, TOPAZ_AUC_DMEM_SIZE) &&
          __in_mem_range(end, TOPAZ_AUC_DMEM_ADDR, TOPAZ_AUC_DMEM_SIZE))))
        return 0;
    return -ERANGE;
}

static int qdrv_fw_segment_address(const Elf32_Phdr *phdr,
                                   enum qdrv_fw_cpu cpu,
                                   unsigned long *address)
{
    unsigned long source;
    void *host;
    if (cpu == qdrv_fw_dsp && phdr->p_vaddr >= RUBY_DSP_XYMEM_BEGIN &&
        phdr->p_vaddr <= RUBY_DSP_XYMEM_END) {
        if (!phdr->p_memsz || phdr->p_memsz - 1 > RUBY_DSP_XYMEM_END - phdr->p_vaddr)
            return -ERANGE;
        return 1; /* Retain the DSP X/Y skip; this loader does not write it. */
    }
    if (cpu < qdrv_fw_muc || cpu > qdrv_fw_dsp)
        return -EINVAL;
    source = cpu == qdrv_fw_dsp ? phdr->p_vaddr :
             (phdr->p_paddr ? phdr->p_paddr : phdr->p_vaddr);
    host = cpu == qdrv_fw_muc ? (void *)muc_to_lhost(source) : bus_to_virt(source);
    if (host == RUBY_BAD_VIRT_ADDR)
        return -ERANGE;
    *address = virt_to_phys(host);
    return qdrv_fw_physical_range(*address, phdr->p_memsz, cpu);
}

static int qdrv_fw_preflight(const char *data, size_t size,
                             enum qdrv_fw_cpu cpu, Elf32_Ehdr *header)
{
    Elf32_Phdr phdr;
    size_t cursor, table_bytes;
    unsigned long address;
    u32 i;
    int ret;
    if (!data || !header || size < sizeof(*header) ||
        cpu < qdrv_fw_muc || cpu > qdrv_fw_dsp)
        return -EINVAL;
    memcpy(header, data, sizeof(*header));
    if (memcmp(header->e_ident, ELFMAG, SELFMAG) ||
        header->e_ident[EI_CLASS] != ELFCLASS32 ||
        header->e_ident[EI_DATA] != ELFDATA2LSB ||
        header->e_ident[EI_VERSION] != EV_CURRENT ||
        header->e_version != EV_CURRENT || header->e_type != ET_EXEC ||
        header->e_machine != EM_ARCOMPACT ||
        header->e_ehsize != sizeof(*header) ||
        header->e_phoff != sizeof(*header) ||
        header->e_phentsize != sizeof(phdr) || !header->e_phnum)
        return -ENOEXEC;
    table_bytes = (size_t)header->e_phnum * sizeof(phdr);
    if (table_bytes > size - sizeof(*header))
        return -EINVAL;
    cursor = sizeof(*header) + table_bytes;
    for (i = 0; i < header->e_phnum; i++) {
        memcpy(&phdr, data + sizeof(*header) + i * sizeof(phdr), sizeof(phdr));
        if (phdr.p_type != PT_LOAD || phdr.p_filesz > phdr.p_memsz ||
            phdr.p_filesz > size - cursor || phdr.p_offset > size ||
            (phdr.p_filesz && phdr.p_offset != cursor))
            return -EINVAL;
        ret = qdrv_fw_check_info(&phdr, data + cursor);
        if (ret < 0)
            return ret;
        if (!ret) {
            ret = qdrv_fw_segment_address(&phdr, cpu, &address);
            if (ret < 0)
                return ret;
        }
        cursor += phdr.p_filesz;
    }
    /* Entry is processor-relative, while p_paddr may hold a load copy address.
     * Validate it independently without demanding it match the load-copy VA. */
    memset(&phdr, 0, sizeof(phdr));
    phdr.p_vaddr = header->e_entry;
    phdr.p_memsz = 1;
    ret = qdrv_fw_segment_address(&phdr, cpu, &address);
    return ret ? (ret < 0 ? ret : -ERANGE) : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    proof = json.loads((args.parent / 'result.json').read_text())
    for rel, digest in proof['files'].items():
        assert sha(args.parent / rel.replace('\\', '/')) == digest
    shutil.copytree(args.parent, args.output)
    path = args.output / 'source/qdrv/qdrv_fw.c'
    text = path.read_text()
    enum_end = text.index('\n};', text.index('enum qdrv_fw_cpu {')) + 3
    text = text[:enum_end] + '\n' + VALIDATION + text[enum_end:]
    start = text.index('static void qdrv_fw_install_segment(')
    end = text.index('\nstatic int qdrv_fw_install(', start)
    original = text[start:end]
    segment = original.replace('static void qdrv_fw_install_segment(', 'static int qdrv_fw_install_segment(', 1)
    addr_start = segment.index('\tif (cpu == qdrv_fw_dsp) {')
    addr_end = segment.index('\n\tDBGPRINTF(', addr_start)
    segment = segment[:addr_start] + '''\tint ret = qdrv_fw_segment_address(phdr, cpu, &paddr);
\tif (ret)
\t\treturn ret > 0 ? 0 : ret;
''' + segment[addr_end:]
    segment = segment.replace('\tvaddr = ioremap_nocache(paddr, phdr->p_memsz);',
                              '\tvaddr = ioremap_nocache(paddr, phdr->p_memsz);\n\tif (!vaddr)\n\t\treturn -ENOMEM;', 1)
    segment = segment.replace('\tiounmap(vaddr);\n}', '\tiounmap(vaddr);\n\treturn 0;\n}', 1)
    text = text[:start] + segment + text[end:]
    start = text.index('static int qdrv_fw_install(')
    end = text.index('\nstatic const char *qdrv_fw_cpu_str', start)
    text = text[:start] + '''static int qdrv_fw_install(const char *data, size_t size,
                           uint32_t *start_addr, enum qdrv_fw_cpu cpu)
{
\tElf32_Ehdr header;
\tElf32_Phdr phdr;
\tsize_t cursor;
\tu32 i;
\tint ret;

\tif (!start_addr)
\t\treturn -EINVAL;
\tret = qdrv_fw_preflight(data, size, cpu, &header);
\tif (ret)
\t\treturn ret;
\tcursor = sizeof(header) + (size_t)header.e_phnum * sizeof(phdr);
\tfor (i = 0; i < header.e_phnum; i++) {
\t\tmemcpy(&phdr, data + sizeof(header) + i * sizeof(phdr), sizeof(phdr));
\t\tret = qdrv_fw_check_info(&phdr, data + cursor);
\t\tif (!ret) {
\t\t\tret = qdrv_fw_install_segment(&phdr, data + cursor, cpu);
\t\t\tif (ret)
\t\t\t\treturn ret;
\t\t}
\t\tcursor += phdr.p_filesz;
\t}
\t/* Publish entry only after every segment was successfully installed. */
\t*start_addr = header.e_entry;
\treturn header.e_phnum;
}
''' + text[end:]
    old = 'ret = qdrv_fw_install((char *)fw->data, start_addr, cpu);'
    assert text.count(old) == 1
    text = text.replace(old, 'ret = qdrv_fw_install((const char *)fw->data, fw->size, start_addr, cpu);')
    path.write_text(text, newline='\n')
    result = dict(proof)
    result.update(status='SOURCE_ONLY_LINUX73_TYPED_SRAM_AND_BOUNDED_FW_LOADER_PENDING_QUALIFICATION',
                  parent=str(args.parent), parent_result_sha256=sha(args.parent / 'result.json'),
                  reconstruction_tool_sha256=sha(Path(__file__)),
                  changed_sources={'source/qdrv/qdrv_fw.c': sha(path)},
                  files={p.relative_to(args.output).as_posix(): sha(p)
                         for group in ('source', 'headers', 'providers', 'kernel-overlay')
                         for p in (args.output / group).rglob('*') if p.is_file()},
                  hardware_accessed=False, firmware_eligible=False,
                  loader_preflight_source_only=True,
                  limits=['Packed OEM carrier format, metadata and addresses require actual fixture and ARC build qualification.',
                          'Structural/address errors rejected before first segment map; allocation failures are propagated.',
                          'Mapping failure may leave earlier installed segments; no CPU entry published on failure.',
                          'SRAM reservation and runtime writers still unproved; no board registration or physical loading.'])
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'loader_sha256': sha(path), 'files': len(result['files'])}))


if __name__ == '__main__':
    main()
