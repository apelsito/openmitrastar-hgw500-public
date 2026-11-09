"""Actual R20 DMA allocator/free on32bit host withownedheap/map failures."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);src=a.candidate/'source/platform/ruby/dmautil.c';raw=src.read_text();actual='\n'.join(l for l in raw[raw.index('#include <qtn/dmautil.h>'):].splitlines()if not l.startswith('#include'))
 pre=r'''#include <stdint.h>
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
#define pr_info(...) ((void)0)
#define DEFINE_SPINLOCK(x) int x
#define spin_lock_irqsave(lock,flags) do{(void)(lock);(flags)=0;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);}while(0)
struct list_head{struct list_head*next,*prev;};
#define LIST_HEAD(x) struct list_head x={&x,&x}
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define list_for_each_entry(pos,head,member) for(struct list_head*it=(head)->next;it!=(head)&&((pos)=container_of(it,__typeof__(*(pos)),member),1);it=it->next)
static void list_add(struct list_head*n,struct list_head*h){n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;}
static void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
typedef struct {uint32_t desc_count;void*descs;unsigned long aligned_vdescs,unaligned_vdescs,descs_dma_addr;}aligned_dma_descs;
#define is_power_of_2(x) ((x)&&!((x)&((x)-1)))
#define check_mul_overflow(a,b,p) __builtin_mul_overflow((a),(b),(p))
#define check_add_overflow(a,b,p) __builtin_add_overflow((a),(b),(p))
static unsigned recordallocs,recordfrees,rawallocs,rawfrees,heapallocs,heapfrees,maps,unmaps;
static unsigned fail_record,fail_raw,fail_map;static void*record_ptrs[16];static unsigned nrecords;
static void*kzalloc(size_t n,int f){(void)f;recordallocs++;if(fail_record)return NULL;void*p=calloc(1,n);assert(p&&nrecords<16);record_ptrs[nrecords++]=p;return p;}
static void*kmalloc(size_t n,int f){(void)f;rawallocs++;if(fail_raw)return NULL;assert(n&&n<1048576);void*p=malloc(n);assert(p);return p;}
static void kfree(void*p){if(!p)return;unsigned i;for(i=0;i<nrecords;i++)if(record_ptrs[i]==p)break;if(i<nrecords){recordfrees++;record_ptrs[i]=record_ptrs[--nrecords];}else rawfrees++;free(p);}
static void*heap_sram_alloc(size_t n){heapallocs++;if(fail_raw)return NULL;assert(n&&n<1048576);void*p=malloc(n);assert(p);return p;}
static void heap_sram_free(void*p){assert(p);heapfrees++;free(p);}
static unsigned long align_val_up(unsigned long a,unsigned long b){return(a+b-1)&~(b-1);}
static unsigned long virt_to_bus(void*p){return(unsigned long)p;}
static void flush_dcache_range(unsigned long a,unsigned long b){assert(b>=a);}
static void iounmap(void*p){assert(p);unmaps++;}
static void inject_owner(void);static unsigned inject;static aligned_dma_descs*current_owner;
static void*ioremap_nocache(unsigned long a,size_t n){maps++;assert(a&&n);if(inject){inject=0;inject_owner();}return fail_map?NULL:(void*)a;}
'''
 test=r'''static void inject_owner(void){struct om_dma_allocation*r=kzalloc(sizeof(*r),0);r->owner=current_owner;r->raw=kmalloc(64,0);r->mapped=r->raw;current_owner->descs=r->mapped;current_owner->unaligned_vdescs=(unsigned long)r->raw;current_owner->aligned_vdescs=(unsigned long)r->raw;current_owner->desc_count=2;list_add(&r->link,&om_dma_allocations);}
static void reset(void){assert(om_dma_allocations.next==&om_dma_allocations&&!nrecords);recordallocs=recordfrees=rawallocs=rawfrees=heapallocs=heapfrees=maps=unmaps=0;fail_record=fail_raw=fail_map=inject=0;}
int main(void){_Static_assert(sizeof(size_t)==4&&sizeof(unsigned long)==4,"32bit size overflow");_Static_assert(sizeof(aligned_dma_descs)==20,"unchangedpubliclayout");unsigned cases=0;aligned_dma_descs d;unsigned dims[][3]={{0,1,4},{1,0,4},{1,1,0},{1,1,3},{UINT_MAX,2,4},{UINT_MAX,1,2},{1,UINT_MAX,8}};
for(unsigned i=0;i<7;i++){reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs snap=d;int rc=dmautil_aligned_dma_desc_alloc(&d,dims[i][0],dims[i][1],dims[i][2],0);assert(rc==(i<4?-EINVAL:-EOVERFLOW)&&!memcmp(&d,&snap,sizeof(d))&&!recordallocs&&!rawallocs&&!maps);cases++;}reset();assert(dmautil_aligned_dma_desc_alloc(NULL,1,1,4,0)==-EINVAL&&!recordallocs);cases++;
for(unsigned backend=0;backend<2;backend++)for(unsigned failure=0;failure<4;failure++){reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs snap=d;fail_record=failure==1;fail_raw=failure==2;fail_map=failure==3;int rc=dmautil_aligned_dma_desc_alloc(&d,20,4,32,backend);if(failure){assert(rc==-ENOMEM&&!memcmp(&d,&snap,sizeof(d)));assert(!nrecords&&om_dma_allocations.next==&om_dma_allocations);if(failure==3)assert((backend?heapfrees:rawfrees)==1&&!unmaps);}else{assert(!rc&&d.desc_count==4&&!(d.aligned_vdescs&31)&&maps==1);assert(backend?heapallocs==1:rawallocs==1);unsigned before=recordallocs;aligned_dma_descs exact=d;assert(dmautil_aligned_dma_desc_alloc(&d,20,4,32,backend)==-EBUSY&&recordallocs==before&&!memcmp(&exact,&d,sizeof(d)));memset(&d,0x5a,sizeof(d));dmautil_aligned_dma_desc_free(&d);aligned_dma_descs zero={0};assert(!memcmp(&d,&zero,sizeof(d))&&unmaps==1&&(backend?heapfrees:rawfrees)==1&&recordfrees==1);dmautil_aligned_dma_desc_free(&d);assert(unmaps==1&&recordfrees==1);}cases++;}
reset();memset(&d,0xa5,sizeof(d));aligned_dma_descs snap=d;dmautil_aligned_dma_desc_free(&d);assert(!memcmp(&d,&snap,sizeof(d))&&!rawfrees&&!heapfrees&&!unmaps);dmautil_aligned_dma_desc_free(NULL);cases++;
reset();memset(&d,0,sizeof(d));current_owner=&d;inject=1;assert(dmautil_aligned_dma_desc_alloc(&d,16,4,16,0)==-EBUSY);assert(d.desc_count==2&&recordallocs==2&&recordfrees==1&&rawallocs==2&&rawfrees==1&&unmaps==1);dmautil_aligned_dma_desc_free(&d);assert(recordfrees==2&&rawfrees==2&&unmaps==2&&!nrecords);cases++;
for(unsigned backend=0;backend<2;backend++)for(unsigned power=0;power<12;power++){reset();memset(&d,0,sizeof(d));unsigned align=1U<<power;assert(!dmautil_aligned_dma_desc_alloc(&d,16,3,align,backend)&&!(d.aligned_vdescs&(align-1)));dmautil_aligned_dma_desc_free(&d);assert(unmaps==1&&(backend?heapfrees:rawfrees)==1);cases++;}reset();printf("{\"actual_DMA_cases\":%u,\"public_layout_bytes\":20}\n",cases);return 0;}
''';f=a.output/'actual-dma.c';f.write_text(pre+actual+test);compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe';r=subprocess.run([str(compiler),'-O1','-std=gnu11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(x):sha(x)for x in[Path(__file__),src,compiler,f,a.output/'fixture.exe']};r={'status':'PASS_R20_ACTUAL_DMA_ALLOCATION_FREE_BOUNDS_BACKEND_AND_DUPLICATE_OWNER_32BIT_FIXTURE','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':'ActualDMAcontroller/body, hostheap/map/spinlocks fakes; 32bitmul/addoverflow&typedpubliclayout tested. NoARCphysicalbus/MMIO/MuCtiming or concurrentrealcaller proof.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
