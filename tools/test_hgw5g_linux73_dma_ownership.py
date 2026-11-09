"""Execute selected actual DMA source against fake alloc/MMIO ownership providers."""
import argparse, hashlib, json, subprocess
from pathlib import Path

SHIM = r'''
#ifndef OM_DMA_FIXTURE_H
#define OM_DMA_FIXTURE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <stdio.h>
#define __iomem
#define GFP_KERNEL 0
#define EXPORT_SYMBOL(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_LICENSE(x)
#define DEFINE_SPINLOCK(x) int x
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags))
#define check_mul_overflow(a,b,p) __builtin_mul_overflow((a),(b),(p))
#define check_add_overflow(a,b,p) __builtin_add_overflow((a),(b),(p))
#define is_power_of_2(x) ((x) && !((x)&((x)-1)))
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(name) struct list_head name={&name,&name}
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define list_for_each_entry(pos,head,member) \
 for(struct list_head *fixture_it=(head)->next; \
 fixture_it!=(head) && (((pos)=container_of(fixture_it,__typeof__(*(pos)),member)),1); \
 fixture_it=fixture_it->next)
static void list_add(struct list_head *n,struct list_head *head){n->next=head->next;n->prev=head;head->next->prev=n;head->next=n;}
static void list_del(struct list_head *n){n->next->prev=n->prev;n->prev->next=n->next;}
typedef struct {uint32_t desc_count;void *descs;unsigned long aligned_vdescs,unaligned_vdescs,descs_dma_addr;} aligned_dma_descs;
static int fail_record,fail_raw,fail_map,record_live,raw_live,mapping_live,dram_free,sram_free,unmaps;
static void (*fixture_hook)(void);
static void *kzalloc(size_t n,int g){(void)g;if(fail_record){fail_record=0;return NULL;}void *p=calloc(1,n);if(p)record_live++;return p;}
static void *kmalloc(size_t n,int g){(void)g;if(fail_raw){fail_raw=0;return NULL;}if(n>1048576)return NULL;void *p=malloc(n);if(p)raw_live++;if(fixture_hook){void(*h)(void)=fixture_hook;fixture_hook=NULL;h();}return p;}
static void *heap_sram_alloc(unsigned long n){return kmalloc(n,0);}
static void heap_sram_free(void *p){if(p){sram_free++;raw_live--;free(p);}}
/* Determine record-vs-raw by size tracked using list member containment test. */
static void *record_ptrs[64];
static unsigned record_count;
static void *fixture_record_alloc(size_t n,int g){void *p=kzalloc(n,g);if(p){assert(record_count<64);record_ptrs[record_count++]=p;}return p;}
#define kzalloc fixture_record_alloc
static void kfree(void *p){if(!p)return;for(unsigned i=0;i<record_count;i++){if(record_ptrs[i]==p){record_ptrs[i]=NULL;record_live--;free(p);return;}}dram_free++;raw_live--;free(p);}
static void *ioremap_nocache(unsigned long a,size_t n){(void)a;if(fail_map){fail_map=0;return NULL;}void *p=calloc(1,n);if(p)mapping_live++;return p;}
static void iounmap(void *p){assert(p);unmaps++;mapping_live--;free(p);}
static void flush_dcache_range(unsigned long a,unsigned long b){assert(b>=a);}
static unsigned long align_val_up(unsigned long a,unsigned long align){return (a+align-1)&~(align-1);}
static unsigned long virt_to_bus(void *p){return (unsigned long)p;}
#endif
'''

