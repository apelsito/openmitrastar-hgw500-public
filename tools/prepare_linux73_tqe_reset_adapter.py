"""Isolated bounded TQE ring pause/reprogram controller; no hooks or MMIO."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
HEADER=r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OM73_TQE_RESET_ADAPTER_H
#define OM73_TQE_RESET_ADAPTER_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/string.h>
#else
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;typedef uint64_t u64;
#endif
/* Register offsets are the actual LHOST CPUIF(num=0), not invented idle bits. */
enum om_tqe_reg { OM_TQE_CSR=0,OM_TQE_RING_SIZE=4,OM_TQE_RING=8,
 OM_TQE_CURPTR=12,OM_TQE_QPTR=20,OM_TQE_TXSTART=56,OM_TQE_STATUS=60 };
struct om_tqe_producer_fence { const void *owner;u64 generation; };
struct om_tqe_ring_identity { const void *allocation_owner;u32 bus,count,bytes,generation; };
struct om_tqe_reset_provider {
 void *context;
 /* Missing real all-producer admission fence deliberately prevents all work.
  * IRQ/NAPI disable is not this fence. No existingR24provider implements it. */
 int(*producer_begin)(void*,struct om_tqe_producer_fence*);
 int(*producer_valid)(void*,const struct om_tqe_producer_fence*);
 int(*producer_end)(void*,const struct om_tqe_producer_fence*);
 int(*ring_identity_valid)(void*,const struct om_tqe_ring_identity*);
 int(*local_stop)(void*); /* TX admission + tasklet + synchronizeIRQ + napi_disable */
 int(*local_resume)(void*);
 u32(*read_reg)(void*,enum om_tqe_reg);
 void(*write_reg)(void*,enum om_tqe_reg,u32);
 void(*poll_delay)(void*);
};
enum om_tqe_reset_phase { OM_TQE_IDLE,OM_TQE_PREPARING,OM_TQE_PAUSED,
 OM_TQE_QUARANTINED };
struct om_tqe_reset_adapter {
 struct om_tqe_producer_fence producer;
 struct om_tqe_ring_identity ring;
 u32 saved_csr,phase,polls;
};
int om_tqe_reset_pause(struct om_tqe_reset_adapter*,const struct om_tqe_ring_identity*,
 const struct om_tqe_reset_provider*,u32 max_polls);
int om_tqe_reset_resume(struct om_tqe_reset_adapter*,const struct om_tqe_reset_provider*);
int om_tqe_reset_local_ready(const struct om_tqe_reset_adapter*,
 const struct om_tqe_reset_provider*);
#endif
'''
SOURCE=r'''/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline-only controller: no default provider, no symbols exported, no source
 * calls attached to R24. Preserves the same ring owner/bus/count across reset.
 * A fullNETSSreset still requires the external exactreset/sharedresource lease,
 * producerstop contract and actualhardware readback; this is only local stage. */
#include "om73_tqe_reset_adapter.h"
#define EINVAL_ 22
#define EBUSY_ 16
#define EIO_ 5
#define EOPNOTSUPP_ 95
#define ETIMEDOUT_ 110
#define IRQ_EN 1U
#define CPUIF_RESET (1U<<31)
#define STATUS_EMPTY (1U<<30)
static int provider_ready(const struct om_tqe_reset_provider*p)
{
 return p&&p->producer_begin&&p->producer_valid&&p->producer_end&&
 p->ring_identity_valid&&p->local_stop&&p->local_resume&&p->read_reg&&p->write_reg;
}
static int fence_valid(const struct om_tqe_reset_adapter*s,
 const struct om_tqe_reset_provider*p)
{
 return s->producer.owner&&s->producer.generation&&
 p->producer_valid(p->context,&s->producer)==1&&
 p->ring_identity_valid(p->context,&s->ring)==1;
}
static int quarantine(struct om_tqe_reset_adapter*s,int error)
{s->phase=OM_TQE_QUARANTINED;return error;}
static int rx_tx_idle(const struct om_tqe_reset_provider*p)
{
 u32 status=p->read_reg(p->context,OM_TQE_STATUS);
 u32 indices=p->read_reg(p->context,OM_TQE_QPTR);
 u32 tx=p->read_reg(p->context,OM_TQE_TXSTART);
 /* QPTR halves include the wrap bit. STATUSavailable is no idle ACK. */
 return(status&STATUS_EMPTY)&&((indices&0xffff)==(indices>>16))&&!(tx&1U);
}
int om_tqe_reset_pause(struct om_tqe_reset_adapter*s,const struct om_tqe_ring_identity*ring,
 const struct om_tqe_reset_provider*p,u32 max_polls)
{
 u32 i,idle=0;
 if(!s||!ring||s->phase!=OM_TQE_IDLE||!ring->allocation_owner||!ring->generation||
 !ring->count||ring->count>0xffff||ring->bytes!=ring->count*16U||(ring->bus&7)||
 ring->bus<0x80012000U||ring->bus>=0x80020000U||
 ring->bytes>0x80020000U-ring->bus||!max_polls||max_polls>4096)return-EINVAL_;
 /* Refuse before any state, register or Linux scheduling mutation. */
 if(!provider_ready(p))return-EOPNOTSUPP_;
 if(p->ring_identity_valid(p->context,ring)!=1)return-EBUSY_;
 memset(s,0,sizeof(*s));s->ring=*ring;
 if(p->producer_begin(p->context,&s->producer)!=1)return-EBUSY_;
 s->phase=OM_TQE_PREPARING;
 if(!fence_valid(s,p))return quarantine(s,-EBUSY_);
 s->saved_csr=p->read_reg(p->context,OM_TQE_CSR);
 if((s->saved_csr&CPUIF_RESET)||p->read_reg(p->context,OM_TQE_RING)!=ring->bus||
 p->read_reg(p->context,OM_TQE_RING_SIZE)!=ring->count)return quarantine(s,-EIO_);
 p->write_reg(p->context,OM_TQE_CSR,s->saved_csr&~IRQ_EN);
 if(p->read_reg(p->context,OM_TQE_CSR)&IRQ_EN)return quarantine(s,-EIO_);
 if(p->local_stop(p->context)!=1)return quarantine(s,-EBUSY_);
 /* A runningNAPIpoll can reenableIRQ on completion; mask againafterdrain. */
 p->write_reg(p->context,OM_TQE_CSR,p->read_reg(p->context,OM_TQE_CSR)&~IRQ_EN);
 if(p->read_reg(p->context,OM_TQE_CSR)&IRQ_EN)return quarantine(s,-EIO_);
 for(i=0;i<max_polls;i++){
  s->polls++;
  if(!fence_valid(s,p))return quarantine(s,-EBUSY_);
  if(rx_tx_idle(p)){if(++idle==2)break;}else idle=0;
  if(p->poll_delay)p->poll_delay(p->context);
 }
 if(idle!=2)return quarantine(s,-ETIMEDOUT_);
 /* Unpublish before CPUIFreset, preservingallocatedmemory and ringcontents.
  * Retainedphysicalproducerfence is essential: writesbeloware notstopproof. */
 p->write_reg(p->context,OM_TQE_RING,0);p->write_reg(p->context,OM_TQE_RING_SIZE,0);
 if(p->read_reg(p->context,OM_TQE_RING)||p->read_reg(p->context,OM_TQE_RING_SIZE))
  return quarantine(s,-EIO_);
 p->write_reg(p->context,OM_TQE_CSR,p->read_reg(p->context,OM_TQE_CSR)|CPUIF_RESET);
 if(!(p->read_reg(p->context,OM_TQE_CSR)&CPUIF_RESET)||!fence_valid(s,p))
  return quarantine(s,-EIO_);
 s->phase=OM_TQE_PAUSED;return 0;
}
int om_tqe_reset_local_ready(const struct om_tqe_reset_adapter*s,
 const struct om_tqe_reset_provider*p)
{
 if(!s||!provider_ready(p)||s->phase!=OM_TQE_PAUSED)return 0;
 return fence_valid(s,p)&&!p->read_reg(p->context,OM_TQE_RING)&&
 !p->read_reg(p->context,OM_TQE_RING_SIZE)&&
 (p->read_reg(p->context,OM_TQE_CSR)&CPUIF_RESET);
}
int om_tqe_reset_resume(struct om_tqe_reset_adapter*s,const struct om_tqe_reset_provider*p)
{
 if(!s||!provider_ready(p)||s->phase!=OM_TQE_PAUSED)return-EINVAL_;
 if(!fence_valid(s,p))return quarantine(s,-EBUSY_);
 /* NETSS mayzero CSR; reassertlocalCPUIFreset before restorerings. Noheapinit. */
 p->write_reg(p->context,OM_TQE_CSR,CPUIF_RESET|(s->saved_csr&~IRQ_EN));
 if(!(p->read_reg(p->context,OM_TQE_CSR)&CPUIF_RESET))return quarantine(s,-EIO_);
 p->write_reg(p->context,OM_TQE_RING,s->ring.bus);
 p->write_reg(p->context,OM_TQE_RING_SIZE,s->ring.count);
 if(p->read_reg(p->context,OM_TQE_RING)!=s->ring.bus||
 p->read_reg(p->context,OM_TQE_RING_SIZE)!=s->ring.count||!fence_valid(s,p))
  return quarantine(s,-EIO_);
 p->write_reg(p->context,OM_TQE_CSR,s->saved_csr&~(IRQ_EN|CPUIF_RESET));
 if(p->read_reg(p->context,OM_TQE_CSR)&(IRQ_EN|CPUIF_RESET))
  return quarantine(s,-EIO_);
 if(p->local_resume(p->context)!=1)return quarantine(s,-EBUSY_);
 p->write_reg(p->context,OM_TQE_CSR,s->saved_csr&~CPUIF_RESET);
 if(p->read_reg(p->context,OM_TQE_CSR)!=(s->saved_csr&~CPUIF_RESET)||
 p->producer_end(p->context,&s->producer)!=1)return quarantine(s,-EIO_);
 memset(s,0,sizeof(*s));return 0;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);(a.output/'om73_tqe_reset_adapter.h').write_text(HEADER);(a.output/'om73_tqe_reset_adapter.c').write_text(SOURCE)
 paths=[Path(__file__),a.candidate/'source/platform/topaz/switch_tqe.c',a.candidate/'source/platform/topaz/topaz_congest_queue.c',a.candidate/'source/qdrv/qdrv_hal.c',ROOT/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h',ROOT/'work/sources/Quantenna-GPL/common/topaz_platform.h'];r={'status':'SOURCE_ONLY_BOUNDED_TQE_LOCAL_PAUSE_REPROGRAM_ADAPTER_MISSING_PRODUCER_FENCE','hardware_accessed':False,'firmware_eligible':False,'R24_source_changed':False,'MMIO_provider_connected':False,'pins':{str(p):sha(p)for p in paths},'sourcefiles':{p.name:sha(p)for p in a.output.iterdir()if p.is_file()},'missing_actual_providers':['ExclusiveadmissionbarrierforLHOSTbank/batch/tasklet producers withallpending/retainedrefproof','AllotheringressproducerstopcontractEMAC/WMAC/MCu/AuC/DSP (IRQmask/NAPI notthisproof)','TypedTQEglobalresetlease preserveslivepoolallocationowner; currentR6emptyarena-onlylease rejectsownedring','RealNETSSresetCSR/ring/readback effects onhardware, status/QPTR/TXSTARTidledoesnotestablishremotequiescence'], 'known_actual_sequence':['R24NAPI mayreenableIRQoncompletion; maskagainafterlocal_stop.','Existingteardown unpublishesringbase/count0 thenCPUIFreset1 beforefree; adapterretainsmemory andonlyreprogramssamebus/count.','R24ARC halreset0x4180NETSS/MAC/BB excludesSRAMbit; NETSSimpactTQEregisterscouldzeroreringstate soresumeprogramsonobservedreset.'], 'limits':['No defaultproducer/MMIOcallback implementation supplied; missingcallbackreturnsEOPNOTSUPPbeforeanymutations.','Controllerlocal_readyisnotpermissionforfullNETSSreset; fullwriter/domain/resourceleaseandphysicalsource contractrequired.','SourcefirststageusesexactR24registermeaning butnoOEMglobalproducerfence recovered; noreset/heapfree/reinit loadeddriverbehavior changed.','NoDTprivate/hardware/TX/flash/calibration ordriveropsacceptance.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
