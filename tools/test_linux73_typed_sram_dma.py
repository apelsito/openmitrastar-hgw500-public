"""Run actual typed SRAM DMA allocation/free bodies on a 32-bit fake backend.

The fake pool deliberately separates virtual, CPU-physical and bus addresses.
This is a contract fixture, never a hardware mapping or RF test.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRE = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <limits.h>
#define __iomem
#define EXPORT_SYMBOL(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_LICENSE(x)
#define GFP_KERNEL 0
#define DEFINE_SPINLOCK(x) int x
#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);}while(0)
static unsigned warnings;
#define WARN_ON_ONCE(x) ((x)?(++warnings,1):0)
struct list_head{struct list_head*next,*prev;};
#define LIST_HEAD(x) struct list_head x={&x,&x}
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define list_for_each_entry(pos,h,m) for(struct list_head*i=(h)->next;i!=(h)&&((pos)=container_of(i,__typeof__(*(pos)),m),1);i=i->next)
static void list_add(struct list_head*n,struct list_head*h){n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;}
static void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
typedef struct{uint32_t desc_count;void*descs;unsigned long aligned_vdescs,unaligned_vdescs,descs_dma_addr;}aligned_dma_descs;
struct om73_sram_allocation{uint32_t cpu_phys,bus;void*io_map;size_t size;uint32_t extent_offset,extent_bytes,generation;};
#define is_power_of_2(x) ((x)&&!((x)&((x)-1)))
#define check_mul_overflow(a,b,p) __builtin_mul_overflow((a),(b),(p))
#define check_add_overflow(a,b,p) __builtin_add_overflow((a),(b),(p))
static unsigned rec_alloc,rec_free,dram_alloc,dram_free,maps,unmaps,flushes,converts,iozeros,pool_alloc,pool_free;
static unsigned fail_rec,fail_dram,fail_map,fail_free;static int fail_pool;
static void*records[16];static unsigned nr;
static void*kzalloc(size_t n,int f){(void)f;rec_alloc++;if(fail_rec)return NULL;void*p=calloc(1,n);assert(p&&nr<16);records[nr++]=p;return p;}
static void*kmalloc(size_t n,int f){(void)f;dram_alloc++;if(fail_dram)return NULL;assert(n&&n<1048576);void*p=malloc(n);assert(p);return p;}
static void kfree(void*p){if(!p)return;unsigned i;for(i=0;i<nr;i++)if(records[i]==p)break;if(i<nr){rec_free++;records[i]=records[--nr];}else dram_free++;free(p);}
static unsigned long align_val_up(unsigned long x,unsigned long a){return(x+a-1)&~(a-1);}
static unsigned long virt_to_bus(void*p){converts++;return(unsigned long)p;}
static void flush_dcache_range(unsigned long a,unsigned long b){assert(b>=a);flushes++;}
static void*ioremap_nocache(unsigned long p,size_t n){maps++;assert(p&&n);return fail_map?NULL:(void*)p;}
static void iounmap(void*p){assert(p);unmaps++;}
static struct{const void*owner;void*map;struct om73_sram_allocation a;}pool[16];
static unsigned np,generation;static void(*hook)(void);
static int om73_sram_alloc(const void*owner,size_t n,unsigned align,struct om73_sram_allocation*out){
 pool_alloc++;if(fail_pool)return fail_pool;if(align>8192)return-EINVAL;assert(owner&&n&&np<16);
 for(unsigned i=0;i<np;i++)assert(pool[i].owner!=owner);
 unsigned i=np++;pool[i].owner=owner;pool[i].map=malloc(n+3);assert(pool[i].map);
 /* The mapped alias is intentionally unaligned; only bus/physical alignment matters. */
 uint32_t off=(0x12008U+align-1)&~(align-1);
 pool[i].a=(struct om73_sram_allocation){0x88000000U+off,0x80000000U+off,(char*)pool[i].map+1,n,8,n+align-1,++generation};
 *out=pool[i].a;if(hook){void(*h)(void)=hook;hook=NULL;h();}return 0;
}
static int om73_sram_free(const void*owner){
 if(fail_free)return-EINVAL;unsigned i;for(i=0;i<np;i++)if(pool[i].owner==owner)break;
 assert(i<np);pool_free++;free(pool[i].map);pool[i]=pool[--np];return 0;
}
static void memset_io(void*p,int v,size_t n){unsigned i;for(i=0;i<np;i++)if(pool[i].a.io_map==p)break;assert(i<np&&pool[i].a.size==n);iozeros++;memset(p,v,n);}
'''

TEST = r'''
static aligned_dma_descs raced;
static void commit_other_owner(void){assert(!dmautil_aligned_dma_desc_alloc(&raced,20,4,64,true));}
static void reset(void){assert(!nr&&!np&&om_dma_allocations.next==&om_dma_allocations);rec_alloc=rec_free=dram_alloc=dram_free=maps=unmaps=flushes=converts=iozeros=pool_alloc=pool_free=warnings=0;fail_rec=fail_dram=fail_map=fail_free=0;fail_pool=0;hook=NULL;}
int main(void){_Static_assert(sizeof(size_t)==4&&sizeof(unsigned long)==4,"32-bit arithmetic");_Static_assert(sizeof(aligned_dma_descs)==20,"wire ABI");unsigned cases=0;aligned_dma_descs d;
 unsigned bad[][3]={{0,1,8},{1,0,8},{1,1,0},{1,1,3},{UINT_MAX,2,8},{UINT_MAX,1,8}};
 for(unsigned i=0;i<6;i++){reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs before=d;assert(dmautil_aligned_dma_desc_alloc(&d,bad[i][0],bad[i][1],bad[i][2],true)==(i<4?-EINVAL:-EOVERFLOW));assert(!memcmp(&d,&before,sizeof(d))&&!rec_alloc&&!pool_alloc);cases++;}
 reset();assert(dmautil_aligned_dma_desc_alloc(NULL,1,1,8,true)==-EINVAL);cases++;
 for(unsigned power=0;power<14;power++){reset();memset(&d,0,sizeof(d));unsigned a=1U<<power;assert(!dmautil_aligned_dma_desc_alloc(&d,20,8,a,true));assert(np==1&&d.desc_count==8&&!(d.descs_dma_addr&(a-1)));assert(d.descs_dma_addr==pool[0].a.bus&&d.descs_dma_addr!=pool[0].a.cpu_phys&&d.descs==pool[0].a.io_map);assert(!maps&&!unmaps&&!converts&&!flushes&&!dram_alloc&&iozeros==1);aligned_dma_descs before=d;assert(dmautil_aligned_dma_desc_alloc(&d,20,8,a,true)==-EBUSY&&!memcmp(&d,&before,sizeof(d))&&pool_alloc==1);memset(&d,0x5a,sizeof(d));dmautil_aligned_dma_desc_free(&d);aligned_dma_descs zero={0};assert(!memcmp(&d,&zero,sizeof(d))&&!np&&!nr&&pool_free==1&&!unmaps&&!dram_free);dmautil_aligned_dma_desc_free(&d);assert(pool_free==1);cases+=3;}
 for(unsigned i=0;i<4;i++){reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs before=d;fail_rec=i==0;fail_pool=i==1?-ENODEV:i==2?-EBUSY:i==3?-ENOMEM:0;assert(dmautil_aligned_dma_desc_alloc(&d,20,4,64,true)==(i<2?-ENOMEM+i*(ENOMEM-ENODEV):fail_pool));assert(!memcmp(&d,&before,sizeof(d))&&!np&&!nr&&!unmaps&&!converts&&!flushes);cases++;}
 reset();memset(&d,0,sizeof(d));assert(dmautil_aligned_dma_desc_alloc(&d,20,4,16384,true)==-EINVAL&&!np&&!nr);cases++;
 reset();memset(&raced,0,sizeof(raced));hook=commit_other_owner;assert(dmautil_aligned_dma_desc_alloc(&raced,20,4,64,true)==-EBUSY);assert(np==1&&nr==1&&pool_alloc==2&&pool_free==1&&raced.descs==pool[0].a.io_map);dmautil_aligned_dma_desc_free(&raced);assert(!np&&!nr&&pool_free==2&&!unmaps);cases++;
 reset();memset(&d,0,sizeof(d));assert(!dmautil_aligned_dma_desc_alloc(&d,20,4,64,true));const void*quarantined=pool[0].owner;fail_free=1;dmautil_aligned_dma_desc_free(&d);assert(np==1&&nr==1&&warnings==1&&!unmaps&&!dram_free);fail_free=0;assert(!om73_sram_free(quarantined));kfree((void*)quarantined);reset();cases++;
 for(unsigned f=0;f<4;f++){reset();memset(&d,0,sizeof(d));fail_rec=f==1;fail_dram=f==2;fail_map=f==3;int rc=dmautil_aligned_dma_desc_alloc(&d,20,4,32,false);assert(rc==(f?-ENOMEM:0));if(!f){assert(maps==1&&converts==1&&flushes==1&&!pool_alloc&&!iozeros);dmautil_aligned_dma_desc_free(&d);}assert(!nr&&!np&&!pool_free);cases++;}
 reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs before=d;dmautil_aligned_dma_desc_free(&d);assert(!memcmp(&d,&before,sizeof(d))&&!pool_free&&!dram_free);cases++;
 printf("{\"cases\":%u,\"wire_layout_bytes\":20,\"SRAM_generic_mapping_calls\":0}\n",cases);return 0;}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    source = args.candidate / 'source/platform/ruby/dmautil.c'
    text = source.read_text()
    actual = '\n'.join(line for line in text[text.index('#include <qtn/dmautil.h>'):].splitlines()
                       if not line.startswith('#include'))
    fixture = args.output / 'actual-typed-dma.c'
    fixture.write_text(PRE + actual + TEST, newline='\n')
    compiler = ROOT / 'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe'
    binary = args.output / 'fixture.exe'
    run = subprocess.run([str(compiler), '-O1', '-std=gnu11', '-Wall', '-Wextra',
                          str(fixture), '-o', str(binary)], capture_output=True)
    (args.output / 'compile.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    run = subprocess.run([str(binary)], capture_output=True)
    (args.output / 'run.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    result = {'status': 'PASS_ACTUAL_TYPED_SRAM_DMA_OWNER_BUS_MAP_AND_32BIT_BOUNDS_FIXTURE',
              'hardware_accessed': False, 'firmware_eligible': False, **json.loads(run.stdout),
              'pins': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__), source, fixture, compiler, binary)},
              'limits': ['Actual DMA bodies with fake memory/pool/locking/MMIO.',
                         'Virtual/physical/bus aliases differ; SRAM generic mapping/flush paths must not execute.',
                         'No actual SRAM bank reservation, concurrency, hardware reset, or RF acceptance.']}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
