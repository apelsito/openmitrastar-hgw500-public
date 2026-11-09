"""Actual SRAM provider/core with task-owned pthread writer lease and fake MMIO."""
import argparse,hashlib,json,runpy,subprocess
from pathlib import Path

LOCKS = r'''
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
#include <sched.h>
#define U64_MAX UINT64_MAX
typedef uint64_t u64;
struct task_struct { int identity; };
static _Thread_local struct task_struct fixture_task;
#define current (&fixture_task)
#define DEFINE_MUTEX(name) pthread_mutex_t name=PTHREAD_MUTEX_INITIALIZER
#define DEFINE_SPINLOCK(name) pthread_mutex_t name=PTHREAD_MUTEX_INITIALIZER
static _Thread_local unsigned spin_depth,mutex_depth;
static void lock_spin(pthread_mutex_t *lock,unsigned long *flags){*flags=0;assert(!pthread_mutex_lock(lock));spin_depth++;}
static void unlock_spin(pthread_mutex_t *lock,unsigned long flags){(void)flags;assert(spin_depth);spin_depth--;assert(!pthread_mutex_unlock(lock));}
#define spin_lock_irqsave(lock,flags) lock_spin((lock),&(flags))
#define spin_unlock_irqrestore(lock,flags) unlock_spin((lock),(flags))
static void mutex_lock(pthread_mutex_t *lock){assert(!spin_depth);assert(!pthread_mutex_lock(lock));mutex_depth++;}
static void mutex_unlock(pthread_mutex_t *lock){assert(mutex_depth);mutex_depth--;assert(!pthread_mutex_unlock(lock));}
'''

