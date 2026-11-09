"""Compose a kernel-only SRAM resource/mapping owner around the recovered OEM core."""
import argparse, hashlib, json, shutil
from pathlib import Path

HEADER = r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OM73_SRAM_BACKEND_H
#define OM73_SRAM_BACKEND_H
#include <linux/types.h>
#include <linux/ioport.h>
#include "om_sram_core.h"

/* Only a compiled kernel board caller may admit an arena. These pins identify
 * evidence verified by that caller; nonzero hashes alone never prove occupancy.
 * No module parameter, userspace ioctl, DT yes flag, or guessed free gap may
 * construct this admission contract. Registration is absent by default. */
struct om73_sram_board_contract {
 struct om_sram_contract arena;
 u8 kernel_occupancy_sha256[32];
 u8 selected_carriers_sha256[32];
 u8 complete_writers_map_sha256[32];
};

struct om73_sram_allocation {
 phys_addr_t cpu_phys;
 dma_addr_t bus;
 void __iomem *io_map;
 size_t size;
 u32 extent_offset; /* raw allocation offset, including alignment slack */
 u32 extent_bytes;  /* raw requested bytes, excludes OEM core block header */
 u32 generation;
};

/* acquire/close may sleep; call them only from serialized process context.
 * acquire owns the exclusive iomem resource lease and one NC mapping. The
 * mapping is never returned as an identity CPU/bus pointer. No DRAM fallback.
 * alloc/free/query perform no sleeping operations and use irqsave locking.
 * Callers serialize operations for each owner and quiesce devices before free.
 */
int om73_sram_acquire(const struct om73_sram_board_contract *board);
int om73_sram_close(void);
int om73_sram_alloc(const void *owner, size_t bytes, unsigned int alignment,
                    struct om73_sram_allocation *out);
int om73_sram_query(const void *owner, struct om73_sram_allocation *out);
int om73_sram_free(const void *owner);
#endif
'''

SOURCE = r'''/* SPDX-License-Identifier: GPL-2.0-only */
/* Real Linux 7.3 resource owner; no automatic registration or physical action.
 * The SRAM is RAM-like storage accessed through a single forced-uncached MMU
 * mapping. Core metadata uses normal C loads/stores on that mapping only;
 * device-visible records use io_map plus explicit physical/bus translations.
 */
#include <linux/errno.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/log2.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/overflow.h>
#include <linux/spinlock.h>
#include <asm/page.h>
#include "om73_sram_backend.h"

enum om73_sram_state { OM73_CLOSED, OM73_OPENING, OM73_ACTIVE, OM73_CLOSING };
struct om73_sram_owned {
 const void *owner;
 void *raw;
 struct om73_sram_allocation allocation;
};

static DEFINE_MUTEX(om73_sram_lifecycle);
static DEFINE_SPINLOCK(om73_sram_lock);
static struct om_sram_core om73_core;
static struct om_sram_contract om73_arena;
static struct om73_sram_owned om73_owned[OM_SRAM_MAX_LIVE];
static enum om73_sram_state om73_state;
static struct resource *om73_lease;
static void __iomem *om73_map;
static u32 om73_generation;

static bool om73_pin_present(const u8 hash[32])
{
 u32 i;
 for (i = 0; i < 32; i++)
  if (hash[i])
   return true;
 return false;
}

static int om73_validate_board(const struct om73_sram_board_contract *board)
{
 const struct om_sram_contract *c;
 u32 i;
 if (!board)
  return -EINVAL;
 c = &board->arena;
 if (c->enabled != 1 || c->reserved_exclusive != 1 || c->complete_occupancy_map != 1 ||
     c->cpu_base != 0x88000000U || c->bus_base != 0x80000000U ||
     c->uncached_base != 0x60000000U || c->total_bytes != 0x80000U ||
     !c->kernel_occupied_end || c->start < c->kernel_occupied_end ||
     c->start >= c->end || c->end > c->total_bytes ||
     !IS_ALIGNED(c->start, PAGE_SIZE) || !IS_ALIGNED(c->end, PAGE_SIZE) ||
     c->noccupied > OM_SRAM_MAX_OCCUPIED ||
     !om73_pin_present(board->kernel_occupancy_sha256) ||
     !om73_pin_present(board->selected_carriers_sha256) ||
     !om73_pin_present(board->complete_writers_map_sha256))
  return -EINVAL;
 for (i = 0; i < c->noccupied; i++) {
  const struct om_sram_range *r = &c->occupied[i];
  if (r->start >= r->end || r->end > c->total_bytes ||
      (c->start < r->end && c->end > r->start))
   return -EINVAL;
 }
 return 0;
}

