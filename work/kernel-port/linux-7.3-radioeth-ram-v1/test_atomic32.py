"""Compile actual helper loops with a host CAS backend and ARC syscall backend."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 source=(HERE/'arc750_atomic32.c').read_text()
 # Rename exported test symbols so host libc keeps its real atomic runtime.
 tested=source.replace('__asm__("__atomic_fetch_and_4")','').replace('__asm__("__atomic_fetch_or_4")','').replace('__asm__("__atomic_exchange_4")','')
 backend=r'''
#include <stdint.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#define OM_ATOMIC_HOST_TEST
typedef unsigned int u32;
static unsigned checks;
#define CHECK(c) do{checks++;if(!(c)){fprintf(stderr,"FAIL %u\n",__LINE__);exit(1);}}while(0)
static void full_barrier(void){atomic_thread_fence(memory_order_seq_cst);}
static u32 atomic_load32(volatile u32 *p){return atomic_load((_Atomic u32*)p);}
static u32 cmpxchg32(volatile u32 *p,u32 expected,u32 desired){atomic_compare_exchange_strong((_Atomic u32*)p,&expected,desired);return expected;}
'''
 tests=r'''
static _Atomic u32 shared;
static void *worker(void *arg){unsigned mask=1U<<(uintptr_t)arg;for(unsigned i=0;i<20000;i++)om_fetch_or32(&shared,mask,5);return NULL;}
int main(void){
 for(unsigned model=0;model<6;model++)for(unsigned i=0;i<10000;i++){
  _Atomic u32 value=i*7919U, initial=value,mask=i*3571U;
  CHECK(om_fetch_or32(&value,mask,model)==initial);CHECK(value==(initial|mask));
  initial=value;CHECK(om_fetch_and32(&value,~mask,model)==initial);CHECK(value==(initial&~mask));
  initial=value;CHECK(om_exchange32(&value,mask,model)==initial);CHECK(value==mask);
 }
 pthread_t threads[16];shared=0;
 for(uintptr_t i=0;i<16;i++)CHECK(!pthread_create(&threads[i],NULL,worker,(void*)i));
 for(unsigned i=0;i<16;i++)CHECK(!pthread_join(threads[i],NULL));
 CHECK(shared==65535);printf("ATOMIC32_PASS checks=%u concurrent_operations=320000\n",checks);return 0;
}
'''
 fixture=a.output/'fixture.c';fixture.write_text(backend+tested+tests)
 subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=undefined',str(fixture),'-o',str(a.output/'fixture')],check=True)
 r=subprocess.run([str(a.output/'fixture')],capture_output=True,check=True)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');obj=a.output/'arc750_atomic32.o'
 subprocess.run([tc+'gcc','-std=gnu11','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-Os','-fPIC','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-c',str(HERE/'arc750_atomic32.c'),'-o',str(obj)],check=True)
 asm=subprocess.check_output([tc+'objdump','-d',str(obj)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
 assert not subprocess.check_output([tc+'nm','-u',str(obj)],text=True).strip()
 for name in ['__atomic_fetch_and_4','__atomic_fetch_or_4','__atomic_exchange_4']:
  assert name in subprocess.check_output([tc+'nm',str(obj)],text=True)
 report={'schema':'openmitrastar.arc750-atomic32/v1','status':'PASS_REAL_HELPER_LOOPS_HOST_AND_ARC_COMPILE','stdout':r.stdout.decode(),'hardware_accessed':False,'physical':'UNRUN','source_sha256':hashlib.sha256(source.encode()).hexdigest(),'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'limits':['Host backend verifies loops and concurrent semantics; ARC backend syscall runtime is unrun.','UP ARC750 only; not an SMP atomic implementation.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
