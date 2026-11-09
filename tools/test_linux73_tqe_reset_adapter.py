"""Actual isolatedTQEringcontroller code withregister/backendfailures; nohardware."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
TEST=r'''#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "om73_tqe_reset_adapter.h"
static unsigned cases,checks;
#define CHECK(x) do{checks++;assert(x);}while(0)
struct hw { u32 r[64],reads,writes,begin,end,stop,resume,delay;u32 fail_begin,fail_valid,fail_identity,fail_stop,fail_resume,fail_end,fail_write,noidle,busy_tx,bad_indices,reenable_after_stop;int owner; };
static int begin(void*x,struct om_tqe_producer_fence*f){struct hw*h=x;h->begin++;if(h->fail_begin)return 0;f->owner=&h->owner;f->generation=1;return 1;}
static int valid(void*x,const struct om_tqe_producer_fence*f){struct hw*h=x;return !h->fail_valid&&f->owner==&h->owner&&f->generation==1;}
static int end(void*x,const struct om_tqe_producer_fence*f){struct hw*h=x;CHECK(valid(x,f));h->end++;return h->fail_end?0:1;}
static int identity(void*x,const struct om_tqe_ring_identity*i){struct hw*h=x;return!h->fail_identity&&i->allocation_owner==&h->owner&&i->bus==0x80012008&&i->count==16&&i->bytes==256&&i->generation==7;}
static int stop(void*x){struct hw*h=x;h->stop++;if(h->reenable_after_stop)h->r[OM_TQE_CSR]|=1;return h->fail_stop?0:1;}
static int resume(void*x){struct hw*h=x;h->resume++;return h->fail_resume?0:1;}
static u32 read_reg(void*x,enum om_tqe_reg r){struct hw*h=x;h->reads++;if(r==OM_TQE_STATUS)return h->noidle?0:1U<<30;if(r==OM_TQE_QPTR)return h->bad_indices?0x00010000:0x12341234;if(r==OM_TQE_TXSTART)return h->busy_tx?1:0;return h->r[r];}
static void write_reg(void*x,enum om_tqe_reg r,u32 value){struct hw*h=x;h->writes++;if(h->fail_write==h->writes)return;h->r[r]=value;}
static void delay(void*x){((struct hw*)x)->delay++;}
static struct om_tqe_reset_provider provider(struct hw*h){return(struct om_tqe_reset_provider){h,begin,valid,end,identity,stop,resume,read_reg,write_reg,delay};}
static struct om_tqe_ring_identity ring(struct hw*h){return(struct om_tqe_ring_identity){&h->owner,0x80012008,16,256,7};}
static void init(struct hw*h){memset(h,0,sizeof(*h));h->r[OM_TQE_CSR]=0x81;h->r[OM_TQE_RING]=0x80012008;h->r[OM_TQE_RING_SIZE]=16;}
int main(void){struct hw h;struct om_tqe_reset_adapter state;init(&h);state=(struct om_tqe_reset_adapter){0};struct om_tqe_ring_identity id=ring(&h);struct om_tqe_reset_provider p=provider(&h);
struct om_tqe_reset_provider absent=p;absent.producer_begin=NULL;CHECK(om_tqe_reset_pause(&state,&id,&absent,16)==-95);CHECK(!h.reads&&!h.writes&&!h.stop&&!h.begin&&state.phase==0);cases++;
for(unsigned i=0;i<6;i++){init(&h);state=(struct om_tqe_reset_adapter){0};id=ring(&h);p=provider(&h);if(i==0)id.bytes=255;if(i==1)id.count=0;if(i==2)id.bus++;if(i==3)id.bus=0x80020000;if(i==4)id.generation=0;if(i==5)id.allocation_owner=NULL;CHECK(om_tqe_reset_pause(&state,&id,&p,16)==-22);CHECK(!h.reads&&!h.writes&&!h.begin);cases++;}
for(unsigned fault=0;fault<8;fault++){init(&h);state=(struct om_tqe_reset_adapter){0};id=ring(&h);p=provider(&h);if(fault==0)h.fail_identity=1;if(fault==1)h.fail_begin=1;if(fault==2)h.fail_valid=1;if(fault==3)h.r[OM_TQE_RING_SIZE]=17;if(fault==4)h.r[OM_TQE_RING]=0x80013000;if(fault==5)h.fail_stop=1;if(fault==6)h.fail_write=1;if(fault==7)h.r[OM_TQE_CSR]|=1U<<31;int rc=om_tqe_reset_pause(&state,&id,&p,16);CHECK(rc<0);CHECK(h.resume==0&&h.end==0);if(fault<2)CHECK(!h.writes);else CHECK(state.phase==OM_TQE_QUARANTINED);CHECK(h.r[OM_TQE_RING]!=(u32)0||fault==4);cases++;}
for(unsigned busy=0;busy<3;busy++){init(&h);state=(struct om_tqe_reset_adapter){0};id=ring(&h);p=provider(&h);h.noidle=busy==0;h.busy_tx=busy==1;h.bad_indices=busy==2;CHECK(om_tqe_reset_pause(&state,&id,&p,4)==-110);CHECK(h.delay==4&&state.polls==4&&state.phase==OM_TQE_QUARANTINED);CHECK(h.r[OM_TQE_RING]==id.bus&&!h.end&&!h.resume);cases++;}
init(&h);state=(struct om_tqe_reset_adapter){0};id=ring(&h);p=provider(&h);h.reenable_after_stop=1;CHECK(!om_tqe_reset_pause(&state,&id,&p,16));CHECK(state.polls==2&&state.phase==OM_TQE_PAUSED&&h.stop==1&&!h.end&&!h.resume);CHECK(!h.r[OM_TQE_RING]&&!h.r[OM_TQE_RING_SIZE]&&(h.r[OM_TQE_CSR]&(1U<<31)));CHECK(om_tqe_reset_local_ready(&state,&p)==1);
/* SimulateNETSS losingCSR/ringregisters, preserveallocatedringidentity. */h.r[OM_TQE_CSR]=0;h.r[OM_TQE_RING]=0;h.r[OM_TQE_RING_SIZE]=0;CHECK(!om_tqe_reset_resume(&state,&p));CHECK(h.r[OM_TQE_RING]==id.bus&&h.r[OM_TQE_RING_SIZE]==id.count&&h.r[OM_TQE_CSR]==0x81&&h.resume==1&&h.end==1&&state.phase==0);cases++;
for(unsigned fail=0;fail<5;fail++){init(&h);state=(struct om_tqe_reset_adapter){0};id=ring(&h);p=provider(&h);CHECK(!om_tqe_reset_pause(&state,&id,&p,8));h.writes=0;h.r[OM_TQE_CSR]=0;if(fail==0)h.fail_valid=1;if(fail==1)h.fail_write=1;if(fail==2)h.fail_write=2;if(fail==3)h.fail_resume=1;if(fail==4)h.fail_end=1;CHECK(om_tqe_reset_resume(&state,&p)<0);CHECK(state.phase==OM_TQE_QUARANTINED);CHECK(state.ring.allocation_owner==&h.owner&&state.ring.bus==id.bus&&state.ring.count==16);cases++;}
printf("{\"actual_controller_cases\":%u,\"checks\":%u,\"MMIO_callbacks_real\":false,\"producer_barrier_real\":false}\n",cases,checks);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);source=a.candidate/'om73_tqe_reset_adapter.c';header=a.candidate/'om73_tqe_reset_adapter.h';f=a.output/'actual-tqe-controller.c';f.write_text(TEST);cc=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe';binary=a.output/'fixture.exe';cmd=[str(cc),'-O1','-std=gnu11','-Wall','-Wextra','-Werror','-I'+str(a.candidate),str(source),str(f),'-o',str(binary)];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(binary)],capture_output=True);(a.output/'run.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(p):sha(p)for p in[Path(__file__),source,header,cc,f,binary]};result={'status':'PASS_ISOLATED_TQE_PAUSE_REPROGRAM_CONTROLLER_FAKEREG_BOUNDED_FAILURE_CASES','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':['ActualcontrollerC only, fakeproducer/localLinux/MMIOreadbacks; noactualNETSSreset orproducerstop.','No defaultproducerfence meansEOPNOTSUPPbeforemutation; realprovider notimplemented orconnected.','Timeouts/mismatch quarantinekeepsringallocationidentity, doesnotfree/reinitSRAM.','Thislocalstageisnotfullresetadmission, norLinuxNAPI/IRQ/TQEhardwareproof.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
