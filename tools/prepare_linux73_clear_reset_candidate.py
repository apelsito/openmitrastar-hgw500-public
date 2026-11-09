"""Compose a versioned port with clear/load and reset lifecycle ownership.

Changes source only. No MMIO, firmware loading, board registration or radio access.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent', type=Path, required=True)
    p.add_argument('--reset-provider', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    parent = json.loads((a.parent / 'result.json').read_text())
    for rel, h in parent['files'].items():
        assert sha(a.parent / rel.replace('\\', '/')) == h
    provider = json.loads((a.reset_provider / 'result.json').read_text())
    shutil.copytree(a.parent, a.output)
    for rel, h in provider['source_files'].items():
        if rel == 'Kbuild':
            continue
        src = a.reset_provider / rel
        assert sha(src) == h
        shutil.copyfile(src, a.output / 'providers/sram73' / rel)
    changed = {}

    rel = 'source/qdrv/qdrv_fw.h'
    path = a.output / rel
    text = path.read_text()
    text = text.replace('\n#endif', '''
/* Prepare callback executes after exact carrier/full destination preflight,
 * under the same task-owned writer lease as the actual firmware installation. */
struct om73_sram_writer_token;
typedef int (*qdrv_fw_prepare_fn)(const struct om73_sram_writer_token *, void *);
int qdrv_fw_load_auc_prepared(struct device *, char *, uint32_t *,
                             qdrv_fw_prepare_fn, void *);

#endif''', 1)
    path.write_text(text, newline='\n'); changed[rel] = sha(path)

    rel = 'source/qdrv/qdrv_fw.c'
    path = a.output / rel
    text = path.read_text()
    old = '''int qdrv_fw_load(struct device *dev,
\t\tchar *firmware,
\t\tuint32_t *start_addr,
\t\tenum qdrv_fw_cpu cpu)'''
    assert text.count(old) == 1
    text = text.replace(old, '''int qdrv_fw_load_prepared(struct device *dev,
\t\tchar *firmware,
\t\tuint32_t *start_addr,
\t\tenum qdrv_fw_cpu cpu, qdrv_fw_prepare_fn prepare, void *context)''', 1)
    old = '\tret = qdrv_fw_writer_preflight((const char *)fw->data, fw->size, cpu, &writer);\n\tif (!ret)'
    assert text.count(old) == 1
    text = text.replace(old, '''\tret = qdrv_fw_writer_preflight((const char *)fw->data, fw->size, cpu, &writer);
\tif (!ret && prepare) {
\t\tret = prepare(&writer, context);
\t\tif (ret > 0)
\t\t\tret = -EPROTO;
\t}
\tif (!ret)''', 1)
    marker = '\nint qdrv_fw_load_muc('
    assert text.count(marker) == 1
    text = text.replace(marker, '''
static int qdrv_fw_load(struct device *dev, char *firmware, uint32_t *start,
                         enum qdrv_fw_cpu cpu)
{
    return qdrv_fw_load_prepared(dev, firmware, start, cpu, NULL, NULL);
}

int qdrv_fw_load_auc_prepared(struct device *dev, char *firmware, uint32_t *start,
                             qdrv_fw_prepare_fn prepare, void *context)
{
    if (!prepare)
        return -EINVAL;
    return qdrv_fw_load_prepared(dev, firmware, start, qdrv_fw_auc, prepare, context);
}
''' + marker, 1)
    path.write_text(text, newline='\n'); changed[rel] = sha(path)

    rel = 'source/qdrv/qdrv_auc.c'
    path = a.output / rel
    text = path.read_text().replace('#include <linux/version.h>',
                                  '#include <linux/version.h>\n#include <om73_sram_backend.h>', 1)
    start = text.index('static void auc_clear_addr_range(')
    end = text.index('\nvoid qdrv_auc_stats_setup(', start)
    text = text[:start] + '''static int auc_clear_addr_range(unsigned long physaddr, unsigned long size)
{
\tvoid *vaddr = ioremap_nocache(physaddr, size);
\tif (!vaddr) {
\t\tDBGPRINTF_E("0x%lx, 0x%lx cannot be mapped\\n", physaddr, size);
\t\treturn -ENOMEM;
\t}
\tqdrv_fw_auc_memzero(vaddr, size, physaddr);
\tiounmap(vaddr);
\treturn 0;
}

static int auc_clear_mem(const struct om73_sram_writer_token *writer, void *context)
{
\tstatic const struct { unsigned long address, size; } regions[] = {
\t\t{ TOPAZ_AUC_IMEM_ADDR, TOPAZ_AUC_IMEM_SIZE },
\t\t{ TOPAZ_AUC_DMEM_ADDR, TOPAZ_AUC_DMEM_SIZE },
\t\t{ RUBY_DRAM_BEGIN + CONFIG_ARC_AUC_BASE, CONFIG_ARC_AUC_SIZE },
\t\t{ RUBY_SRAM_BEGIN + CONFIG_ARC_AUC_SRAM_BASE, CONFIG_ARC_AUC_SRAM_SIZE },
\t};
\tunsigned int i;
\tint ret;
\t(void)context;
\t/* Admission of every clear span precedes the first clear mapping. */
\tfor (i = 0; i < ARRAY_SIZE(regions); i++) {
\t\tret = om73_sram_writer_check(writer, regions[i].address, regions[i].size);
\t\tif (ret)
\t\t\treturn ret;
\t}
\tfor (i = 0; i < ARRAY_SIZE(regions); i++) {
\t\tret = auc_clear_addr_range(regions[i].address, regions[i].size);
\t\tif (ret)
\t\t\treturn ret;
\t}
\treturn 0;
}
''' + text[end:]
    old = '''\tauc_clear_mem();

\tif (qdrv_fw_load_auc(qcb->dev, qcb->auc_firmware, &auc_start_addr) < 0) {'''
    assert text.count(old) == 1
    text = text.replace(old, '''\t/* Hashes/load destinations and all clear spans share one writer lease. */
\tif (qdrv_fw_load_auc_prepared(qcb->dev, qcb->auc_firmware, &auc_start_addr,
\t\t\tauc_clear_mem, NULL) < 0) {''', 1)
    path.write_text(text, newline='\n'); changed[rel] = sha(path)

    rel = 'source/qdrv/qdrv_control.c'
    path = a.output / rel
    text = path.read_text().replace('#include <linux/string.h>',
                                  '#include <linux/string.h>\n#include <om73_sram_backend.h>', 1)
    helper_at = text.index('static int qdrv_command_clearsram(struct device *dev, int argc, char *argv[])\n{')
    text = text[:helper_at] + '''static int qdrv_clearsram_capture_log(const struct qdrv_clearsram_region *stack)
{
\tvoid __iomem *mapped;
\tchar *copy;
\tu16 bytes;
\tint ret = 0;
\tif (qdrv_crash_log)
\t\treturn 0;
\tmapped = ioremap_nocache(stack->start, stack->size);
\tif (!mapped)
\t\treturn -ENOMEM;
\tif (readw(mapped) != HEADER_CORE_DUMP)
\t\tgoto out;
\tbytes = readw((u8 __iomem *)mapped + sizeof(u16));
\tif (bytes > stack->size - 2 * sizeof(u16)) {
\t\tret = -ERANGE;
\t\tgoto out;
\t}
\tcopy = kmalloc(bytes, GFP_KERNEL);
\tif (!copy) {
\t\tret = -ENOMEM;
\t\tgoto out;
\t}
\tmemcpy_fromio(copy, (u8 __iomem *)mapped + 2 * sizeof(u16), bytes);
\tqdrv_crash_log_len = bytes;
\tqdrv_crash_log = copy;
out:
\tiounmap(mapped);
\treturn ret;
}

''' + text[helper_at:]
    old = 'static int qdrv_command_clearsram(struct device *dev, int argc, char *argv[])\n{'
    text = text.replace(old, '''static int qdrv_command_clearsram_owned(struct device *dev, int argc, char *argv[],
                                        const struct om73_sram_writer_token *writer)
{''', 1)
    start = text.index('static int qdrv_command_clearsram_owned(')
    end = text.index('\nstatic int qdrv_command_bridge(', start)
    body = text[start:end].replace('\tuint16_t *buf;\n', '')
    old = '\tbuf = (uint16_t *)stack_start;'
    old_start = body.index(old)
    old_end = body.index('\n\t/* Fill only the five OEM firmware regions', old_start)
    body = body[:old_start] + '''\tret = om73_sram_writer_check(writer, stack_region.start, stack_region.size);
\tif (ret)
\t\treturn ret;
\tfor (i = 0; i < ARRAY_SIZE(regions); i++) {
\t\tret = om73_sram_writer_check(writer, regions[i].start, regions[i].size);
\t\tif (ret)
\t\t\treturn ret;
\t}
\t/* Copy out any crash log, let the parse function deal with validity of the buffer */
\tret = qdrv_clearsram_capture_log(&stack_region);
\tif (ret)
\t\treturn ret;
''' + body[old_end:]
    wrapper = '''
static int qdrv_command_clearsram(struct device *dev, int argc, char *argv[])
{
\tstruct om73_sram_writer_token writer;
\tint ret, end_ret;
\tret = om73_sram_writer_begin(0, &writer);
\tif (ret)
\t\treturn ret;
\tret = qdrv_command_clearsram_owned(dev, argc, argv, &writer);
\tend_ret = om73_sram_writer_end(&writer);
\treturn ret ? ret : end_ret;
}
'''
    text = text[:start] + body + wrapper + text[end:]
    path.write_text(text, newline='\n'); changed[rel] = sha(path)

    rel = 'source/qdrv/qdrv_soc.c'
    path = a.output / rel
    text = path.read_text().replace('#include <linux/device.h>',
                                  '#include <linux/device.h>\n#include <om73_sram_backend.h>', 1)
    marker = '\nint qdrv_soc_init(struct device *dev)'
    text = text.replace(marker, '''
static int qdrv_soc_admitted_core_reset(void)
{
\tstruct om73_sram_reset_token reset;
\tint ret, end_ret;
\t/* This software lease does not prove NETSS/TQE/firmware quiescence.
\t * It must reject live pool owners before lifetime promotion or MMIO. */
\tret = om73_sram_reset_begin(0x4180U, &reset);
\tif (ret)
\t\treturn ret;
\tret = qdrv_f355_core_begin();
\tif (!ret)
\t\thal_reset();
\tend_ret = om73_sram_reset_end(&reset);
\tif (!ret && end_ret) {
\t\tqdrv_f355_boot_failure();
\t\tret = end_ret;
\t}
\treturn ret;
}
''' + marker, 1)
    start = text.index('int qdrv_soc_init(struct device *dev)')
    prefix, body = text[:start], text[start:]
    old = '\tretval=qdrv_f355_core_begin();\n\tif(retval)return retval;\n\thal_reset();'
    assert body.count(old) == 1
    body = body.replace(old, '\tretval = qdrv_soc_admitted_core_reset();\n\tif (retval)\n\t\treturn retval;', 1)
    path.write_text(prefix + body, newline='\n'); changed[rel] = sha(path)

    result = dict(parent)
    requirements = list(parent.get('new_kernel_config_required', []))
    if 'CRYPTO_LIB_SHA256=y' not in requirements:
        requirements.append('CRYPTO_LIB_SHA256=y')
    result.update(status='SOURCE_ONLY_LINUX73_CLEAR_LOAD_RESET_LEASES_PENDING_QUALIFICATION',
                  parent=str(a.parent), parent_result_sha256=sha(a.parent / 'result.json'),
                  reset_provider_result_sha256=sha(a.reset_provider / 'result.json'),
                  reconstruction_tool_sha256=sha(Path(__file__)),
                  new_kernel_config_required=requirements, changed_sources=changed,
                  files={p.relative_to(a.output).as_posix(): sha(p)
                         for group in ('source', 'headers', 'providers', 'kernel-overlay')
                         for p in (a.output / group).rglob('*') if p.is_file()},
                  hardware_accessed=False, firmware_eligible=False,
                  limits=['AuC clear is admitted only after carrier identity and full destination preflight under one writer lease.',
                          'Clearsram maps crash-log memory rather than dereferencing a literal physical pointer.',
                          'Reset software lease rejects live pool owners before F355 promotion; it is not physical producer quiescence.',
                          'No automatic pool reservation, heap reset, radio start or physical acceptance.'])
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'files': len(result['files']), 'changed': changed}))


if __name__ == '__main__':
    main()
