"""Keep module callbacks and DMA allocations owned without changing wire layouts."""
import argparse, hashlib, json, shutil
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    shutil.copytree(args.parent, args.output)
    changes = {}
    rel = 'source/platform/ruby/gpio.c'
    path = args.output / rel
    text = path.read_text()
    old = '\tarc_gpio.chip.label = "arcgpio";'
    assert text.count(old) == 1
    text = text.replace(old, old + '\n\tarc_gpio.chip.owner = THIS_MODULE;', 1)
    old = 'arch_initcall(arc_gpio_init);'
    assert text.count(old) == 1
    text = text.replace(old, '''static void __exit arc_gpio_exit(void)
{
\tgpiochip_remove(&arc_gpio.chip);
}

/* Built-in builds retain the original architecture init ordering. */
#ifdef MODULE
module_init(arc_gpio_init);
#else
arch_initcall(arc_gpio_init);
#endif
module_exit(arc_gpio_exit);''', 1)
    path.write_text(text, newline='\n')
    changes[rel] = sha(path)

    rel = 'source/platform/ruby/dmautil.c'
    path = args.output / rel
    old = path.read_text()
    start = old.index('#include <qtn/dmautil.h>')
    text = old[:start] + '''#include <qtn/dmautil.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/list.h>
#include <linux/spinlock.h>
#include <linux/overflow.h>
#include <linux/log2.h>
#include <asm/io.h>
#include <asm/cacheflush.h>

/* Host-only allocation ownership. The shared descriptor/wire ABI is unchanged.
 * The caller serializes allocation/free for each descriptor owner. */
struct om_dma_allocation {
\tstruct list_head link;
\taligned_dma_descs *owner;
\tvoid *raw;
\tvoid __iomem *mapped;
\tbool is_sram;
};

static LIST_HEAD(om_dma_allocations);
static DEFINE_SPINLOCK(om_dma_allocations_lock);

static struct om_dma_allocation *om_dma_find_owner(aligned_dma_descs *owner)
{
\tstruct om_dma_allocation *record;

\tlist_for_each_entry(record, &om_dma_allocations, link) {
\t\tif (record->owner == owner)
\t\t\treturn record;
\t}
\treturn NULL;
}

static void om_dma_release(struct om_dma_allocation *record)
{
\tif (record->mapped)
\t\tiounmap(record->mapped);
\tif (record->raw) {
\t\tif (record->is_sram)
\t\t\theap_sram_free(record->raw);
\t\telse
\t\t\tkfree(record->raw);
\t}
\tkfree(record);
}

int dmautil_aligned_dma_desc_alloc(aligned_dma_descs *d,
\t\tunsigned int desc_size, unsigned int desc_count,
\t\tunsigned int align, bool is_sram)
{
\tstruct om_dma_allocation *record;
\taligned_dma_descs allocated = { 0 };
\tsize_t remap_size, alloc_size;
\tunsigned long flags;

\tif (!d || !desc_size || !desc_count || !is_power_of_2(align))
\t\treturn -EINVAL;
\tif (check_mul_overflow((size_t)desc_size, (size_t)desc_count, &remap_size) ||
\t\tcheck_add_overflow(remap_size, (size_t)align - 1, &alloc_size))
\t\treturn -EOVERFLOW;

\tspin_lock_irqsave(&om_dma_allocations_lock, flags);
\tif (om_dma_find_owner(d)) {
\t\tspin_unlock_irqrestore(&om_dma_allocations_lock, flags);
\t\treturn -EBUSY;
\t}
\tspin_unlock_irqrestore(&om_dma_allocations_lock, flags);

\trecord = kzalloc(sizeof(*record), GFP_KERNEL);
\tif (!record)
\t\treturn -ENOMEM;
\trecord->owner = d;
\trecord->is_sram = is_sram;
\trecord->raw = is_sram ? heap_sram_alloc(alloc_size) : kmalloc(alloc_size, GFP_KERNEL);
\tif (!record->raw) {
\t\tom_dma_release(record);
\t\treturn -ENOMEM;
\t}

\tallocated.desc_count = desc_count;
\tallocated.unaligned_vdescs = (unsigned long)record->raw;
\tflush_dcache_range(allocated.unaligned_vdescs, allocated.unaligned_vdescs + alloc_size);
\tallocated.aligned_vdescs = align_val_up(allocated.unaligned_vdescs, align);
\tallocated.descs_dma_addr = virt_to_bus((void *)allocated.aligned_vdescs);
\trecord->mapped = ioremap_nocache(allocated.aligned_vdescs, remap_size);
\tif (!record->mapped) {
\t\tom_dma_release(record);
\t\treturn -ENOMEM;
\t}
\tallocated.descs = record->mapped;
\tmemset(allocated.descs, 0, remap_size);

\tspin_lock_irqsave(&om_dma_allocations_lock, flags);
\t/* Also reject an allocation committed while this one was preparing. */
\tif (om_dma_find_owner(d)) {
\t\tspin_unlock_irqrestore(&om_dma_allocations_lock, flags);
\t\tom_dma_release(record);
\t\treturn -EBUSY;
\t}
\t*d = allocated;
\tlist_add(&record->link, &om_dma_allocations);
\tspin_unlock_irqrestore(&om_dma_allocations_lock, flags);
\treturn 0;
}
EXPORT_SYMBOL(dmautil_aligned_dma_desc_alloc);

void dmautil_aligned_dma_desc_free(aligned_dma_descs *d)
{
\tstruct om_dma_allocation *record;
\tunsigned long flags;

\tif (!d)
\t\treturn;
\tspin_lock_irqsave(&om_dma_allocations_lock, flags);
\trecord = om_dma_find_owner(d);
\tif (record) {
\t\tlist_del(&record->link);
\t\tmemset(d, 0, sizeof(*d));
\t}
\tspin_unlock_irqrestore(&om_dma_allocations_lock, flags);
\t/* Unknown/repeated frees never unmap or free an inferred address. */
\tif (record)
\t\tom_dma_release(record);
}
EXPORT_SYMBOL(dmautil_aligned_dma_desc_free);

MODULE_DESCRIPTION("Quantenna owned aligned DMA descriptor allocator");
MODULE_LICENSE("GPL");
'''
    path.write_text(text, newline='\n')
    changes[rel] = sha(path)
    proof = json.loads((args.parent / 'result.json').read_text())
    proof.update(status='SOURCE_ONLY_LINUX73_NATIVE_OWNERSHIP_PENDING_BUILD_AND_TEST',
                 parent=str(args.parent), changed_sources=changes, firmware_eligible=False,
                 native_ownership_changes=[
                     'GPIO chip pins calling module; unregister removes callbacks at exit',
                     'DMA rejects invalid dimensions, alignment and size overflow',
                     'DMA records exact backend/raw/map/owner in private host memory',
                     'DMA duplicate allocation and unknown/repeated frees fail closed',
                     'Shared DMA descriptor layout and wire addresses unchanged',
                 ])
    proof['files'] = {str(p.relative_to(args.output)): sha(p) for group in ('source','headers','kernel-overlay','providers') for p in (args.output / group).rglob('*') if p.is_file()}
    (args.output / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'status': proof['status'], 'changed_sources': changes}, indent=2))

if __name__ == '__main__':
    main()
