"""Actual reset admission plus writer/core regressions with concurrent tasks."""
import argparse,hashlib,json,runpy,subprocess
from pathlib import Path

RESET_TEST = r'''
static struct om73_sram_reset_token *foreign_reset;
static int reset_thread_mode;
static void *reset_operation(void *arg){
 (void)arg;atomic_store(&started,1);
 if(reset_thread_mode==0){struct om73_sram_reset_token token;threaded_result=om73_sram_reset_begin(0x4180,&token);if(!threaded_result)threaded_result=om73_sram_reset_end(&token);}
 else if(reset_thread_mode==1)threaded_result=om73_sram_reset_end(foreign_reset);
 else if(reset_thread_mode==2){struct om73_sram_writer_token token;threaded_result=om73_sram_writer_begin(1,&token);if(!threaded_result)threaded_result=om73_sram_writer_end(&token);}
 else if(reset_thread_mode==3){struct om73_sram_board_contract b=valid();threaded_result=om73_sram_acquire(&b);}
 else if(reset_thread_mode==4)threaded_result=om73_sram_close();
 else if(reset_thread_mode==5){int owner;struct om73_sram_allocation allocation;threaded_result=om73_sram_alloc(&owner,64,64,&allocation);}
 atomic_store(&completed,1);return NULL;
}
static pthread_t start_reset_thread(int mode){
 pthread_t thread;reset_thread_mode=mode;atomic_store(&started,0);atomic_store(&completed,0);
 assert(!pthread_create(&thread,NULL,reset_operation,NULL));
 for(unsigned n=0;!atomic_load(&started)&&n<1000000;n++)sched_yield();
 assert(atomic_load(&started));return thread;
}
int main(void){
 assert(fixture_writer_main()==0);unsigned cases=410;
 struct om73_sram_board_contract b=valid();struct om73_sram_reset_token token={0},copy,old;
 struct om73_sram_writer_token writer;struct om73_sram_allocation allocation;int owner;
 for(unsigned bit=0;bit<32;bit++)if((1u<<bit)!=0x4180){assert(om73_sram_reset_begin(1u<<bit,&token)==-EINVAL);cases++;}
 assert(om73_sram_reset_begin(0,&token)==-EINVAL);cases++;
 assert(om73_sram_reset_begin(0x4180,NULL)==-EINVAL);cases++;
 assert(om73_sram_reset_end(&token)==-EPERM);cases++;
 fail_module=1;assert(om73_sram_reset_begin(0x4180,&token)==-ENODEV);fail_module=0;closed();cases++;
 om73_reset_generation=U64_MAX;assert(om73_sram_reset_begin(0x4180,&token)==-EOVERFLOW);om73_reset_generation=0;closed();cases++;
 assert(om73_sram_writer_begin(0,&writer)==0);
 assert(om73_sram_reset_begin(0x4180,&token)==-EBUSY);cases++;
 pthread_t waiter=start_reset_thread(0);blocked();assert(om73_sram_writer_end(&writer)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);closed();cases++;
 assert(om73_sram_acquire(&b)==0);assert(om73_sram_alloc(&owner,64,64,&allocation)==0);
 unsigned refs=module_live;assert(om73_sram_reset_begin(0x4180,&token)==-EBUSY);assert(module_live==(int)refs);cases++;
 assert(om73_sram_query(&owner,&allocation)==0);assert(om73_sram_free(&owner)==0);
 /* Detect inconsistent retained ledger even if the core count was cleared. */
 om73_owned[0].owner=&owner;assert(om73_sram_reset_begin(0x4180,&token)==-EBUSY);om73_owned[0].owner=NULL;cases++;
 assert(om73_sram_reset_begin(0x4180,&token)==0);assert(module_live==2&&mutex_depth==1);cases++;
 copy=token;assert(om73_sram_reset_end(&copy)==-EPERM);cases++;
 old=token;token.generation--;assert(om73_sram_reset_end(&token)==-EPERM);token=old;cases++;
 token.mask++;assert(om73_sram_reset_end(&token)==-EPERM);token=old;cases++;
 assert(om73_sram_reset_begin(0x4180,&copy)==-EBUSY);cases++;
 assert(om73_sram_writer_begin(0,&writer)==-EBUSY);cases++;
 assert(om73_sram_acquire(&b)==-EBUSY);cases++;
 assert(om73_sram_close()==-EBUSY);cases++;
 assert(om73_sram_alloc(&owner,64,64,&allocation)==-EBUSY);cases++;
 assert(om73_sram_query(&owner,&allocation)==-EBUSY);cases++;
 assert(om73_sram_free(&owner)==-EBUSY);cases++;
 foreign_reset=&token;pthread_t foreign=start_reset_thread(1);assert(!pthread_join(foreign,NULL));assert(threaded_result==-EPERM);assert(module_live==2&&mutex_depth==1);cases++;
 foreign=start_reset_thread(5);assert(!pthread_join(foreign,NULL));assert(threaded_result==-EBUSY);cases++;
 waiter=start_reset_thread(2);blocked();assert(om73_sram_reset_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0&&module_live==1);cases++;
 assert(om73_sram_alloc(&owner,64,64,&allocation)==0);assert(om73_sram_free(&owner)==0);cases++;
 /* Reset admission does not touch preserved free-list state. */
 unsigned long free_bytes=om73_core.memlist.length;assert(om73_sram_reset_begin(0x4180,&token)==0);
 waiter=start_reset_thread(4);blocked();assert(om73_core.memlist.length==free_bytes);assert(om73_sram_reset_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);closed();cases++;
 assert(om73_sram_reset_begin(0x4180,&token)==0);
 waiter=start_reset_thread(3);blocked();assert(om73_sram_reset_end(&token)==0);assert(!pthread_join(waiter,NULL));assert(threaded_result==0);assert(om73_sram_close()==0);closed();cases++;
 printf("PASS actual reset software lease cases=%u mask=0x4180 hardware_reset_writes=0 concurrent_waiters=4\n",cases);
 return 0;
}
'''

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 provider=runpy.run_path(str(Path(__file__).with_name('test_linux73_sram_backend_adapter.py')));writer=runpy.run_path(str(Path(__file__).with_name('test_linux73_sram_writer_lease.py')));shim=provider['SHIM'];start=shim.index('#define DEFINE_MUTEX(name)');end=shim.index('static int module_live',start);shim=shim[:start]+writer['LOCKS']+shim[end:];shim=shim.replace('#define EOVERFLOW 75','#define EOVERFLOW 75\n#define EPERM 1\n#define ERANGE 34')
 inc=a.output/'include'
 for name in('linux/types.h','linux/string.h','linux/ioport.h','linux/errno.h','linux/io.h','linux/log2.h','linux/module.h','linux/mutex.h','linux/overflow.h','linux/spinlock.h','linux/sched.h','asm/page.h'):
  f=inc/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('/* actual pthread task synchronization; fake physical operations */\n')
 (a.output/'shim.h').write_text(shim);fixture=a.output/'fixture.c';old=provider['HARNESS'].replace('int main(void)','int fixture_core_main(void)',1);wr=writer['TEST'].replace('int main(void)','int fixture_writer_main(void)',1);fixture.write_text('#include "'+str((a.source/'om_sram_core.c').resolve())+'"\n#include "'+str((a.source/'om73_sram_backend.c').resolve())+'"\n'+old+wr+RESET_TEST)
 binary=a.output/'fixture';cmd=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(inc.resolve()),'-include',str((a.output/'shim.h').resolve()),str(fixture.resolve()),'-o',str(binary.resolve())];r=subprocess.run(cmd,capture_output=True,text=True);(a.output/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(binary.resolve())],capture_output=True,text=True);(a.output/'run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 result={'status':'PASS_ACTUAL_SRAM_CORE_WRITER_RESET_SOFTWARE_LEASE_CONCURRENT_TASK_FIXTURE','source_sha256':sha(a.source/'om73_sram_backend.c'),'header_sha256':sha(a.source/'om73_sram_backend.h'),'output':r.stdout.strip(),'hardware_accessed':False,'firmware_eligible':False,'hardware_quiescence_proved':False,'limits':'Reset software admission only; no actual reset/queue/device/MMIO proof. pthreadlifeactual locks; resource/mapping fakes.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