TEST = r'''
static atomic_int started,completed;
static int threaded_result,thread_mode;
static struct om73_sram_writer_token *foreign_token;
static void *operation(void *arg){
 (void)arg;atomic_store(&started,1);
 if(thread_mode==0){struct om73_sram_writer_token token;threaded_result=om73_sram_writer_begin(1,&token);if(!threaded_result)threaded_result=om73_sram_writer_end(&token);}
 else if(thread_mode==1){struct om73_sram_board_contract b=valid();threaded_result=om73_sram_acquire(&b);}
 else if(thread_mode==2)threaded_result=om73_sram_close();
 else if(thread_mode==3)threaded_result=om73_sram_writer_end(foreign_token);
 atomic_store(&completed,1);return NULL;
}
static pthread_t start_thread(int mode){
 pthread_t thread;thread_mode=mode;atomic_store(&started,0);atomic_store(&completed,0);
 assert(!pthread_create(&thread,NULL,operation,NULL));
 for(unsigned n=0;!atomic_load(&started)&&n<1000000;n++)sched_yield();
 assert(atomic_load(&started));return thread;
}
static void blocked(void){usleep(20000);assert(!atomic_load(&completed));}
int main(void){
 int baseline=fixture_core_main();assert(!baseline);unsigned cases=362;
 struct om73_sram_writer_token token={0},copy,old;
 struct om73_sram_board_contract b=valid();struct om73_sram_allocation allocation;int owner;
 assert(om73_sram_writer_begin(3,&token)==-EINVAL);cases++;
 assert(om73_sram_writer_begin(0,NULL)==-EINVAL);cases++;
 assert(om73_sram_writer_check(&token,0x88012000,1)==-EPERM);cases++;
 assert(om73_sram_writer_end(&token)==-EPERM);cases++;
 fail_module=1;assert(om73_sram_writer_begin(0,&token)==-ENODEV);fail_module=0;closed();cases++;
 om73_writer_generation=U64_MAX;assert(om73_sram_writer_begin(0,&token)==-EOVERFLOW);om73_writer_generation=0;closed();cases++;
 assert(om73_sram_writer_begin(0,&token)==0);assert(module_live==1&&mutex_depth==1);cases++;
 assert(om73_sram_writer_check(&token,0x88012000,8192)==0);cases++;
 assert(om73_sram_writer_check(&token,0xffffffff,2)==-ERANGE);cases++;
 assert(om73_sram_writer_check(&token,0,0)==-ERANGE);cases++;
 copy=token;assert(om73_sram_writer_end(&copy)==-EPERM);assert(mutex_depth==1&&module_live==1);cases++;
 old=token;token.generation--;assert(om73_sram_writer_end(&token)==-EPERM);token=old;cases++;
 token.cpu=2;assert(om73_sram_writer_check(&token,0x88000000,1)==-EPERM);token=old;cases++;
 assert(om73_sram_writer_begin(1,&copy)==-EBUSY);cases++;
 assert(om73_sram_acquire(&b)==-EBUSY);cases++;
 assert(om73_sram_close()==-EBUSY);cases++;
 foreign_token=&token;pthread_t foreign=start_thread(3);assert(!pthread_join(foreign,NULL));assert(threaded_result==-EPERM);assert(module_live==1&&mutex_depth==1);cases++;
 pthread_t waiter=start_thread(0);blocked();assert(om73_sram_writer_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);closed();cases++;
 assert(om73_sram_writer_end(&token)==-EPERM);cases++;
 assert(om73_sram_writer_begin(2,&token)==0);
 waiter=start_thread(1);blocked();assert(om73_sram_writer_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);assert(resource_live==1&&mapping_live==1&&module_live==1);cases++;
 for(unsigned cpu=0;cpu<3;cpu++){
  assert(om73_sram_writer_begin(cpu,&token)==0);assert(module_live==2);
  /* Free-list metadata protects the full arena even with live_count==0. */
  assert(om73_core.live_count==0);
  assert(om73_sram_writer_check(&token,0x88012000,8192)==-EBUSY);
  assert(om73_sram_writer_check(&token,0x88011fff,2)==-EBUSY);
  assert(om73_sram_writer_check(&token,0x88013fff,2)==-EBUSY);
  assert(om73_sram_writer_check(&token,0x88014000,1)==0);
  assert(om73_sram_writer_check(&token,0x88011fff,1)==0);
  assert(om73_sram_alloc(&owner,64,64,&allocation)==0);
  assert(om73_sram_writer_check(&token,allocation.cpu_phys,1)==-EBUSY);
  assert(om73_sram_free(&owner)==0);
  assert(om73_sram_writer_end(&token)==0);assert(module_live==1);cases+=9;
 }
 assert(om73_sram_writer_begin(0,&token)==0);
 waiter=start_thread(2);blocked();assert(om73_sram_writer_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);closed();cases++;
 printf("PASS actual task writer lease cases=%u concurrent_waiters=3 foreign_end=refused resource=%u/%u map=%u/%u\n",cases,request_calls,release_calls,map_calls,unmap_calls);
 return 0;
}
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 old=runpy.run_path(str(Path(__file__).with_name('test_linux73_sram_backend_adapter.py')));shim=old['SHIM'];start=shim.index('#define DEFINE_MUTEX(name)');end=shim.index('static int module_live',start);shim=shim[:start]+LOCKS+shim[end:];shim=shim.replace('#define EOVERFLOW 75','#define EOVERFLOW 75\n#define EPERM 1\n#define ERANGE 34')
 inc=a.output/'include'
 for name in('linux/types.h','linux/string.h','linux/ioport.h','linux/errno.h','linux/io.h','linux/log2.h','linux/module.h','linux/mutex.h','linux/overflow.h','linux/spinlock.h','linux/sched.h','asm/page.h'):
  path=inc/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('/* fake resource/MMIO; actual pthread lifetime synchronization */\n')
 (a.output/'shim.h').write_text(shim);fixture=a.output/'fixture.c';body=old['HARNESS'].replace('int main(void)','int fixture_core_main(void)',1);fixture.write_text('#include "'+str((a.source/'om_sram_core.c').resolve())+'"\n#include "'+str((a.source/'om73_sram_backend.c').resolve())+'"\n'+body+TEST)
 binary=a.output/'fixture';cmd=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(inc.resolve()),'-include',str((a.output/'shim.h').resolve()),str(fixture.resolve()),'-o',str(binary.resolve())];r=subprocess.run(cmd,capture_output=True,text=True);(a.output/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(binary.resolve())],capture_output=True,text=True);(a.output/'run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 result={'status':'PASS_ACTUAL_SRAM_CORE_BACKEND_TASK_WRITER_LEASE_OWNERSHIP_CONCURRENT_WAITS','output':r.stdout.strip(),'source_sha256':sha(a.source/'om73_sram_backend.c'),'header_sha256':sha(a.source/'om73_sram_backend.h'),'hardware_accessed':False,'firmware_eligible':False,'limits':'Actual source/core with pthread locks and task TLS; resource/map mocked, no physicalwriters/cache/RF proof','command':cmd};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
