"""Run the actual typed backend/core with fake resource/MMIO and failure gates."""
import argparse, hashlib, json, subprocess
from pathlib import Path

SHIM = r'''
#ifndef OM73_TEST_SHIM
#define OM73_TEST_SHIM
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <limits.h>
#define EINVAL 22
#define EBUSY 16
#define ENODEV 19
#define ENOMEM 12
#define ENOENT 2
#define EOVERFLOW 75
typedef uint8_t u8;
typedef uint32_t u32;
typedef unsigned long phys_addr_t;
typedef unsigned long dma_addr_t;
typedef unsigned long resource_size_t;
#define __iomem
#define __force
#define __KERNEL__
#define U32_MAX UINT32_MAX
#define PAGE_SIZE 8192u
#define IS_ALIGNED(x,a) (!((x)&((a)-1)))
#define ALIGN(x,a) (((x)+((a)-1))&~((__typeof__(x))(a)-1))
#define is_power_of_2(x) ((x)&&!((x)&((x)-1)))
#define check_add_overflow(a,b,p) __builtin_add_overflow(a,b,p)
#define EXPORT_SYMBOL_GPL(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_LICENSE(x)
#define THIS_MODULE ((void *)1)
#define DEFINE_MUTEX(name) int name
#define DEFINE_SPINLOCK(name) int name
static unsigned spin_depth, mutex_depth;
static void lock_spin(int *lock,unsigned long *flags){(void)lock;*flags=0;spin_depth++;}
static void unlock_spin(int *lock,unsigned long flags){(void)lock;(void)flags;assert(spin_depth);spin_depth--;}
#define spin_lock_irqsave(lock,flags) lock_spin((lock),&(flags))
#define spin_unlock_irqrestore(lock,flags) unlock_spin((lock),(flags))
static void mutex_lock(int *lock){(void)lock;assert(!spin_depth);mutex_depth++;}
static void mutex_unlock(int *lock){(void)lock;assert(mutex_depth);mutex_depth--;}
static int module_live,fail_module,fail_resource,fail_mapping;
static unsigned request_calls,release_calls,map_calls,unmap_calls;
static int resource_live,mapping_live;
static unsigned char storage[0x10000] __attribute__((aligned(8192)));
struct resource {resource_size_t start,end;};
static struct resource resource;
static bool try_module_get(void *m){(void)m;assert(!spin_depth);if(fail_module)return false;module_live++;return true;}
static void module_put(void *m){(void)m;assert(!spin_depth);assert(module_live>0);module_live--;}
static struct resource *request_mem_region_exclusive(resource_size_t start,resource_size_t size,const char *name){
 (void)name;assert(!spin_depth);request_calls++;if(fail_resource||resource_live)return NULL;
 assert(start>=0x88000000ul&&start+size<=0x88080000ul);resource=(struct resource){start,start+size-1};resource_live++;return &resource;
}
static void release_mem_region(resource_size_t start,resource_size_t size){assert(!spin_depth);assert(resource_live);assert(start==resource.start&&size==resource.end-resource.start+1);resource_live--;release_calls++;}
static void *ioremap(resource_size_t start,unsigned long size){assert(!spin_depth);assert(resource_live);assert(start==resource.start&&size<=sizeof(storage));map_calls++;if(fail_mapping)return NULL;mapping_live++;return storage;}
static void iounmap(void *p){assert(!spin_depth);assert(p==storage&&mapping_live);mapping_live--;unmap_calls++;}
static resource_size_t resource_size(struct resource *r){return r->end-r->start+1;}
#endif
'''