HARNESS = r'''
static aligned_dma_descs race_owner;
static void publish_second_owner(void){assert(dmautil_aligned_dma_desc_alloc(&race_owner,16,4,32,false)==0);}
static void balanced(void){assert(record_live==0&&raw_live==0&&mapping_live==0);}
int main(void){
 unsigned cases=0;aligned_dma_descs d={0},unknown={0};
 assert(dmautil_aligned_dma_desc_alloc(NULL,16,4,32,false)==-EINVAL);cases++;
 assert(dmautil_aligned_dma_desc_alloc(&d,0,4,32,false)==-EINVAL);cases++;
 assert(dmautil_aligned_dma_desc_alloc(&d,16,0,32,false)==-EINVAL);cases++;
 for(unsigned a=0;a<31;a++){if(a&&(a&(a-1))==0)continue;assert(dmautil_aligned_dma_desc_alloc(&d,16,4,a,false)==-EINVAL);cases++;}
 for(unsigned backend=0;backend<2;backend++){
  for(unsigned shift=0;shift<8;shift++){
   unsigned a=1u<<shift;
   assert(dmautil_aligned_dma_desc_alloc(&d,16,4,a,backend)==0);
   assert(d.desc_count==4&&d.descs&&!(d.aligned_vdescs&(a-1)));
   aligned_dma_descs before=d;
   assert(dmautil_aligned_dma_desc_alloc(&d,16,4,a,backend)==-EBUSY);
   assert(!memcmp(&before,&d,sizeof(d)));
   /* Free uses the private record despite all public pointer fields corrupted. */
   memset(&d,0xa5,sizeof(d));
   dmautil_aligned_dma_desc_free(&d);balanced();
   assert(d.descs==NULL&&d.unaligned_vdescs==0);
   int frees=dram_free+sram_free;
   dmautil_aligned_dma_desc_free(&d);assert(frees==dram_free+sram_free);balanced();cases+=4;
  }
  for(unsigned stage=0;stage<3;stage++){
   if(stage==0)fail_record=1;if(stage==1)fail_raw=1;if(stage==2)fail_map=1;
   d=(aligned_dma_descs){0};
   assert(dmautil_aligned_dma_desc_alloc(&d,16,4,32,backend)==-ENOMEM);
   assert(!d.descs&&!d.unaligned_vdescs);balanced();cases++;
  }
 }
 unknown.unaligned_vdescs=1;unknown.descs=(void *)2;
 dmautil_aligned_dma_desc_free(&unknown);balanced();assert(unknown.unaligned_vdescs==1);cases++;
 dmautil_aligned_dma_desc_free(NULL);balanced();cases++;
 fixture_hook=publish_second_owner;
 assert(dmautil_aligned_dma_desc_alloc(&race_owner,16,4,32,true)==-EBUSY);
 assert(record_live==1&&raw_live==1&&mapping_live==1);
 dmautil_aligned_dma_desc_free(&race_owner);balanced();cases++;
 printf("PASS actual source ownership cases=%u dram_free=%d sram_free=%d unmaps=%d\n",cases,dram_free,sram_free,unmaps);
 return 0;
}
'''

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source=args.candidate/'source/platform/ruby/dmautil.c'
    include=args.output/'include'
    for name in ('qtn/dmautil.h','linux/module.h','linux/slab.h','linux/list.h','linux/spinlock.h',
                 'linux/overflow.h','linux/log2.h','asm/io.h','asm/cacheflush.h'):
        path=include/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('/* fake ownership/MMIO provider */\n')
    shim=args.output/'shim.h';shim.write_text(SHIM)
    harness=args.output/'fixture.c';harness.write_text('#include "'+str(source.resolve())+'"\n'+HARNESS)
    binary=args.output/'fixture'
    command=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
             '-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(include.resolve()),
             '-include',str(shim.resolve()),str(harness.resolve()),'-o',str(binary.resolve())]
    compile_result=subprocess.run(command,capture_output=True,text=True)
    (args.output/'compile.log').write_text(compile_result.stdout+compile_result.stderr)
    assert compile_result.returncode==0,compile_result.stderr
    result=subprocess.run([str(binary.resolve())],capture_output=True,text=True)
    (args.output/'run.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stderr
    proof={'status':'PASS_ACTUAL_DMA_SOURCE_HOST_OWNERSHIP_FIXTURE',
           'source_sha256':sha(source),'compile_argv':command,'output':result.stdout.strip(),
           'target_arithmetic_scope':'Host size_t; independent ARC32 bounds fixture required',
           'hardware_accessed':False,'MMIO_emulated':True,'firmware_eligible':False}
    (args.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

if __name__=='__main__':main()
