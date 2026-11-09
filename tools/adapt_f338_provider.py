"""Apply the F338 syscall boundary to the newly seeded provider copy only."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'work/kernel-port/f338/kernel/f332_provider.c'
def main():
 s=P.read_text()
 if '#include "f338_ipc.h"' in s:raise SystemExit('already adapted')
 s=s.replace('separate proprietary math engines','GPL math postfilter and a separate userspace service')
 s=s.replace('#include "f332_errors.h"','#include "f338_ipc.h"')
 s=s.replace('F332_RELEASE_QUALIFIED','F338_RELEASE_QUALIFIED')
 s=s.replace('static struct delayed_work poll_work;','''static struct delayed_work poll_work;
static struct work_struct availability_work;
static void (*availability_callback)(uint32_t,uint32_t);
static bool loss_pending,loss_running;
static uint32_t loss_generation,loss_reason;''')
 s=s.replace(' struct f332_ocac_state ocac_state;',' struct f332_ocac_state ocac_state;\n struct f338_job job;\n struct f338_reply reply;')
 pos=s.index('static uint32_t ticks200')
 s=s[:pos]+'''/* Availability is distinct from radar detection: no NOP is created. */
static void availability_worker(struct work_struct *unused)
{
 unsigned long flags;void (*cb)(uint32_t,uint32_t);uint32_t gen,reason;bool again;(void)unused;
 for(;;){
  spin_lock_irqsave(&request_lock,flags);
  if(!loss_pending){spin_unlock_irqrestore(&request_lock,flags);break;}
  loss_pending=false;loss_running=true;gen=loss_generation;reason=loss_reason;cb=availability_callback;
  spin_unlock_irqrestore(&request_lock,flags);
  if(cb)cb(gen,reason);
  spin_lock_irqsave(&request_lock,flags);loss_running=false;again=requests.started;
  spin_unlock_irqrestore(&request_lock,flags);
  if(again)mod_delayed_work(system_wq,&poll_work,0);
 }
}
static void service_lost(unsigned reason)
{
 unsigned long flags;uint32_t generation;
 spin_lock_irqsave(&request_lock,flags);
 generation=ready&&(requests.applied_epoch<=0xffffffffULL)?(uint32_t)requests.applied_epoch:0;
 ready=false;
 if(!loss_pending){loss_generation=generation;loss_reason=reason;loss_pending=true;}
 else if(reason==F338_HARDWARE_FAULT)loss_reason=reason;
 (void)f327_oem_invalidate(&requests);
 spin_unlock_irqrestore(&request_lock,flags);
 f338_ipc_wake();schedule_work(&availability_work);
}
int radar_register_availability(void(*cb)(uint32_t,uint32_t))
{
 unsigned long flags;spin_lock_irqsave(&request_lock,flags);availability_callback=cb;
 if(!cb)ready=false;spin_unlock_irqrestore(&request_lock,flags);return 0;
}
''' +s[pos:]
 s=s.replace(' if(w->epoch>0xffffffffULL', ' if(!f338_ipc_available())return -ENOTCONN;\n if(w->epoch>0xffffffffULL')
 s=s.replace('sta_required=!!workspace->pipeline.detection.configuration[1];','sta_required=true; /* Exact EU profile byte1=1, validated by first service reply. */')
 s=s.replace(' cancel_delayed_work(&poll_work);',' f338_ipc_wake();\n cancel_delayed_work(&poll_work);')
 s=s.replace(' if(wanted.registrations!=7)goto reschedule;',' if(wanted.registrations!=7||!f338_ipc_available()||READ_ONCE(loss_pending)||READ_ONCE(loss_running))goto reschedule;')
 s=s.replace('frame.raw=(const struct f330_raw*)','frame.raw=(const struct f332_pulse*)')
 s=s.replace(' rc=f332_pipeline_errno(f332_pipeline_run(&workspace->pipeline,&frame,&workspace->result));polls++;', ''' rc=f338_pipeline_make_job(&workspace->pipeline,&frame,&workspace->job,&workspace->result);
 if(rc)goto discard;
 /* The worker alone owns PM. There is NO BB or state_lock across IPC.
  * A reset RPC wakes this worker and is performed before its PM release. */
 mutex_unlock(&state_lock);
 rc=f338_ipc_exchange(&workspace->job,&workspace->reply,f332_provider_current,f332_hw_reset);
 mutex_lock(&state_lock);
 if(!rc&&!f332_provider_current((uint32_t)wanted.epoch))rc=-ESTALE;
 if(!rc)rc=f338_pipeline_finish(&workspace->pipeline,&frame,&workspace->reply,&workspace->result);
 polls++;''')
 s=s.replace('ready=context_ok&&workspace->result.postfilter_applied&&f332_hw_ready()&&','ready=context_ok&&!loss_pending&&!loss_running&&availability_callback&&workspace->result.postfilter_applied&&f332_hw_ready()&&')
 s=s.replace(' if(f332_context_cancelled(rc)){',' if(rc==-ESTALE||rc==-ENOTCONN||rc==-ETIMEDOUT||rc==-EPROTO){')
 s=s.replace('  last_error=rc;ready=false;events.phase=F332_OFF;','  if(rc!=-ESTALE&&rc!=-ENOTCONN)service_lost(rc==-ETIMEDOUT?F338_SERVICE_TIMEOUT:F338_SERVICE_PROTOCOL);\n  last_error=rc;ready=false;events.phase=F332_OFF;')
 s=s.replace(' last_error=rc;ready=false;events.phase=F332_FAULT;',' service_lost(F338_HARDWARE_FAULT);\n last_error=rc;ready=false;events.phase=F332_FAULT;')
 s=s.replace(' if(current_work()==&poll_work.work)return -EDEADLK;',' if(current_work()==&poll_work.work||current_work()==&availability_work)return -EDEADLK;')
 s=s.replace(' stop_request(true);cancel_delayed_work_sync(&poll_work);',' stop_request(true);cancel_delayed_work_sync(&poll_work);cancel_work_sync(&availability_work);f338_ipc_cancel();')
 s=s.replace(' dfs_callback=0;is_dfs_channel=0;', ' availability_callback=0;loss_pending=loss_running=false;\n dfs_callback=0;is_dfs_channel=0;')
 s=s.replace('EXPORT_SYMBOL(radar_wait_stopped);','EXPORT_SYMBOL(radar_wait_stopped);EXPORT_SYMBOL(radar_register_availability);')
 s=s.replace('openmitrastar.f332-provider/v1','openmitrastar.f338-provider/v1').replace('openmitrastar_radar_f332','openmitrastar_radar_f338')
 s=s.replace('static int __init provider_init(void)\n{','static int __init provider_init(void)\n{\n int rc;')
 s=s.replace(' BUILD_BUG_ON(sizeof(struct f333_raw)!=sizeof(struct f330_raw));\n','')
 s=s.replace('f327_oem_init(&requests,36,80);INIT_DELAYED_WORK(&poll_work,worker);','f327_oem_init(&requests,36,80);INIT_DELAYED_WORK(&poll_work,worker);INIT_WORK(&availability_work,availability_worker);\n rc=f338_ipc_init(service_lost);if(rc){kfree(workspace);return rc;}')
 s=s.replace('remove_proc_subtree("openmitrastar_radar_f338",0);kfree(workspace);return -ENOMEM;','remove_proc_subtree("openmitrastar_radar_f338",0);f338_ipc_exit();kfree(workspace);return -ENOMEM;')
 s=s.replace('f332_hw_cleanup_unarmed();kfree(workspace);','f338_ipc_exit();f332_hw_cleanup_unarmed();kfree(workspace);')
 s=s.replace('F332 OEM pipeline provider','F338 GPL kernel and userspace OEM pipeline provider')
 P.write_bytes(s.encode())
if __name__=='__main__':main()
