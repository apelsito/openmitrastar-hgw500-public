"""Exercise actual proc init/exit and verify F355's release boundaries."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess
from test_f355_lifetime import extract
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1];Q=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime/qdrv'
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u_int32_t;
struct qdrv_cb{int id;};struct device{struct qdrv_cb*data;};struct proc_dir_entry{int id;};
static struct qdrv_cb cb;static struct device dev={&cb};static struct proc_dir_entry nodes[3];
static struct qdrv_cb*s_output_qcb;static int s_output_sem,qdrv_event_lock,qdrv_event_log_table[3],s_qdrv_proc_ops;
static int qdrv_hw_revision_show,qdrv_carrier_id_show,qdrv_wbsp_ctrl __attribute__((unused));
static unsigned checks,created_mask,stage,fail_stage,removes,locks;
#define C(v) do{checks++;assert(v);}while(0)
#define DBGPRINTF(...) do{}while(0)
#define DBGPRINTF_N(...) do{}while(0)
#define DBGPRINTF_E(...) do{}while(0)
#define printk(...) do{if(0)printf(__VA_ARGS__);}while(0)
#define QDRV_EVENT(...) do{}while(0)
#define RUBY_SRAM_BEGIN 0
#define CONFIG_ARC_AUC_SRAM_BASE 4
#define CONFIG_ARC_AUC_SRAM_END 20
#define CONFIG_ARC_AUC_SRAM_SIZE 16
#define RUBY_SRAM_BANK_SIZE 8
static void*dev_get_drvdata(struct device*d){return d->data;}
static void sema_init(int*s,int n){*s=n;}
static void spin_lock_init(int*s){*s=0;}
static void down(int*s){C(*s==1&&!locks);*s=0;locks++;}
static void up(int*s){C(*s==0&&locks==1);*s=1;locks--;}
static struct proc_dir_entry*new_node(void){C(s_output_sem==1&&s_output_qcb==&cb);stage++;if(stage==fail_stage)return NULL;created_mask|=1U<<(stage-1);return &nodes[stage-1];}
static struct proc_dir_entry*proc_create(const char*n,unsigned m,void*p,void*ops){(void)n;(void)m;(void)p;(void)ops;return new_node();}
static struct proc_dir_entry*proc_create_single(const char*n,unsigned m,void*p,int show){(void)n;(void)m;(void)p;(void)show;return new_node();}
static void remove_proc_entry(const char*n,void*p){unsigned bit=(unsigned)!strcmp(n,"qdrvdata")?0:!strcmp(n,"hw_revision")?1:2;(void)p;C(created_mask&(1U<<bit));created_mask&=~(1U<<bit);removes++;}
'''
TEST=r'''
int main(void){unsigned n;for(n=1;n<=3;n++){s_output_sem=0;s_output_qcb=NULL;stage=created_mask=removes=0;fail_stage=n;C(qdrv_control_init(&dev)<0);C(!created_mask&&removes==n-1&&!locks);}
 s_output_sem=0;s_output_qcb=NULL;stage=created_mask=removes=0;fail_stage=0;
 C(!qdrv_control_init(&dev)&&created_mask==7);C(!qdrv_control_exit(&dev));C(!created_mask&&removes==3&&s_output_qcb==NULL&&!locks);
 printf("F355_ACTUAL_PROC_INIT_EXIT_PASS checks=%u failure_points=3 fake_procfs=1 hardware=0\n",checks);return 0;}
'''
def main():
 if shutil.disk_usage(ROOT).free<=500*1024*1024:raise RuntimeError('C space guard')
 out=Path('/workspace/OpenMitraStar-build/f355')/('f355-proc-contract-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 control=(Q/'qdrv_control.c').read_text();soc=(Q/'qdrv_soc.c').read_text();module=(Q/'qdrv_module.c').read_text();wlan=(Q/'qdrv_wlan.c').read_text();hostlink=(Q/'qdrv_hostlink.c').read_text();lifetime=(Q/'qdrv_f355_lifetime.c').read_text()
 (out/'test.c').write_bytes((PRE+extract(control,'qdrv_control_init')+extract(control,'qdrv_control_exit')+TEST).encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 contracts={}
 def check(name,v):contracts[name]=bool(v)
 dispatch=extract(control,'qdrv_control_input_serialized');check('pin_before_handler',dispatch.index('qdrv_f355_claim')<dispatch.index('(*s_command_table[found].fn)'))
 check('policy_before_pin',dispatch.index('qdrv_sequential_precheck')<dispatch.index('qdrv_f355_claim'))
 entry=extract(control,'qdrv_control_input');check('ready_rechecked_after_wait',entry.count('qdrv_f355_ready()')==2 and entry.index('mutex_lock')<entry.rindex('qdrv_f355_ready()')<entry.index('qdrv_control_input_serialized'))
 core=extract(soc,'qdrv_soc_init');check('core_pin_before_reset',core.index('qdrv_f355_core_begin')<core.index('hal_reset();'));check('no_unsafe_init_error_teardown','qdrv_soc_exit(' not in core and 'qdrv_f355_boot_failure()' in core)
 for key,source,fn,release in [('soc',soc,'qdrv_soc_exit','qdrv_radar_exit'),('shared',soc,'qdrv_soc_revoke_params','dma_free_coherent'),('wlan',wlan,'qdrv_wlan_exit','qdrv_wlan_80211_exit'),('hostlink',hostlink,'qdrv_hostlink_exit','flush_scheduled_work')]:
  body=extract(source,fn);check(key+'_retained_before_release',body.index('qdrv_f355_retained()')<body.index(release))
 publish=extract(soc,'qdrv_soc_publish_params');check('no_shared_overwrite',publish.index('if(soc_shared_params)return -EBUSY;')<publish.index('dma_alloc_coherent('))
 exit_body=extract(module,'qdrv_module_exit');check('no_bare_stop_on_unload','qdrv_control_input(' not in exit_body);check('sysfs_drained_before_proc_cleanup',exit_body.index('device_remove_file(&qdrv_device,&dev_attr_control)')<exit_body.index('qdrv_control_exit')<exit_body.index('kfree(data)'))
 init=extract(module,'qdrv_module_init');check('ready_commit_after_last_failure',init.index('qdrv_f355_ready_commit')>init.index('qdrv_module_create_sysfs_phy_stats'));check('partial_init_control_cleanup','if(control_initialized)qdrv_control_exit' in init);check('failed_device_registration_put','put_device(&qdrv_device)' in init)
 check('no_retained_pin_release','module_put(' not in lifetime);check('forced_unload_rejected_at_build','#ifdef CONFIG_MODULE_FORCE_UNLOAD\n#error' in lifetime)
 check('no_wire_header_changes',not any(p.name=='ieee80211_var.h' for p in Q.rglob('*.h')))
 ok=not p.returncode and all(contracts.values())
 result={'status':'PASS_PROC_INIT_EXIT_AND_RELEASE_CONTRACT' if ok else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'contracts':contracts,'failed_contracts':[k for k,v in contracts.items() if not v],'source_bindings':{n:hashlib.sha256((Q/n).read_bytes()).hexdigest() for n in ('qdrv_control.c','qdrv_soc.c','qdrv_module.c','qdrv_wlan.c','qdrv_hostlink.c','qdrv_f355_lifetime.c')},'hardware':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return not ok
if __name__=='__main__':raise SystemExit(main())