int om73_sram_acquire(const struct om73_sram_board_contract *board)
{
 struct om_sram_contract arena;
 struct resource *lease;
 void __iomem *mapping;
 unsigned long flags;
 resource_size_t physical, length;
 int error;

 error = om73_validate_board(board);
 if (error)
  return error;
 /* Snapshot the admitted immutable board contract before any resource write. */
 arena = board->arena;
 physical = (resource_size_t)arena.cpu_base + arena.start;
 length = arena.end - arena.start;
 mutex_lock(&om73_sram_lifecycle);
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_state != OM73_CLOSED) {
  spin_unlock_irqrestore(&om73_sram_lock, flags);
  mutex_unlock(&om73_sram_lifecycle);
  return -EBUSY;
 }
 om73_state = OM73_OPENING;
 spin_unlock_irqrestore(&om73_sram_lock, flags);

 /* If built as a module, keep its code/metadata alive for the arena lifetime. */
 if (!try_module_get(THIS_MODULE)) {
  error = -ENODEV;
  goto closed;
 }

 lease = request_mem_region_exclusive(physical, length, "openmitrastar-sram73");
 if (!lease) {
  error = -EBUSY;
  goto unpin_closed;
 }
 mapping = ioremap(physical, length);
 if (!mapping) {
  release_mem_region(physical, length);
  error = -ENOMEM;
  goto unpin_closed;
 }
 /* SRAM is RAM-like memory, never MMIO registers. This is the only __force
  * cast used by the recovered core; no cached/identity alias is dereferenced. */
 error = om_sram_core_init(&om73_core, (__force void *)mapping, length, &arena);
 if (error) {
  iounmap(mapping);
  release_mem_region(physical, length);
  goto unpin_closed;
 }
 spin_lock_irqsave(&om73_sram_lock, flags);
 om73_arena = arena;
 om73_lease = lease;
 om73_map = mapping;
 memset(om73_owned, 0, sizeof(om73_owned));
 om73_state = OM73_ACTIVE;
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 return 0;

unpin_closed:
 module_put(THIS_MODULE);
closed:
 spin_lock_irqsave(&om73_sram_lock, flags);
 om73_state = OM73_CLOSED;
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_acquire);

static struct om73_sram_owned *om73_find_owner(const void *owner)
{
 u32 i;
 for (i = 0; i < OM_SRAM_MAX_LIVE; i++)
  if (om73_owned[i].owner == owner)
   return &om73_owned[i];
 return NULL;
}

int om73_sram_alloc(const void *owner, size_t bytes, unsigned int alignment,
                    struct om73_sram_allocation *out)
{
 struct om73_sram_owned *record = NULL;
 unsigned long flags, raw_address, aligned_address;
 phys_addr_t raw_physical, aligned_physical;
 size_t extent;
 u32 i, offset;
 void *raw;
 int error = -ENOMEM;

 if (!owner || !out || !bytes || !is_power_of_2(alignment) || alignment > PAGE_SIZE)
  return -EINVAL;
 if (check_add_overflow(bytes, (size_t)alignment - 1, &extent) || extent > U32_MAX)
  return -EOVERFLOW;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_state != OM73_ACTIVE) {
  error = -ENODEV;
  goto done;
 }
 if (om73_find_owner(owner)) {
  error = -EBUSY;
  goto done;
 }
 for (i = 0; i < OM_SRAM_MAX_LIVE; i++)
  if (!om73_owned[i].owner) {
   record = &om73_owned[i];
   break;
  }
 if (!record)
  goto done;
 raw = om_sram_core_alloc(&om73_core, extent);
 if (!raw)
  goto done;
 raw_address = (unsigned long)raw;
 raw_physical = (phys_addr_t)om73_arena.cpu_base + om73_arena.start +
                (raw_address - (unsigned long)om73_map);
 aligned_physical = ALIGN(raw_physical, alignment);
 aligned_address = raw_address + (aligned_physical - raw_physical);
 offset = (u32)(aligned_address - (unsigned long)om73_map);
 if (offset > om73_arena.end - om73_arena.start ||
     bytes > om73_arena.end - om73_arena.start - offset) {
  om_sram_core_free(&om73_core, raw);
  error = -EINVAL;
  goto done;
 }
 record->raw = raw;
 record->owner = owner;
 record->allocation.cpu_phys = (phys_addr_t)om73_arena.cpu_base + om73_arena.start + offset;
 record->allocation.bus = (dma_addr_t)om73_arena.bus_base + om73_arena.start + offset;
 record->allocation.io_map = (__force void __iomem *)aligned_address;
 record->allocation.size = bytes;
 record->allocation.extent_offset = (u32)(raw_address - (unsigned long)om73_map);
 record->allocation.extent_bytes = extent;
 if (!++om73_generation)
  ++om73_generation;
 record->allocation.generation = om73_generation;
 *out = record->allocation;
 error = 0;
