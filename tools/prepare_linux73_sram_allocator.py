"""Prepare offline SRAM allocator core, derived from OEM first-fit/coalescing.
No heap_sram exports, module init, MMIO, DT mutation or driver replacement.
"""
import argparse,hashlib,json,difflib
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
HEADER=r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OM_SRAM_CORE_H
#define OM_SRAM_CORE_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/string.h>
#else
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint32_t u32;
#endif
#define OM_SRAM_MAX_LIVE 128
#define OM_SRAM_MAX_OCCUPIED 16
struct om_sram_range { u32 start,end; }; /* offsets in the same physical SRAM */
struct om_sram_contract {
 u32 enabled,reserved_exclusive,complete_occupancy_map;
 u32 cpu_base,bus_base,uncached_base,total_bytes;
 u32 start,end,kernel_occupied_end,noccupied;
 struct om_sram_range occupied[OM_SRAM_MAX_OCCUPIED];
};
struct memblock { struct memblock *next; unsigned long length; };
struct om_sram_live { void *pointer; unsigned long bytes; };
struct om_sram_core {
 struct memblock memlist;
 unsigned char *begin,*end;
 struct om_sram_live live[OM_SRAM_MAX_LIVE];
 u32 active,live_count;
};
int om_sram_core_init(struct om_sram_core *,void *mapped,u32 mapped_bytes,
 const struct om_sram_contract *);
void *om_sram_core_alloc(struct om_sram_core *,unsigned long bytes);
int om_sram_core_free(struct om_sram_core *,void *pointer);
int om_sram_core_close(struct om_sram_core *);
#endif
'''
PREFIX=r'''/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline core: OEM2.6.35 qtn_memget/free first-fit split/coalescing derived
 * here; caller must serialize init/alloc/free/close. No hardware provider exists.
 * Admission requires an exclusive kernel reservation and a complete occupied
 * region map. User module parameters must never stand in for those proofs. */
#include "om_sram_core.h"
#define OM_EINVAL 22
#define OM_EBUSY 16
#define OM_ENOENT 2
#define OM_EOVERFLOW 75
#define OM_ENOSPC 28
#define roundmb(x) ((void *)((7UL+(unsigned long)(x))&~7UL))

