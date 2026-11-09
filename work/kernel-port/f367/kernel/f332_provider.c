// SPDX-License-Identifier: GPL-2.0-only
/* F332 provider: GPL ownership/control plane, GPL math postfilter and a separate userspace service.
 * A disabled artifact cannot acquire MMIO or confer DFS authority on import.
 */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/workqueue.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/slab.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/errno.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/capability.h>
#include <radar/detect.h>
#include <radar/radar.h>
#include "f327_oem_requests.h"
#include "f332_events.h"
#include "f338_pipeline.h"
#include "f332_hardware.h"
#include "f338_ipc.h"
#include "f367_build_gate.h"
#define F332_POLL_MS 50
static bool hardware_enable,diagnostic_capture,authoritative_enable;
module_param(hardware_enable,bool,0444);
module_param(diagnostic_capture,bool,0444);
module_param(authoritative_enable,bool,0444);
MODULE_PARM_DESC(hardware_enable,"Explicit physical gate; false leaves all MMIO unopened");
MODULE_PARM_DESC(diagnostic_capture,"Acquire and evaluate without DFS callback authority");
MODULE_PARM_DESC(authoritative_enable,"Rejected until a separately qualified release artifact");
static DEFINE_SPINLOCK(request_lock);
static DEFINE_MUTEX(state_lock);
static struct f327_oem_requests requests;
static struct f332_events events;
static struct delayed_work poll_work;
static struct work_struct availability_work;
static void (*availability_callback)(uint32_t,uint32_t);
static bool loss_pending,loss_running,callbacks_closing;
static bool transaction_running; /* state_lock; excludes direct radar_start. */
static bool diagnostic_stopped,pm_active;
static unsigned long pm_attempts,pm_acquisitions,pm_releases,pm_busy;
static uint32_t loss_generation,loss_reason;
static void (*dfs_callback)(void);
static bool (*is_dfs_channel)(uint8_t),(*is_weather_channel)(uint8_t);
static void (*stats_callback)(void*,int(*)(void*,void*,int),void*,int);
static void *stats_argument;
static struct shared_params *owner_shared;
extern struct shared_params *soc_shared_params;
/* Exact initial OEM BSS values, not substitutes for an absent producer. */
static struct detect_drv_sample_t driver_sample={.lock=__SPIN_LOCK_UNLOCKED(driver_sample.lock)};
static struct radar_ocac_info_s ocac={.lock=__SPIN_LOCK_UNLOCKED(ocac.lock)};
static bool ready,started,sta_required,pinned,rate_source_initialized,sample_source_registered,engine_fault_latched;
static uint8_t requested_scan_channel;
static uint64_t applied_request_epoch;
static int last_error;
static unsigned long callbacks,polls;
struct f332_workspace {
 struct f332_pipeline pipeline;
 struct f332_capture capture;
 struct f332_pipeline_result result;
 struct f332_ocac_state ocac_state;
 struct f338_job job;
 struct f338_reply reply;
};
static struct f332_workspace *workspace;
static bool f341_duty_acquire(uint32_t generation)
{
 pm_attempts++;
 if(!f332_hw_duty_acquire(generation)){pm_busy++;return false;}
 pm_acquisitions++;WRITE_ONCE(pm_active,true);return true;
}
static void f341_duty_release(void)
{f332_hw_duty_release();pm_releases++;WRITE_ONCE(pm_active,false);}
/* Availability is distinct from radar detection: no NOP is created. */
static void availability_worker(struct work_struct *unused)
{
 unsigned long flags;void (*cb)(uint32_t,uint32_t);uint32_t gen,reason;bool again;(void)unused;
 for(;;){
  spin_lock_irqsave(&request_lock,flags);
  if(!loss_pending){spin_unlock_irqrestore(&request_lock,flags);break;}
  loss_pending=false;loss_running=true;gen=loss_generation;reason=loss_reason;cb=callbacks_closing?0:availability_callback;
  spin_unlock_irqrestore(&request_lock,flags);
  if(cb)cb(gen,reason);
  spin_lock_irqsave(&request_lock,flags);loss_running=false;again=requests.started&&!callbacks_closing;
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
 /* Queue while holding the admission lock: teardown sets closing under
  * this same lock, then joins, so close cannot enqueue a late callback. */
 if(!callbacks_closing)schedule_work(&availability_work);
 spin_unlock_irqrestore(&request_lock,flags);
 f338_ipc_wake();
}
int radar_register_availability(void(*cb)(uint32_t,uint32_t))
{
 unsigned long flags;spin_lock_irqsave(&request_lock,flags);availability_callback=cb;
 if(cb)callbacks_closing=false;
 if(!cb)ready=false;
 spin_unlock_irqrestore(&request_lock,flags);return 0;
}
static uint32_t ticks200(u64 n)
{
 uint32_t rem=0,q=0;unsigned i;
 for(i=64;i;i--){uint32_t bit=i>32?((uint32_t)(n>>32)>>(i-33))&1U:((uint32_t)n>>(i-1))&1U;rem=(rem<<1)|bit;q<<=1;if(rem>=5000000U){rem-=5000000U;q|=1;}}
 return q;
}
int f332_provider_current(uint32_t gen)
{
 unsigned long flags;bool context_ok;
 spin_lock_irqsave(&request_lock,flags);
 context_ok=!requests.exhausted&&requests.epoch<=0xffffffffULL&&requests.epoch==gen;
 spin_unlock_irqrestore(&request_lock,flags);return context_ok;
}
static int backend_current(void*unused,uint32_t gen){(void)unused;return f332_provider_current(gen);}
static bool runtime_context_supported(void)
{
 return owner_shared&&owner_shared==READ_ONCE(soc_shared_params);
}
static bool sample(int32_t *rate)
{
 unsigned long flags;int bytes;
 if(!READ_ONCE(sample_source_registered))return false;
 spin_lock_irqsave(&driver_sample.lock,flags);bytes=driver_sample.tx_bytes;spin_unlock_irqrestore(&driver_sample.lock,flags);
 *rate=bytes;return true;
}
static int context_begin(const struct f327_oem_requests*w,bool bootstrap)
{
 struct f332_backend backend={0,backend_current,f332_hw_reset};
 /* These are the exact EU profile fields; builder binds the 300-byte profile
  * and rechecks the detector configuration before any release promotion. */
 const struct f332_hw_profile profile={120,28,4,360,false};
 uint64_t epoch;uint32_t base;int rc;bool dfs=false;unsigned long flags;uint8_t scan;
 if(!f338_ipc_available())return -ENOTCONN;
 if(w->epoch>0xffffffffULL||(!bootstrap&&w->registrations!=7)||!runtime_context_supported())return -EAGAIN;
 rc=f332_events_transition(&events,&epoch);if(rc)return -EBUSY;
 if(workspace->pipeline.initialized){rc=f332_pipeline_end(&workspace->pipeline);if(rc)return -EIO;}
 if(!pinned){if(!try_module_get(THIS_MODULE))return -ENODEV;pinned=true;}
 rc=f332_hw_open((uint32_t)w->epoch,hardware_enable,w->bandwidth,&profile,bootstrap,&base);if(rc)return rc;
 spin_lock_irqsave(&ocac.lock,flags);ocac.array_ps=0;scan=ocac.ocac_scan_chan;spin_unlock_irqrestore(&ocac.lock,flags);
 {bool weather=workspace->ocac_state.weather;memset(&workspace->ocac_state,0,sizeof(workspace->ocac_state));workspace->ocac_state.previous_status=2;workspace->ocac_state.weather=weather;}
 if(bootstrap){workspace->pipeline.generation=0;memset(&workspace->pipeline.rate,0,sizeof(workspace->pipeline.rate));workspace->pipeline.poll_counter=0;workspace->pipeline.rate_ready=false;}
 rc=f332_pipeline_begin(&workspace->pipeline,(uint32_t)w->epoch,w->channel,w->bandwidth,base,ticks200(ktime_get_ns()),0,&backend);if(rc)return -EIO;
 sta_required=true; /* Exact EU profile byte1=1, validated by first service reply. */
 if(is_dfs_channel)dfs=is_dfs_channel((uint8_t)w->channel);
 if(!dfs&&scan&&is_dfs_channel)dfs=is_dfs_channel(scan);
 rc=f332_events_commit(&events,epoch,w->channel,w->bandwidth,!bootstrap&&f332_hw_ready(),dfs,
  F367_NATIVE_AUTHORITY_BUILD&&authoritative_enable&&w->started&&w->enable_requested&&dfs);
 if(rc)return -EIO;
 applied_request_epoch=w->epoch;return 0;
}
static void stop_request(bool stopping)
{
 unsigned long flags;bool observe;
 spin_lock_irqsave(&request_lock,flags);f327_oem_disable(&requests,stopping);ready=false;if(stopping)started=false;observe=!stopping&&requests.started&&diagnostic_capture&&hardware_enable;spin_unlock_irqrestore(&request_lock,flags);
 /* OEM nonblocking stop: an admitted callback may return after disable. */
 f338_ipc_wake();
 cancel_delayed_work(&poll_work);
 if(observe)mod_delayed_work(system_wq,&poll_work,msecs_to_jiffies(F332_POLL_MS));
}
static int stats_copy(void*dst,void*src,int index)
{
 if(!dst||!src||index<0||index>=256)return -EINVAL;
 /* OEM 03f4..043a copies start/stop/power only, returns 12 bytes. */
 memcpy(dst,(struct f333_raw*)src+index,12);return 12;
}
static int capture_with_ocac(const struct f327_oem_requests*w)
{
 struct f332_ocac_point points[10];unsigned count,n;unsigned long flags;
 uint32_t current_ptr=0;uint8_t scan;bool home_dfs,weather,need_current;int rc;
 home_dfs=is_dfs_channel&&is_dfs_channel((uint8_t)w->channel);
 spin_lock_irqsave(&ocac.lock,flags);
 count=ocac.array_ps;scan=ocac.ocac_scan_chan;
 if(count>10){spin_unlock_irqrestore(&ocac.lock,flags);return -EOVERFLOW;}
 for(n=0;n<count;n++){points[n].status=ocac.ocac_radar_pts[n].ocac_status;points[n].fifo_pointer=ocac.ocac_radar_pts[n].fifo_pt;}
 weather=is_weather_channel&&is_weather_channel(scan);
 need_current=!home_dfs&&(count?points[count-1].status:workspace->ocac_state.previous_status)==2;
 if(need_current){rc=f332_hw_point(&current_ptr);if(rc){spin_unlock_irqrestore(&ocac.lock,flags);return rc;}}
 rc=f332_ocac_prepare(&workspace->ocac_state,points,count,home_dfs,weather,!need_current||current_ptr<256,current_ptr);
 if(rc){spin_unlock_irqrestore(&ocac.lock,flags);return -EINVAL;}
 ocac.ocac_enabled=workspace->ocac_state.filter;ocac.weather_channel_yes=workspace->ocac_state.weather;
 workspace->capture.ocac_filter=workspace->ocac_state.filter;
 workspace->capture.ocac_weather=workspace->ocac_state.weather;
 workspace->capture.ocac_scan_channel=scan;
 /* Producer uses ocac.lock -> BB in its tasklet. Keep the same lock order;
  * release before preprocessing, classifier code or external callbacks. */
 rc=f332_hw_capture((uint32_t)w->epoch,&workspace->capture,&workspace->ocac_state);
 if(!rc){ocac.array_ps=0;f332_ocac_consume(&workspace->ocac_state);}
 spin_unlock_irqrestore(&ocac.lock,flags);return rc;
}
static void worker(struct work_struct*unused)
{
 struct f327_oem_requests wanted;struct f332_token token,event;struct f332_frame frame;
 struct timespec64 now;unsigned long flags;bool arm,rate_ok,context_ok,duty_acquired=false;
 void (*callback)(void)=0;
 void (*readyfn)(uint32_t,uint32_t)=0;uint32_t readygen=0;bool was_ready;
 void (*statfn)(void*,int(*)(void*,void*,int),void*,int)=0;void *statarg=0;
 int rc;int32_t rate=0;(void)unused;
 spin_lock_irqsave(&request_lock,flags);wanted=requests;arm=wanted.started&&(diagnostic_capture||wanted.enable_requested);spin_unlock_irqrestore(&request_lock,flags);
 if(!arm||!hardware_enable||wanted.exhausted)return;
 /* qdrv registers callbacks AFTER radar_start returns successfully. */
 if(wanted.registrations!=7||!f338_ipc_available()||READ_ONCE(loss_pending)||READ_ONCE(loss_running))goto reschedule;
 mutex_lock(&state_lock);
 if(!runtime_context_supported()){rc=-EOPNOTSUPP;goto fail;}
 /* OEM 3b2c..3b3a holds PM duty across the whole worker, separately from
  * the shorter BB reader sections; a busy PM owner postpones this poll. */
 if(!f341_duty_acquire((uint32_t)wanted.epoch)){mutex_unlock(&state_lock);goto reschedule;}
 duty_acquired=true;
 if(applied_request_epoch!=wanted.epoch||events.phase!=F332_ACTIVE){rc=context_begin(&wanted,false);if(rc)goto fail;}
 /* qdrv obtains the shared sample AFTER radar_start. The initial zero is
  * the actual initialized OEM object; do not wait an invented full interval. */
 rate_ok=sample(&rate);rate_source_initialized=rate_ok;if(!rate_ok){mutex_unlock(&state_lock);goto reschedule;}
 rc=f332_events_capture(&events,&token);if(rc)goto fail;
 rc=capture_with_ocac(&wanted);
 if(rc)goto discard;
 spin_lock_irqsave(&request_lock,flags);context_ok=f327_oem_current(&requests,&wanted);if(context_ok){statfn=stats_callback;statarg=stats_argument;}spin_unlock_irqrestore(&request_lock,flags);
 if(!context_ok){rc=-ESTALE;goto discard;}
 /* Stats delivery is a separate OEM observer, before preprocessing. */
 if(statfn&&statarg){
  transaction_running=true;mutex_unlock(&state_lock);
  statfn(statarg,stats_copy,workspace->capture.raw,workspace->capture.raw_meta.captured_count);
  mutex_lock(&state_lock);transaction_running=false;
  if(!f332_provider_current((uint32_t)wanted.epoch)){rc=-ESTALE;goto discard;}
 }
 ktime_get_real_ts64(&now);
 if(now.tv_sec<0||now.tv_sec>0x7fffffff){rc=-ERANGE;goto discard;}
 memset(&frame,0,sizeof(frame));frame.generation=(uint32_t)wanted.epoch;frame.channel=wanted.channel;frame.bandwidth=wanted.bandwidth;
 frame.legacy_ticks=ticks200(ktime_get_ns());frame.seconds=(int32_t)now.tv_sec;frame.microseconds=(int32_t)(now.tv_nsec/1000);
 frame.raw=(const struct f332_pulse*)workspace->capture.raw;frame.raw_count=workspace->capture.raw_meta.preprocess_count;frame.zc=&workspace->capture.zc;
 frame.raw_valid=workspace->capture.raw_valid;frame.zc_association_valid=workspace->capture.zc_valid;frame.rate_valid=rate_ok;frame.tx_bytes_per_second=rate;frame.callback_registered=wanted.registrations==7;
 frame.ocac_filter=workspace->capture.ocac_filter;frame.ocac_weather=workspace->capture.ocac_weather;frame.ocac_scan_channel=workspace->capture.ocac_scan_channel;
 rc=f338_pipeline_make_job(&workspace->pipeline,&frame,&workspace->job,&workspace->result);
 if(rc)goto discard;
 /* The worker alone owns PM. There is NO BB or state_lock across IPC.
  * A reset RPC wakes this worker and is performed before its PM release. */
 transaction_running=true;mutex_unlock(&state_lock);
 rc=f338_ipc_exchange(&workspace->job,&workspace->reply,f332_provider_current,f332_hw_reset);
 mutex_lock(&state_lock);transaction_running=false;
 if(!rc&&!f332_provider_current((uint32_t)wanted.epoch))rc=-ESTALE;
 if(!rc)rc=f338_pipeline_finish(&workspace->pipeline,&frame,&workspace->reply,&workspace->result);
 polls++;
 if(rc)goto discard;
 rc=f332_events_complete(&events,&token,workspace->result.callback_condition,&event);
 if(rc<0){rc=-EIO;goto fail;}
 last_error=0;
 spin_lock_irqsave(&request_lock,flags);
 context_ok=f327_oem_current(&requests,&wanted);
 if(context_ok)(void)f327_oem_apply(&requests,&wanted);
 if(rc==1&&dfs_callback&&f327_oem_callback_allowed(&requests,&wanted,F367_NATIVE_AUTHORITY_BUILD&&authoritative_enable)&&!f332_events_dispatch(&events,&event))callback=dfs_callback;
 was_ready=ready;
 ready=context_ok&&!loss_pending&&!loss_running&&availability_callback&&workspace->result.postfilter_applied&&f332_hw_ready()&&
  f327_oem_callback_allowed(&requests,&wanted,F367_NATIVE_AUTHORITY_BUILD&&authoritative_enable);
 if(ready&&!was_ready){readyfn=availability_callback;readygen=(uint32_t)wanted.epoch;}
 spin_unlock_irqrestore(&request_lock,flags);
 mutex_unlock(&state_lock);
 if(readyfn)readyfn(readygen,F338_SERVICE_READY);
 if(callback){callback();mutex_lock(&state_lock);callbacks++;(void)f332_events_return(&events,&event);mutex_unlock(&state_lock);}
 goto reschedule;
discard:
 (void)f332_events_complete(&events,&token,false,&event);
fail:
 if(rc==-ESTALE||rc==-ENOTCONN||rc==-ETIMEDOUT||rc==-EPROTO){
  /* Valid channel/width/registration changes retire only the old batch.
   * Preserve started and the latest request; do not kill the new epoch. */
  if(rc!=-ESTALE&&rc!=-ENOTCONN)service_lost(rc==-ETIMEDOUT?F338_SERVICE_TIMEOUT:F338_SERVICE_PROTOCOL);
  last_error=rc;ready=false;events.phase=F332_OFF;
  mutex_unlock(&state_lock);goto reschedule;
 }
 service_lost(F338_HARDWARE_FAULT);
 engine_fault_latched=true;
 last_error=rc;ready=false;events.phase=F332_FAULT;
 /* A failed epoch is terminal. Diagnostic mode must not turn a hardware or
  * reset failure into an automatic reconfiguration/retry loop. */
 mutex_unlock(&state_lock);if(duty_acquired)f341_duty_release();stop_request(true);return;
reschedule:
 if(duty_acquired)f341_duty_release();
 spin_lock_irqsave(&request_lock,flags);arm=requests.started&&(diagnostic_capture||requests.enable_requested);spin_unlock_irqrestore(&request_lock,flags);
 if(arm)schedule_delayed_work(&poll_work,msecs_to_jiffies(F332_POLL_MS));
}
static void registration_changed(unsigned bit,bool present)
{
 (void)f327_oem_invalidate(&requests);if(present)requests.registrations|=bit;else requests.registrations&=~bit;ready=false;
}
int radar_register(void(*cb)(void)){unsigned long f;spin_lock_irqsave(&request_lock,f);dfs_callback=cb;registration_changed(1,!!cb);spin_unlock_irqrestore(&request_lock,f);return 0;}
int radar_register_is_dfs_chan(bool(*cb)(uint8_t)){unsigned long f;spin_lock_irqsave(&request_lock,f);is_dfs_channel=cb;registration_changed(2,!!cb);spin_unlock_irqrestore(&request_lock,f);return 0;}
int radar_register_is_dfs_weather_chan(bool(*cb)(uint8_t)){unsigned long f;spin_lock_irqsave(&request_lock,f);is_weather_channel=cb;registration_changed(4,!!cb);spin_unlock_irqrestore(&request_lock,f);return 0;}
void radar_disable(void){stop_request(false);}
void radar_stop(void){stop_request(true);}
void radar_enable(void){unsigned long f;bool accepted=false;spin_lock_irqsave(&request_lock,f);if(!requests.enable_requested&&(diagnostic_capture||(F367_NATIVE_AUTHORITY_BUILD&&authoritative_enable))){accepted=f327_oem_enable(&requests);if(accepted)ready=false;}spin_unlock_irqrestore(&request_lock,f);if(accepted)mod_delayed_work(system_wq,&poll_work,0);}
bool radar_start(const char*region)
{
 struct f327_oem_requests wanted;unsigned long flags;int rc;
 if(!region||(strcasecmp(region,"eu")&&strcasecmp(region,"es"))||!hardware_enable||engine_fault_latched||READ_ONCE(diagnostic_stopped)||in_atomic()||irqs_disabled())return false;
 mutex_lock(&state_lock);
 if(transaction_running){mutex_unlock(&state_lock);return false;}
 spin_lock_irqsave(&request_lock,flags);(void)f327_oem_invalidate(&requests);wanted=requests;if(!owner_shared)owner_shared=READ_ONCE(soc_shared_params);spin_unlock_irqrestore(&request_lock,flags);
 /* Bootstrap initializes hardware/engines but does not publish ACTIVE;
  * callback registration and the first verified batch are separate gates. */
 rc=context_begin(&wanted,true);
 spin_lock_irqsave(&request_lock,flags);
 if(!rc&&!f327_oem_current(&requests,&wanted))rc=-ESTALE;
 if(!rc){requests.started=true;started=true;}else if(rc!=-ESTALE){requests.started=false;started=false;ready=false;}else{started=requests.started;ready=false;}
 spin_unlock_irqrestore(&request_lock,flags);last_error=rc;mutex_unlock(&state_lock);
 if(!rc&&diagnostic_capture)mod_delayed_work(system_wq,&poll_work,0);
 return !rc;
}
int radar_set_chan(uint8_t channel){unsigned long f;bool ok,changed;uint64_t old;if(channel!=36&&channel!=52)return -EPERM;spin_lock_irqsave(&request_lock,f);old=requests.epoch;ok=f327_oem_channel(&requests,channel);changed=old!=requests.epoch;if(changed)ready=false;spin_unlock_irqrestore(&request_lock,f);if(changed&&hardware_enable)mod_delayed_work(system_wq,&poll_work,0);return ok?0:-EINVAL;}
void radar_set_bw(uint32_t bw){unsigned long f;bool changed;uint64_t old;if(bw!=20&&bw!=40&&bw!=80)return;spin_lock_irqsave(&request_lock,f);old=requests.epoch;(void)f327_oem_bandwidth(&requests,bw);changed=old!=requests.epoch;if(changed)ready=false;spin_unlock_irqrestore(&request_lock,f);if(changed&&hardware_enable)mod_delayed_work(system_wq,&poll_work,0);}
int radar_set_scan_context(uint8_t channel)
{
 unsigned long outer,inner;bool changed=false;
 if(channel)return -EPERM; /* F341 only observes the non-DFS home channel36. */
 spin_lock_irqsave(&ocac.lock,outer);
 spin_lock_irqsave(&request_lock,inner);
 if(requested_scan_channel!=channel){requested_scan_channel=channel;ocac.ocac_scan_chan=channel;(void)f327_oem_invalidate(&requests);ready=false;changed=true;}
 spin_unlock_irqrestore(&request_lock,inner);spin_unlock_irqrestore(&ocac.lock,outer);
 if(changed&&hardware_enable)mod_delayed_work(system_wq,&poll_work,0);
 return 0;
}
uint32_t radar_ready_generation(void)
{
 unsigned long flags;uint32_t gen=0;
 spin_lock_irqsave(&request_lock,flags);
 if(ready&&!requests.exhausted&&requests.epoch<=0xffffffffULL&&requests.applied_epoch==requests.epoch)gen=(uint32_t)requests.epoch;
 spin_unlock_irqrestore(&request_lock,flags);return gen;
}
int radar_wait_stopped(void)
{
 unsigned long flags;int rc=0;
 if(in_atomic()||irqs_disabled())return -EWOULDBLOCK;
 if(current_work()==&poll_work.work||current_work()==&availability_work)return -EDEADLK;
 spin_lock_irqsave(&request_lock,flags);callbacks_closing=true;spin_unlock_irqrestore(&request_lock,flags);
 stop_request(true);cancel_delayed_work_sync(&poll_work);cancel_work_sync(&availability_work);f338_ipc_cancel();
 mutex_lock(&state_lock);
 if(workspace->pipeline.initialized)rc=f332_pipeline_end(&workspace->pipeline);
 spin_lock_irqsave(&request_lock,flags);
 availability_callback=0;loss_pending=loss_running=false;
 dfs_callback=0;is_dfs_channel=0;is_weather_channel=0;stats_callback=0;stats_argument=0;
 requests.registrations=0;ready=false;owner_shared=0;
 if(rc){last_error=-EIO;engine_fault_latched=true;requests.exhausted=true;}
 spin_unlock_irqrestore(&request_lock,flags);
 events.phase=F332_OFF;f332_hw_retire();mutex_unlock(&state_lock);
 /* Join and caller-pointer removal have succeeded. The synchronous math
  * engine has no kernel timer or IC reference. Report its reset fault in
  * status and reject reuse; do not misreport caller lifetime as undrained. */
 return 0;
}
uint8_t radar_get_chan(void){return READ_ONCE(requests.channel);}
bool radar_get_status(void){return READ_ONCE(ready);}
bool sta_dfs_is_region_required(void){return READ_ONCE(sta_required);}
void radar_set_shared_params(struct shared_params*p){unsigned long f;spin_lock_irqsave(&request_lock,f);owner_shared=p;(void)f327_oem_invalidate(&requests);ready=false;spin_unlock_irqrestore(&request_lock,f);}
struct radar_ocac_info_s *radar_ocac_info_addr_get(void){return &ocac;}
void radar_record_buffer_pt(uint32_t*point){if(point&&f332_hw_point(point))*point=~0U;}
struct detect_drv_sample_t *detect_drv_sample_loc_get(void){WRITE_ONCE(sample_source_registered,true);return &driver_sample;}
int radar_register_statcb(void(*cb)(void*,int(*)(void*,void*,int),void*,int),void*arg){unsigned long f;spin_lock_irqsave(&request_lock,f);stats_callback=cb;stats_argument=arg;spin_unlock_irqrestore(&request_lock,f);return 0;}
unsigned dfs_rqmt_code(const char*s){if(!s)return DFS_RQMT_UNKNOWN;if(!strcasecmp(s,"eu")||!strcasecmp(s,"es"))return DFS_RQMT_EU;if(!strcasecmp(s,"us"))return DFS_RQMT_US;if(!strcasecmp(s,"jp"))return DFS_RQMT_JP;if(!strcasecmp(s,"au"))return DFS_RQMT_AU;if(!strcasecmp(s,"br"))return DFS_RQMT_BR;if(!strcasecmp(s,"cl"))return DFS_RQMT_CL;return DFS_RQMT_UNKNOWN;}
EXPORT_SYMBOL(radar_register);EXPORT_SYMBOL(radar_register_is_dfs_chan);EXPORT_SYMBOL(radar_register_is_dfs_weather_chan);
EXPORT_SYMBOL(radar_disable);EXPORT_SYMBOL(radar_stop);EXPORT_SYMBOL(radar_enable);EXPORT_SYMBOL(radar_start);
EXPORT_SYMBOL(radar_set_chan);EXPORT_SYMBOL(radar_set_bw);EXPORT_SYMBOL(radar_get_chan);EXPORT_SYMBOL(radar_get_status);
EXPORT_SYMBOL(sta_dfs_is_region_required);EXPORT_SYMBOL(radar_set_shared_params);EXPORT_SYMBOL(radar_ocac_info_addr_get);
EXPORT_SYMBOL(radar_record_buffer_pt);EXPORT_SYMBOL(detect_drv_sample_loc_get);EXPORT_SYMBOL(radar_register_statcb);EXPORT_SYMBOL(dfs_rqmt_code);
EXPORT_SYMBOL(radar_set_scan_context);EXPORT_SYMBOL(radar_ready_generation);
EXPORT_SYMBOL(radar_wait_stopped);EXPORT_SYMBOL(radar_register_availability);
static int status_show(struct seq_file*s,void*unused)
{
 struct f341_ipc_stats ipc;
 (void)unused;mutex_lock(&state_lock);
 seq_printf(s,"schema=openmitrastar.f341-provider/v1\nhardware_enabled=%u\nhardware_ready=%u\nhardware_dirty=%u\nrelease_qualified=%u\nstarted=%u\nready=%u\npolls=%lu\ncallbacks=%lu\nlast_error=%d\npostfilter_applied=%u\ncallback_condition=%u\n",hardware_enable,f332_hw_ready(),f332_hw_dirty(),0,started,ready,polls,callbacks,last_error,workspace->result.postfilter_applied,workspace->result.callback_condition);
 seq_puts(s,"disable_contract=oem_nonblocking\nhardware_quiesce_claim=0\nrate_unit=bytes_per_second\n");
 seq_printf(s,"rate_source_registered=%u\nrate_sample_object_readable=%u\nrate_fresh_muc_period_not_attested=1\nreset_sequences_emitted=%u\nhardware_reset_acknowledged=0\n",sample_source_registered,rate_source_initialized,workspace->result.reset_sequences_emitted);
 seq_printf(s,"engine_fault_latched=%u\n",engine_fault_latched);
 seq_printf(s,"diagnostic_stopped=%u\nprofile_channel=52\nchannel=%u\nrequest_generation=%llu\napplied_generation=%llu\npm_active=%u\npm_attempts=%lu\npm_acquisitions=%lu\npm_releases=%lu\npm_busy=%lu\n",diagnostic_stopped,requests.channel,(unsigned long long)requests.epoch,(unsigned long long)requests.applied_epoch,READ_ONCE(pm_active),READ_ONCE(pm_attempts),READ_ONCE(pm_acquisitions),READ_ONCE(pm_releases),READ_ONCE(pm_busy));
 f341_ipc_snapshot(&ipc);
 seq_printf(s,"ipc_session=%u\nipc_sequence=%u\nipc_generation=%u\nipc_state=%u\njobs_queued=%u\njobs_delivered=%u\njobs_replied=%u\njobs_completed=%u\njobs_cancelled=%u\njob_timeouts=%u\nprotocol_errors=%u\nservice_closes=%u\nhardware_errors=%u\nreset_requests=%u\nreset_sequences=%u\nreset_replays=%u\nlast_job_latency_ms=%u\nmax_job_latency_ms=%u\n",ipc.session,ipc.sequence,ipc.generation,ipc.state,ipc.jobs_queued,ipc.jobs_delivered,ipc.jobs_replied,ipc.jobs_completed,ipc.jobs_cancelled,ipc.timeouts,ipc.protocol_errors,ipc.service_closes,ipc.hardware_errors,ipc.reset_requests,ipc.reset_sequences,ipc.reset_replays,ipc.last_latency_ms,ipc.max_latency_ms);
 mutex_unlock(&state_lock);return 0;
}
static ssize_t diagnostic_control(struct file*f,const char __user*input,size_t count,loff_t*position)
{
 char command[16];int rc;(void)f;(void)position;
 if(!capable(CAP_SYS_ADMIN))return -EPERM;
 if(count!=sizeof(command))return -EINVAL;
 if(copy_from_user(command,input,count))return -EFAULT;
 if(memcmp(command,"STOP_DIAGNOSTIC\n",sizeof(command)))return -EINVAL;
 WRITE_ONCE(diagnostic_stopped,true);rc=radar_wait_stopped();
 /* Software drain only. A dirty producer is never claimed stopped, and
  * the module remains self-pinned until the watchdog/recovery reboot. */
 return rc?rc:count;
}
static const struct proc_ops control_ops={.proc_write=diagnostic_control};
static int status_open(struct inode*i,struct file*f){return single_open(f,status_show,0);}
static const struct proc_ops status_ops={.proc_open=status_open,.proc_read=seq_read,.proc_lseek=seq_lseek,.proc_release=single_release};
static int __init provider_init(void)
{
 int rc;
 BUILD_BUG_ON(sizeof(struct f333_raw)!=sizeof(struct f332_pulse));
 BUILD_BUG_ON(sizeof(struct f332_zc)!=21956);
 BUILD_BUG_ON(offsetof(struct detect_drv_sample_t,tx_bytes)!=offsetof(struct detect_drv_sample_t,tx_pkts)+4);
 if(authoritative_enable&&!F367_NATIVE_AUTHORITY_BUILD)return -EPERM;
 workspace=kzalloc(sizeof(*workspace),GFP_KERNEL);if(!workspace)return -ENOMEM;
 f327_oem_init(&requests,36,80);INIT_DELAYED_WORK(&poll_work,worker);INIT_WORK(&availability_work,availability_worker);
 rc=f338_ipc_init(service_lost);if(rc){kfree(workspace);return rc;}
 if(!proc_mkdir("openmitrastar_radar_f367",0)||!proc_create("openmitrastar_radar_f367/status",0400,0,&status_ops)||!proc_create("openmitrastar_radar_f367/control",0200,0,&control_ops)){remove_proc_subtree("openmitrastar_radar_f367",0);f338_ipc_exit();kfree(workspace);return -ENOMEM;}
 return 0;
}
static void __exit provider_exit(void)
{
 unsigned long flags;
 spin_lock_irqsave(&request_lock,flags);callbacks_closing=true;spin_unlock_irqrestore(&request_lock,flags);
 stop_request(true);cancel_delayed_work_sync(&poll_work);cancel_work_sync(&availability_work);
 remove_proc_subtree("openmitrastar_radar_f367",0);
 if(workspace->pipeline.initialized)(void)f332_pipeline_end(&workspace->pipeline);
 f338_ipc_exit();f332_hw_cleanup_unarmed();kfree(workspace);
}
module_init(provider_init);module_exit(provider_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("F367 experimental AP52 DFS: GPL kernel, original userspace OEM engine, gated build");
