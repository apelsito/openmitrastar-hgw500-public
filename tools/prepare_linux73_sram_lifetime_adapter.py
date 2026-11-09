"""Isolated SRAM lifecycle adapter tied to current reset/ring source events."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
HEADER=r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OM_SRAM_LIFETIME_H
#define OM_SRAM_LIFETIME_H
#include "om_sram_core.h"
#define OM_SRAM_RESET_BIT (1U<<3)
#define OM_NETSS_RESET_BIT (1U<<7)
#define OM_R20_ARC_RESET_MASK ((1U<<7)|(1U<<8)|(1U<<14))
struct om_sram_ring_binding { void *allocation;u32 bus_base,count,descriptor_bytes; };
struct om_sram_lifetime {
 struct om_sram_core *core;
 struct om_sram_contract contract;
 struct om_sram_ring_binding ring;
 u32 generation,pending_reset_mask,reset_asserted,clear_start,clear_end;
};
int om_sram_lifetime_bind(struct om_sram_lifetime *,struct om_sram_core *,
 const struct om_sram_contract *);
void *om_sram_lifetime_alloc(struct om_sram_lifetime *,unsigned long bytes);
int om_sram_lifetime_free(struct om_sram_lifetime *,void *pointer);
int om_sram_ring_published(struct om_sram_lifetime *,void *allocation,
 u32 bus_base,u32 count,u32 descriptor_bytes,u32 observed_base,u32 observed_count);
int om_sram_ring_unpublished(struct om_sram_lifetime *,u32 observed_base,
 u32 observed_count,u32 observed_csr);
int om_sram_reset_prepare(struct om_sram_lifetime *,u32 exact_mask);
int om_sram_reset_asserted(struct om_sram_lifetime *,u32 observed_mask,u32 observed_vector);
int om_sram_reset_released(struct om_sram_lifetime *,u32 observed_mask,u32 observed_vector);
int om_sram_clear_prepare(struct om_sram_lifetime *,u32 host_start,u32 bytes);
int om_sram_clear_complete(struct om_sram_lifetime *,u32 host_start,u32 bytes);
#endif
'''
CORE=r'''/* SPDX-License-Identifier: GPL-2.0-only */
/* Source-only lifecycle bookkeeping. Call before/after exact observed writes;
 * this core neither performs MMIO nor proves a complete firmware writer map.
 * A trusted kernel provider still must own mapping/reservation and serialize
 * these events with allocation/free. No hook is connected to R20 here. */
#include "om_sram_lifetime.h"
#define EINVAL_ 22
#define EBUSY_ 16
#define EOVERFLOW_ 75
static int live_pointer(struct om_sram_lifetime *l,void *p,u32 base,u32 bytes)
{
 u32 i;unsigned long offset,userbytes;
 if(!l||!l->core||!l->core->active||!p)return 0;
 for(i=0;i<OM_SRAM_MAX_LIVE;i++)if(l->core->live[i].pointer==p)break;
 if(i==OM_SRAM_MAX_LIVE)return 0;
 offset=(unsigned char*)p-l->core->begin;
 userbytes=l->core->live[i].bytes-sizeof(struct memblock);
 if(base<l->contract.bus_base+l->contract.start+offset)return 0;
 offset=base-(l->contract.bus_base+l->contract.start+offset);
 return offset<=userbytes&&bytes<=userbytes-offset;
}
int om_sram_lifetime_bind(struct om_sram_lifetime *l,struct om_sram_core *core,
 const struct om_sram_contract *c)
{
 if(!l||!core||!c||!core->active||l->generation||
    c->enabled!=1||c->reserved_exclusive!=1||c->complete_occupancy_map!=1||
    c->start>=c->end||(unsigned long)(core->end-core->begin)!=c->end-c->start)return-EINVAL_;
 memset(l,0,sizeof(*l));l->core=core;l->contract=*c;l->generation=1;return 0;
}
void *om_sram_lifetime_alloc(struct om_sram_lifetime *l,unsigned long bytes)
{
 if(!l||!l->generation||l->pending_reset_mask||l->clear_end)return 0;
 return om_sram_core_alloc(l->core,bytes);
}
int om_sram_lifetime_free(struct om_sram_lifetime *l,void *pointer)
{
 if(!l||!l->generation||l->pending_reset_mask||l->clear_end)return-EINVAL_;
 if(pointer&&l->ring.allocation==pointer)return-EBUSY_;
 return om_sram_core_free(l->core,pointer);
}
int om_sram_ring_published(struct om_sram_lifetime *l,void *allocation,
 u32 bus_base,u32 count,u32 descriptor_bytes,u32 observed_base,u32 observed_count)
{
 u32 bytes;
 if(!l||!l->generation||l->pending_reset_mask||l->clear_end||
    l->ring.allocation||!count||!descriptor_bytes)return-EINVAL_;
 if(count>0xffffffffU/descriptor_bytes)return-EOVERFLOW_;
 bytes=count*descriptor_bytes;
 if(bus_base!=observed_base||count!=observed_count||
    !live_pointer(l,allocation,bus_base,bytes))return-EINVAL_;
 l->ring=(struct om_sram_ring_binding){allocation,bus_base,count,descriptor_bytes};return 0;
}
int om_sram_ring_unpublished(struct om_sram_lifetime *l,u32 base,u32 count,u32 csr)
{
 if(!l||!l->ring.allocation||base||count||!(csr&(1U<<31)))return-EINVAL_;
 memset(&l->ring,0,sizeof(l->ring));return 0;
}
int om_sram_reset_prepare(struct om_sram_lifetime *l,u32 exact_mask)
{
 if(!l||!l->core||!l->core->active||l->pending_reset_mask||l->clear_end)return-EINVAL_;
 /* Only observed R20 ARC mask, optionally SRAM bit for a future exact caller.
  * A domain reset with live owned memory cannot silently orphan consumers. */
 if(exact_mask!=OM_R20_ARC_RESET_MASK&&
    exact_mask!=(OM_R20_ARC_RESET_MASK|OM_SRAM_RESET_BIT))return-EINVAL_;
 if(l->ring.allocation||l->core->live_count)return-EBUSY_;
 if(l->generation==0xffffffffU)return-EOVERFLOW_;
 if(exact_mask&OM_SRAM_RESET_BIT){int rc=om_sram_core_close(l->core);if(rc)return rc;}
 l->pending_reset_mask=exact_mask;l->reset_asserted=0;return 0;
}
int om_sram_reset_asserted(struct om_sram_lifetime *l,u32 mask,u32 vector)
{
 if(!l||!l->pending_reset_mask||mask!=l->pending_reset_mask||
    vector!=l->pending_reset_mask)return-EINVAL_;
 l->reset_asserted=1;return 0;
}
int om_sram_reset_released(struct om_sram_lifetime *l,u32 mask,u32 vector)
{
 u32 destructive;
 if(!l||!l->reset_asserted||mask||vector!=l->pending_reset_mask)return-EINVAL_;
 destructive=l->pending_reset_mask&OM_SRAM_RESET_BIT;
 /* Physical restore must reinit core through its exact mapping/contract first.
  * This function never manufactures that proof from register values. */
 if(destructive&&(!l->core->active||l->core->live_count))return-EBUSY_;
 l->generation++;l->pending_reset_mask=0;l->reset_asserted=0;return 0;
}
int om_sram_clear_prepare(struct om_sram_lifetime *l,u32 host_start,u32 bytes)
{
 u32 start,end;
 if(!l||!l->core||!l->core->active||l->pending_reset_mask||l->clear_end||
    !bytes||host_start<l->contract.cpu_base)return-EINVAL_;
 start=host_start-l->contract.cpu_base;
 if(start>=l->contract.total_bytes||bytes>l->contract.total_bytes-start)return-EINVAL_;
 end=start+bytes;
 /* R20 clearsram ranges >=0x20000 do not overlap proposed12000..20000.
  * Never admit a direct write into the owned heap, even if currently empty. */
 if(start<l->contract.end&&end>l->contract.start)return-EBUSY_;
 l->clear_start=start;l->clear_end=end;return 0;
}
int om_sram_clear_complete(struct om_sram_lifetime *l,u32 host_start,u32 bytes)
{
 if(!l||!l->clear_end||host_start!=l->contract.cpu_base+l->clear_start||
    bytes!=l->clear_end-l->clear_start)return-EINVAL_;
 l->clear_start=l->clear_end=0;return 0;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--core',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 for n in['om_sram_core.c','om_sram_core.h']:shutil.copyfile(a.core/n,a.output/n)
 (a.output/'om_sram_lifetime.h').write_text(HEADER);(a.output/'om_sram_lifetime.c').write_text(CORE)
 paths=[Path(__file__),a.core/'result.json',a.candidate/'source/qdrv/qdrv_hal.c',a.candidate/'source/qdrv/qdrv_soc.c',a.candidate/'source/qdrv/qdrv_control.c',a.candidate/'source/platform/topaz/switch_tqe.c',ROOT/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h',ROOT/'work/sources/Quantenna-GPL/common/ruby_platform.h'];r={'status':'SOURCE_ONLY_SRAM_LIFETIME_ADAPTER_REAL_R20_RESET_RING_CALLSITE_CONTRACT_NOT_CONNECTED','hardware_accessed':False,'firmware_eligible':False,'R20_source_changed':False,'heap_exports_added':False,'pins':{str(p):sha(p)for p in paths},'sourcefiles':{p.name:sha(p)for p in a.output.iterdir()if p.is_file()},'actual_R20_reset_mask':'0x4180 NETSS|MAC|BB noSRAMbit; nonARCbranchcontainsSRAM_RESETbutisnotcompiled','callsite_requirements':['BindreservedkernelheapbeforeTQEdependencyringallocation; allocator cannotreinitafterqdrv_soc_initbecauseTQEalreadyownsring','BeforeNETSSreset: actualunpublishringbase/count0 andCPUIFresetbit31 plusfreeownedallocations; otherwise-resetprepareEBUSY. R20currentlydoesnotperformthisbeforehal_reset.','AfterSRAMbitdestructivereset(ifanyfutureexactcaller): stopcorebeforewrite,explicittrustedmappingcontractreinitafterassert/release; noautomaticreinitfromboolflags.','R20clearsramregions >=20000donottouchheap; adapterrefusesanyoverlap; disjointdirectwritebookkeepingneverclaimsindirectwritersclosed.'],'unknowns':['NETSSreset impact onTQEhardware ring/base registers needsrealRTL/OEM/runtimeevidence; sourceadapterrejectswithliveobjects ratherthanassumesunchanged.','MCu/AuC/DSPindirectwriterboundsandcompleteexclusivekernelmappingstillmissing.','R20hal_disable_auc emptyandDSPdisablecompiledout; stopcannotproveallfirmwarewritersquiet fromthosecalls.','NoQDRVhookintegration/functionalheapprovider untilreservation+writer+reset callsitegates passed.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