HARNESS = r'''
static struct om73_sram_board_contract valid(void){
 struct om73_sram_board_contract b={0};
 b.arena=(struct om_sram_contract){.enabled=1,.reserved_exclusive=1,.complete_occupancy_map=1,
 .cpu_base=0x88000000,.bus_base=0x80000000,.uncached_base=0x60000000,.total_bytes=0x80000,
 .start=0x12000,.end=0x14000,.kernel_occupied_end=0x12000};
 b.kernel_occupancy_sha256[0]=1;b.selected_carriers_sha256[0]=2;b.complete_writers_map_sha256[0]=3;return b;
}
static void closed(void){assert(!resource_live&&!mapping_live&&!module_live&&!spin_depth&&!mutex_depth);}
int main(void){
 unsigned cases=0;struct om73_sram_board_contract b=valid(),bad;struct om73_sram_allocation a,q;
 int owner[129];
 memset(storage,0xa5,sizeof(storage));
 assert(om73_sram_alloc(&owner[0],16,16,&a)==-ENODEV);cases++;
 assert(om73_sram_query(&owner[0],&a)==-ENODEV);cases++;
 assert(om73_sram_free(&owner[0])==-ENODEV);cases++;
 assert(om73_sram_close()==-ENODEV);closed();cases++;
 assert(om73_sram_acquire(NULL)==-EINVAL);closed();cases++;
 for(unsigned mode=0;mode<11;mode++){
  bad=b;
  switch(mode){case0:bad.arena.enabled=0;break;case1:bad.arena.reserved_exclusive=0;break;
   case2:bad.arena.complete_occupancy_map=0;break;case3:bad.arena.cpu_base++;break;
   case4:bad.arena.start++;break;case5:bad.arena.end++;break;case6:bad.arena.kernel_occupied_end=0;break;
   case7:bad.arena.occupied[0]=(struct om_sram_range){0x11000,0x13000};bad.arena.noccupied=1;break;
   case8:memset(bad.kernel_occupancy_sha256,0,32);break;
   case9:memset(bad.selected_carriers_sha256,0,32);break;
   case10:memset(bad.complete_writers_map_sha256,0,32);break;}
  assert(om73_sram_acquire(&bad)==-EINVAL);closed();assert(storage[0]==0xa5);cases++;
 }
 fail_module=1;assert(om73_sram_acquire(&b)==-ENODEV);fail_module=0;closed();cases++;
 fail_resource=1;assert(om73_sram_acquire(&b)==-EBUSY);fail_resource=0;closed();cases++;
 fail_mapping=1;assert(om73_sram_acquire(&b)==-ENOMEM);fail_mapping=0;closed();cases++;
 assert(om73_sram_acquire(&b)==0);assert(resource_live&&mapping_live&&module_live);cases++;
 assert(om73_sram_acquire(&b)==-EBUSY);cases++;
 for(unsigned shift=0;shift<=13;shift++){
  unsigned align=1u<<shift;
  int result=om73_sram_alloc(&owner[0],16,align,&a);
  if(align==8192){assert(result==-ENOMEM);cases++;continue;}
  assert(result==0);assert(!(a.cpu_phys&(align-1)));assert(!(a.bus&(align-1)));
  assert(a.bus==a.cpu_phys-0x08000000ul);
  assert((unsigned char *)a.io_map==storage+(a.cpu_phys-0x88012000ul));
  assert(a.size==16&&a.generation);
  assert(om73_sram_query(&owner[0],&q)==0&&!memcmp(&a,&q,sizeof(a)));
  assert(om73_sram_close()==-EBUSY);assert(module_live&&mapping_live&&resource_live);
  assert(om73_sram_alloc(&owner[0],16,align,&q)==-EBUSY);
  assert(om73_sram_free(&owner[0])==0);assert(om73_sram_free(&owner[0])==-ENOENT);cases+=6;
 }
 assert(om73_sram_alloc(NULL,16,16,&a)==-EINVAL);cases++;
 assert(om73_sram_alloc(&owner[0],0,16,&a)==-EINVAL);cases++;
 assert(om73_sram_alloc(&owner[0],16,3,&a)==-EINVAL);cases++;
 assert(om73_sram_alloc(&owner[0],SIZE_MAX,8192,&a)==-EOVERFLOW);cases++;
 for(unsigned i=0;i<128;i++)assert(om73_sram_alloc(&owner[i],1,1,&a)==0);
 assert(om73_sram_alloc(&owner[128],1,1,&a)==-ENOMEM);cases+=129;
 for(unsigned i=0;i<128;i++)assert(om73_sram_free(&owner[i])==0);cases+=128;
 assert(om73_sram_close()==0);closed();cases++;
 assert(release_calls==unmap_calls+1); /* mappingfail released resource only */
 printf("PASS actual backend resource+mapping+ownership cases=%u request=%u release=%u map=%u unmap=%u\n",cases,request_calls,release_calls,map_calls,unmap_calls);
 return 0;
}
'''.replace('case0:', 'case 0:').replace('case1:', 'case 1:').replace('case2:', 'case 2:').replace('case3:', 'case 3:').replace('case4:', 'case 4:').replace('case5:', 'case 5:').replace('case6:', 'case 6:').replace('case7:', 'case 7:').replace('case8:', 'case 8:').replace('case9:', 'case 9:').replace('case10:', 'case 10:')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 inc=a.output/'include'
 for name in ('linux/types.h','linux/string.h','linux/ioport.h','linux/errno.h','linux/io.h','linux/log2.h','linux/module.h','linux/mutex.h','linux/overflow.h','linux/spinlock.h','asm/page.h'):
  file=inc/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('/* Fake resource/MMIO adapter only. */\n')
 (a.output/'shim.h').write_text(SHIM);fixture=a.output/'fixture.c';fixture.write_text('#include "'+str((a.source/'om_sram_core.c').resolve())+'"\n#include "'+str((a.source/'om73_sram_backend.c').resolve())+'"\n'+HARNESS)
 binary=a.output/'fixture';command=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(inc.resolve()),'-include',str((a.output/'shim.h').resolve()),str(fixture.resolve()),'-o',str(binary.resolve())]
 r=subprocess.run(command,capture_output=True,text=True);(a.output/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
 r=subprocess.run([str(binary.resolve())],capture_output=True,text=True);(a.output/'run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 result={'status':'PASS_ACTUAL_OEM_CORE_TYPED_SRAM_BACKEND_FAKE_RESOURCE_MAPPING_OWNERSHIP','source_sha256':sha(a.source/'om73_sram_backend.c'),'core_sha256':sha(a.source/'om_sram_core.c'),'output':r.stdout.strip(),'command':command,'hardware_accessed':False,'firmware_eligible':False,'limits':'Host pointer-size fixture; real ARCcompile and earlier coreARC32fixtures separate. Fake SRAM does not prove physicalbusmapping.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
