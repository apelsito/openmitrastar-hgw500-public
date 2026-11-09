"""Host-test actual F355 and Linux 5.10 refcount/init/teardown functions."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,subprocess
from prepare_f344_csa_policy import closing
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1];Q=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime/qdrv'
KERNEL='/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux/kernel/module.c'
def extract(s,n):
 m=re.search(r'\b'+n+r'\([^;{}()]*\)\s*\{',s,re.M)
 if not m:raise ValueError(n)
 start=s.rfind('\n',0,m.start())+1
 if not s[start:m.start()].strip():
  previous=s.rfind('\n',0,max(0,start-1))+1
  if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9 \t*]*\n',s[previous:start]):start=previous
 return s[start:closing(s,m.start())+1]+'\n'
PRE=r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {MODULE_STATE_LIVE,MODULE_STATE_COMING,MODULE_STATE_GOING};
struct module {_Atomic int refcnt,state;};static struct module module_owner;
#define THIS_MODULE (&module_owner)
#define MODULE_REF_BASE 1
#define module_is_live(m) ((m)->state!=MODULE_STATE_GOING)
#define likely(v) (v)
#define BUG_ON(v) assert(!(v))
#define _RET_IP_ 0
#define trace_module_get(m,ip) do{(void)(m);(void)(ip);}while(0)
#define preempt_disable() do{}while(0)
#define preempt_enable() do{}while(0)
static int atomic_inc_not_zero(_Atomic int*p){int old=atomic_load(p);while(old&& !atomic_compare_exchange_weak(p,&old,old+1)){}return old!=0;}
static int atomic_sub_return(int n,_Atomic int*p){return atomic_fetch_sub(p,n)-n;}
static int atomic_add_unless(_Atomic int*p,int n,int unless){int old=atomic_load(p);while(old!=unless&&!atomic_compare_exchange_weak(p,&old,old+n)){}return old!=unless;}
static int try_force_unload(unsigned flags){(void)flags;return 0;}
#define DEFINE_SPINLOCK(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define spin_lock_irqsave(l,f) do{(f)=0;pthread_mutex_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);pthread_mutex_unlock(l);}while(0)
#define READ_ONCE(v) (v)
#define pr_info(...) do{}while(0)
#define pr_err(...) do{}while(0)
#define scnprintf snprintf
#define strlcpy f355_test_strlcpy
static size_t strlcpy(char*d,const char*s,size_t n){size_t len=strlen(s);if(n)snprintf(d,n,"%s",s);return len;}
#include "f355_lifetime.h"
'''
MIDDLE=r'''
static unsigned checks,teardown_calls,free_calls,exit_calls,removed_files;
static unsigned serialized_calls;static bool close_while_waiting;static int f344_control_mutex;
static int fail_step,init_step;static bool control_initialized;
#define C(v) do{checks++;assert(v);}while(0)
#define __init
#define __exit
#define DBGPRINTF(...) do{}while(0)
#define DBGPRINTF_E(...) do{}while(0)
#define GFP_KERNEL 0
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(5,10,260)
#define QDRV_DEV_NAME "qdrv"
#define QDRV_RESOURCE_AUC 1
#define QDRV_RESOURCE_DSP 2
#define QDRV_RESOURCE_MUC 4
#define QDRV_RESOURCE_UC_PRINT 8
#define QDRV_RESOURCE_MAC0 16
#define QDRV_RESOURCE_MAC1 32
#define QDRV_RESOURCE_COMM 64
#define QDRV_RESOURCE_WLAN 128
struct qdrv_mac{int id;};struct qdrv_cb{unsigned resources;struct qdrv_mac macs[2];};
struct device{struct qdrv_cb*data;};static struct device qdrv_device;
static int in_atomic(void){return 0;}static int irqs_disabled(void){return 0;}
static void mutex_lock(int*p){assert(!*p);*p=1;if(close_while_waiting){close_while_waiting=false;C(!qdrv_f355_exit_begin());}}
static void mutex_unlock(int*p){assert(*p);*p=0;}
static int qdrv_control_input_serialized(struct device*d,char*b,unsigned n){(void)d;(void)b;(void)n;serialized_calls++;return 0;}
static int dev_attr_mode_state,dev_attr_control,dev_attr_lifetime_state,dev_attr_panic_on_muc_halt,qdrv_show_rssi_phy_stats;
static int panic_on_muc_halt __attribute__((unused));
static int qdrv_soc_cb_size(void){return sizeof(struct qdrv_cb);}
static void*kzalloc(size_t n,int flags){(void)flags;init_step++;return fail_step==init_step?NULL:calloc(1,n);}
static void kfree(void*p){free_calls++;free(p);}
static void dev_set_name(struct device*d,const char*s){(void)d;(void)s;}
static void dev_set_drvdata(struct device*d,void*p){d->data=p;}
static void*dev_get_drvdata(struct device*d){return d->data;}
static void qdrv_panic_on_muc_halt_init(void){}
static int init_point(void){init_step++;C(qdrv_f355_claim("init-race")==F355_NOT_READY);return fail_step==init_step?-1:0;}
static int device_register(struct device*d){(void)d;return init_point();}
static void put_device(struct device*d){(void)d;C(fail_step==2);}
static void device_unregister(struct device*d){(void)d;}
static int device_create_file(struct device*d,int*a){(void)d;(void)a;return init_point();}
static void device_remove_file(struct device*d,int*a){(void)d;(void)a;removed_files++;}
static void device_remove_bin_file(struct device*d,int*a){(void)d;(void)a;removed_files++;}
static int qdrv_control_init(struct device*d){(void)d;if(init_point())return -1;control_initialized=true;return 0;}
static int qdrv_control_exit(struct device*d){(void)d;C(control_initialized);control_initialized=false;exit_calls++;return 0;}
static int qdrv_module_create_sysfs_phy_stats(void){return init_point();}
static int qdrv_radar_exit(struct qdrv_mac*m){(void)m;teardown_calls++;return 0;}
static void qtn_show_info_unregister(void){teardown_calls++;}
static int qdrv_mu_stat_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return 0;}
static int qdrv_auc_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_dsp_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_muc_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_uc_print_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_mac_exit(struct qdrv_mac*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_comm_exit(struct qdrv_cb*q){(void)q;teardown_calls++;return -EIO;}
static int qdrv_wlan_exit(struct qdrv_mac*q){(void)q;teardown_calls++;return -EIO;}
static void qdrv_sch_module_exit(void){teardown_calls++;}
struct shared_params{unsigned alive;};struct _shared_params_alloc{struct shared_params params;};
static struct shared_params*soc_shared_params,*params_bus;static unsigned long params_dma_handle,params_wire_bus;
static struct device*qtn_platform_dma_device(void){return &qdrv_device;}
#define WARN_ON_ONCE(v) (v)
#define container_of(p,t,f) ((t*)((char*)(p)-offsetof(t,f)))
static void dma_free_coherent(struct device*d,size_t n,void*p,unsigned long h){(void)d;(void)n;(void)p;(void)h;free_calls++;}
static void qtn_mproc_sync_shared_params_set(unsigned v){(void)v;teardown_calls++;}
'''
TEST=r'''
static void reset_fixture(void){f355_state=(struct f355_lifetime){0};memset(f355_first_operation,0,sizeof(f355_first_operation));atomic_store(&module_owner.refcnt,MODULE_REF_BASE);atomic_store(&module_owner.state,MODULE_STATE_LIVE);teardown_calls=free_calls=exit_calls=removed_files=serialized_calls=0;fail_step=init_step=f344_control_mutex=0;close_while_waiting=false;control_initialized=false;qdrv_device.data=NULL;soc_shared_params=params_bus=NULL;}
static pthread_barrier_t start_barrier;static int claim_rc,remove_rc;
static void*claim_thread(void*p){(void)p;pthread_barrier_wait(&start_barrier);claim_rc=qdrv_f355_claim("race");return NULL;}
static void*remove_thread(void*p){int forced=0;(void)p;pthread_barrier_wait(&start_barrier);remove_rc=try_stop_module(&module_owner,0,&forced);return NULL;}
static unsigned late_callback(struct shared_params*p){C(p->alive==0x355);return ++p->alive;}
int main(void){unsigned n,steps;int forced,rc;char state[512];pthread_t a,b;struct _shared_params_alloc shared;
 reset_fixture();C(qdrv_f355_claim("early")==F355_NOT_READY);C(atomic_load(&module_owner.refcnt)==1&&!qdrv_f355_retained());
 qdrv_f355_ready_commit();C(!qdrv_f355_claim("set"));C(atomic_load(&module_owner.refcnt)==2&&qdrv_f355_retained());
 C(!qdrv_f355_claim("clearsram"));C(atomic_load(&module_owner.refcnt)==2);forced=0;C(try_stop_module(&module_owner,0,&forced)==-EWOULDBLOCK);C(module_owner.state==MODULE_STATE_LIVE);
 C(!qdrv_f355_core_begin());C(qdrv_f355_core_begin()==F355_ALREADY_ATTEMPTED);qdrv_f355_boot_failure();C(qdrv_f355_failed()&&qdrv_f355_claim("retry")==F355_BOOT_FAILED);C(qdrv_f355_retained());
 shared.params.alive=0x355;soc_shared_params=&shared.params;params_bus=&shared.params;params_dma_handle=42;params_wire_bus=24;
 qdrv_soc_revoke_params();C(!free_calls&&!teardown_calls&&soc_shared_params==&shared.params&&params_dma_handle==42);
 {struct qdrv_cb cb={.resources=255};qdrv_device.data=&cb;C(qdrv_soc_exit(&qdrv_device)==-EBUSY);C(!free_calls&&!teardown_calls&&cb.resources==255);C(late_callback(soc_shared_params)==0x356);qdrv_module_exit();C(!free_calls&&!removed_files);}
 C(qdrv_f355_status(state)>0&&strstr(state,"retained=1")&&strstr(state,"boot_failed=1")&&strstr(state,"release_supported=0"));
 reset_fixture();qdrv_f355_ready_commit();forced=0;C(!try_stop_module(&module_owner,0,&forced));C(qdrv_f355_claim("losing-race")==F355_BUSY&&!qdrv_f355_retained());
 reset_fixture();C(qdrv_control_input(&qdrv_device,"get",3)==-EAGAIN&&!serialized_calls);qdrv_f355_ready_commit();C(!qdrv_control_input(&qdrv_device,"get",3)&&serialized_calls==1);close_while_waiting=true;C(qdrv_control_input(&qdrv_device,"get",3)==-EAGAIN&&serialized_calls==1&&!f344_control_mutex);
 /* Initializer publication races and every initializer failure: no pin can
  * exist until its final commit, so a failed init cannot unload pinned code. */
 reset_fixture();C(!qdrv_module_init());steps=init_step;C(qdrv_f355_ready()&&!qdrv_f355_retained());qdrv_module_exit();C(free_calls==1&&exit_calls==1&&!control_initialized);
 for(n=1;n<=steps;n++){reset_fixture();fail_step=(int)n;rc=qdrv_module_init();C(rc!=0&&!qdrv_f355_ready()&&!qdrv_f355_retained());C(module_owner.refcnt==1&&!control_initialized);C(free_calls==(n==1?0U:1U));if(n==steps)C(exit_calls==1);}
 /* Two real host threads race the extracted Linux refcount algorithm with
  * the actual F355 adapter. Exactly one side may win; no forced unload. */
 for(n=0;n<256;n++){reset_fixture();qdrv_f355_ready_commit();C(!pthread_barrier_init(&start_barrier,NULL,2));C(!pthread_create(&a,NULL,claim_thread,NULL));C(!pthread_create(&b,NULL,remove_thread,NULL));pthread_join(a,NULL);pthread_join(b,NULL);pthread_barrier_destroy(&start_barrier);C(!(claim_rc==0&&remove_rc==0));if(!claim_rc)C(remove_rc==-EWOULDBLOCK&&qdrv_f355_retained()&&module_owner.refcnt==2);else C(!remove_rc&&!qdrv_f355_retained()&&module_owner.refcnt==0);}
 printf("F355_ACTUAL_LIFETIME_PASS checks=%u init_failures=%u race_pairs=256 fake_kernel_services=1 hardware=0\n",checks,steps);return 0;}
'''
def main():
 if shutil.disk_usage(ROOT).free<=500*1024*1024:raise RuntimeError('C space guard')
 out=Path('/workspace/OpenMitraStar-build/f355')/('f355-lifetime-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 k=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',KERNEL],capture_output=True,text=True,timeout=15)
 if k.returncode:raise ValueError('kernel module source unavailable')
 adapter=(Q/'qdrv_f355_lifetime.c').read_text();adapter=re.sub(r'^#include[^\n]*\n','',adapter,flags=re.M)
 kernel_functions=''.join(extract(k.stdout,n) for n in ('try_release_module_ref','try_stop_module','try_module_get'))
 soc=(Q/'qdrv_soc.c').read_text();module=(Q/'qdrv_module.c').read_text()
 actual=extract(soc,'qdrv_soc_revoke_params')+extract(soc,'qdrv_soc_exit')+extract(module,'qdrv_module_init')+extract(module,'qdrv_module_exit')+extract((Q/'qdrv_control.c').read_text(),'qdrv_control_input')
 (out/'test.c').write_bytes((PRE+kernel_functions+adapter+MIDDLE+actual+TEST).encode())
 (out/'f355_lifetime.h').write_bytes((Q/'f355_lifetime.h').read_bytes())
 script=f"set -eu\ncc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -Wno-unused-parameter -pthread '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=60)
 result={'schema':'openmitrastar.f355-lifetime-tests/v1','status':'PASS_ACTUAL_DRIVER_KERNEL_LIFETIME' if not p.returncode else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'kernel_module_c_sha256':hashlib.sha256(k.stdout.encode()).hexdigest(),'kernel_source':KERNEL,'source_bindings':{n:hashlib.sha256((Q/n).read_bytes()).hexdigest() for n in ('qdrv_control.c','qdrv_soc.c','qdrv_module.c','qdrv_f355_lifetime.c','f355_lifetime.h')},'hardware':False,'new_firmware_epoch':False,'forced_unload_supported':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