done:
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_alloc);

int om73_sram_query(const void *owner, struct om73_sram_allocation *out)
{
 struct om73_sram_owned *record;
 unsigned long flags;
 int error = 0;
 if (!owner || !out)
  return -EINVAL;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_state != OM73_ACTIVE)
  error = -ENODEV;
 else if (!(record = om73_find_owner(owner)))
  error = -ENOENT;
 else
  *out = record->allocation;
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_query);

int om73_sram_free(const void *owner)
{
 struct om73_sram_owned *record;
 unsigned long flags;
 int error;
 if (!owner)
  return -EINVAL;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_state != OM73_ACTIVE)
  error = -ENODEV;
 else if (!(record = om73_find_owner(owner)))
  error = -ENOENT;
 else {
  error = om_sram_core_free(&om73_core, record->raw);
  if (!error)
   memset(record, 0, sizeof(*record));
 }
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_free);

int om73_sram_close(void)
{
 void __iomem *mapping;
 resource_size_t physical, length;
 unsigned long flags;
 int error;
 mutex_lock(&om73_sram_lifecycle);
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_state != OM73_ACTIVE) {
  error = -ENODEV;
  goto locked_done;
 }
 error = om_sram_core_close(&om73_core);
 if (error)
  goto locked_done;
 om73_state = OM73_CLOSING;
 mapping = om73_map;
 physical = om73_lease->start;
 length = resource_size(om73_lease);
 spin_unlock_irqrestore(&om73_sram_lock, flags);

 iounmap(mapping);
 release_mem_region(physical, length);
 spin_lock_irqsave(&om73_sram_lock, flags);
 om73_map = NULL;
 om73_lease = NULL;
 memset(&om73_arena, 0, sizeof(om73_arena));
 om73_state = OM73_CLOSED;
locked_done:
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 if (!error)
  module_put(THIS_MODULE);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_close);

/* Built-in provider is preferred. No module_init/module parameters admit an
 * arena; board registration and hardware resource proofs remain separate. */
MODULE_DESCRIPTION("OpenMitraStar typed exclusive SRAM73 backend");
MODULE_LICENSE("GPL");
'''

def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--core',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False)
 for name in ('om_sram_core.c','om_sram_core.h'):
  shutil.copyfile(a.core/name,a.output/name)
 (a.output/'om73_sram_backend.h').write_text(HEADER,newline='\n')
 (a.output/'om73_sram_backend.c').write_text(SOURCE,newline='\n')
 (a.output/'Kbuild').write_text('om73_sram-y := om_sram_core.o om73_sram_backend.o\nobj-m += om73_sram.o\n',newline='\n')
 result={'status':'SOURCE_ONLY_KERNEL_OWNED_TYPED_SRAM73_BACKEND_PENDING_ARC_AND_FIXTURE',
         'hardware_accessed':False,'firmware_eligible':False,'board_registration_present':False,
         'core_parent':str(a.core),'core_parent_result_sha256':sha(a.core/'result.json'),
         'source_files':{p.name:sha(p) for p in a.output.iterdir() if p.is_file()},
         'requirements':['Exclusive page-aligned physical SRAM reservation acquired by compiled immutable board caller',
         'Verified exact kernel/carrier/all-writer occupancy before constructing admission contract',
         'NC mapping accessed as RAM-like SRAM; explicit CPUphysical/bus/IOmap allocation fields',
         'Devices quiesced before allocation free or close; no reset/reload while leases live',
         'No mappedalias virt_to_bus/virt_to_phys/secondioremap or cached alias flush in DMA SRAM branch'],
         'limits':['No automatic board registration, arbitrary moduleparams, DRAM fallback, guessedgap, fullbuild or hardware',
                   'Hash presence is identity validation only; board caller must verify evidence, not set yes flags']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