int om_sram_core_init(struct om_sram_core *core,void *mapped,u32 mapped_bytes,
 const struct om_sram_contract *c)
{
 unsigned long p=(unsigned long)mapped;
 u32 i;
 if(!core||!c||!mapped)return-OM_EINVAL;
 if(core->active||core->live_count)return-OM_EBUSY;
 if(c->enabled!=1||c->reserved_exclusive!=1||c->complete_occupancy_map!=1)
  return-OM_EINVAL;
 /* The observed Linux/OEM flip mapping is the only prototype profile. */
 if(c->cpu_base!=0x88000000U||c->bus_base!=0x80000000U||
    c->uncached_base!=0x60000000U||c->total_bytes!=0x80000U)
  return-OM_EINVAL;
 if(!c->kernel_occupied_end||c->noccupied>OM_SRAM_MAX_OCCUPIED||
    c->start<c->kernel_occupied_end||c->start>=c->end||c->end>c->total_bytes||
    (c->start&7)||(c->end&7)||c->end-c->start<sizeof(struct memblock)||
    mapped_bytes!=c->end-c->start||(p&7)||p>~0UL-mapped_bytes)
  return-OM_EINVAL;
 for(i=0;i<c->noccupied;i++){
  if(c->occupied[i].start>=c->occupied[i].end||
     c->occupied[i].end>c->total_bytes)return-OM_EINVAL;
  if(c->start<c->occupied[i].end&&c->end>c->occupied[i].start)
   return-OM_EINVAL;
 }
 memset(core,0,sizeof(*core));core->begin=mapped;core->end=core->begin+mapped_bytes;
 core->memlist.next=(struct memblock*)mapped;core->memlist.length=mapped_bytes;
 core->memlist.next->next=0;core->memlist.next->length=mapped_bytes;
 core->active=1;return 0;
}
'''
SUFFIX=r'''
void *om_sram_core_alloc(struct om_sram_core *core,unsigned long bytes)
{
 struct memblock *block;unsigned long n;u32 slot;
 if(!core||!core->active||!bytes||bytes>~0UL-sizeof(*block)-7)return 0;
 for(slot=0;slot<OM_SRAM_MAX_LIVE;slot++)if(!core->live[slot].pointer)break;
 if(slot==OM_SRAM_MAX_LIVE)return 0;
 n=(bytes+sizeof(*block)+7)&~7UL;
 block=om_sram_memget(core,n);if(!block)return 0;
 block->next=block;block->length=n;
 core->live[slot].pointer=block+1;core->live[slot].bytes=n;core->live_count++;
 return block+1;
}
int om_sram_core_free(struct om_sram_core *core,void *pointer)
{
 struct memblock *block;u32 slot;unsigned long n;
 if(!core||!core->active)return-OM_EINVAL;
 if(!pointer)return 0;
 /* Match owned identity before reading any caller-supplied address. */
 for(slot=0;slot<OM_SRAM_MAX_LIVE;slot++)if(core->live[slot].pointer==pointer)break;
 if(slot==OM_SRAM_MAX_LIVE)return-OM_ENOENT;
 block=(struct memblock*)pointer-1;n=core->live[slot].bytes;
 if((unsigned char*)block<core->begin||(unsigned char*)block>=core->end||
    n>(unsigned long)(core->end-(unsigned char*)block)||
    block->next!=block||block->length!=n)return-OM_EINVAL;
 if(om_sram_memfree(core,block,n))return-OM_EINVAL;
 core->live[slot].pointer=0;core->live[slot].bytes=0;core->live_count--;return 0;
}
int om_sram_core_close(struct om_sram_core *core)
{
 if(!core||!core->active)return-OM_EINVAL;
 if(core->live_count)return-OM_EBUSY;
 memset(core,0,sizeof(*core));return 0;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'work/sources/Quantenna-GPL/linux_2.6.35.12/arch/arc/kernel/module.c';text=original.read_text();get=function(text,'static void *qtn_memget(');free=function(text,'static int qtn_memfree(')
 (a.output/'oem-qtn_memget.c').write_text(get+'\n');(a.output/'oem-qtn_memfree.c').write_text(free+'\n')
 transformed=[]
 for body,isget in[(get,True),(free,False)]:
  body=body.replace('qtn_memget(unsigned long nbytes)','om_sram_memget(struct om_sram_core *core,unsigned long nbytes)').replace('qtn_memfree(void *memptr, unsigned long nbytes)','om_sram_memfree(struct om_sram_core *core,void *memptr, unsigned long nbytes)').replace('&s_memlist','&core->memlist').replace('\tunsigned long flags;\n','').replace('\tspin_lock_irqsave(&s_heap_lock, flags);\n','').replace('\tspin_unlock_irqrestore(&s_heap_lock, flags);\n','')
  # Caller serialization replaces OEMglobalspinlock; core scoped independentheap.
  if not isget:body=body.replace('if(((unsigned long) block + block->length) == (unsigned long) next)','if(next && ((unsigned long) block + block->length) == (unsigned long) next)')
  transformed.append(body)
 (a.output/'om_sram_core.h').write_text(HEADER);(a.output/'om_sram_core.c').write_text(PREFIX+'\n\n'.join(transformed)+SUFFIX)
 patch=[]
 for name,old,new in[('qtn_memget',get,transformed[0]),('qtn_memfree',free,transformed[1])]:patch+=list(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='OEM/'+name,tofile='prototype/'+name))
 (a.output/'oem-core-adaptation.patch').write_text(''.join(patch));paths=[Path(__file__),original,ROOT/'work/sources/Quantenna-GPL/linux_2.6.35.12/arch/arc/kernel/vmlinux.lds.S',ROOT/'work/sources/Quantenna-GPL/common/ruby_mem.h',ROOT/'work/sources/Quantenna-GPL/common/common_mem.h',ROOT/'work/sources/Quantenna-GPL/common/topaz_config.h'];r={'status':'SOURCE_ONLY_OEM_DERIVED_SRAM_CORE_EXPLICIT_RESERVATION_REQUIRED_NOT_DRIVER_PROVIDER','hardware_accessed':False,'firmware_eligible':False,'heap_sram_export_added':False,'pins':{str(p):sha(p)for p in paths},'source_files':{p.name:sha(p)for p in a.output.iterdir()if p.is_file()},'missing_promotion_inputs':['Linux73kerneloccupiedSRAMend equivalentto__sram_end with linker/runtime provenance','completeHBM/FWT/MuC/AuC/DSP/crumbs/Qmatrix SRAMoccupiedmap for exactfirmware/mapprofile','exclusivekernelreservation+safeCPU/bus/uncachedmapping witness for proposedgap','pairedfullkernel/providerbuild andphysicalbus/cache/ownership acceptance'],'limits':['Coreonly, noMMIO/moduleinit/heap_sramexports/currentdriverchanges. Defaultcontractdisabledrefuseswithouttouchingmappedarena.','Firstfit/split/coalescebodyderivedfromOEM; bounded128liveallocledger andcallerperspanserializationnew constraints.','Noarbitraryusersuppliedmoduleparams mayauthorizephysicalSRAM; reservation/mapkernelprovider ismissing.','NoDRAMsubstitution/vehicle/routeraccess/TX/flash/DTprivate orsecretdata.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
