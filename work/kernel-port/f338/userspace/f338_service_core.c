/* Linux userspace only. Calls the unchanged F328/F330 OEM projections through
 * GP-preserving ARC thunks. No GPL postfilter object is linked here. */
#include <string.h>
#include "f338_service_core.h"
#include "f332_detector.h"
#include "f330_preprocess.h"
static struct f330_raw raw[128];
static struct f330_result prepared,scratch;
static struct f332_detection detection;
static struct f332_zc crossing;
static uint32_t active_session,active_generation,last_generation,last_sequence,active_channel,active_bandwidth;
static int overload_reset,fault;
static uint32_t le32(const unsigned char*c,unsigned off)
{return (uint32_t)c[off]|(uint32_t)c[off+1]<<8|(uint32_t)c[off+2]<<16|(uint32_t)c[off+3]<<24;}
static int valid(const struct f338_job*j)
{
 unsigned n;
 if(!j||j->h.magic!=F338_MAGIC||j->h.abi!=F338_ABI||j->h.size!=sizeof(*j)||!j->h.session||!j->h.sequence||!j->h.generation||
 !j->channel||j->channel>196||(j->bandwidth!=20&&j->bandwidth!=40&&j->bandwidth!=80)||j->scan_channel>196||
 (j->flags&~15U)||j->raw_count>128||j->zc_accurate>1||j->real_seconds<0||j->real_microseconds<0||j->real_microseconds>=1000000||
 !!(j->flags&F338_JOB_POLL_DETECTOR)!=(j->poll_counter%50==0))return 0;
 for(n=0;n<j->raw_count;n++)if(j->raw[n].tagged>1)return 0;
 return 1;
}
static int prepare(const struct f338_job*j,struct f338_reply*r,const struct f330_raw*input,unsigned count,struct f330_result*out,f338_reset_rpc rpc,void*context)
{
 struct f338_reset reset;int rc,rpc_rc;
 rc=f330_prepare(j->h.generation,input,count,j->real_seconds,j->real_microseconds,out);
 if(rc==F330_RESET_REQUIRED){
  if(r->reset_sequences>=F338_RESET_MAX)return -1;
  memset(&reset,0,sizeof(reset));reset.h=j->h;reset.h.size=sizeof(reset);reset.request_id=out->request_id;
  rpc_rc=rpc?rpc(context,&reset):F338_ENGINE_FAILED;
  if(rpc_rc==F338_ENGINE_CANCELED){(void)f330_confirm_reset(j->h.generation,out->request_id,0,0,0,out);return F338_ENGINE_CANCELED;}
  if(rpc_rc||reset.h.magic!=F338_MAGIC||reset.h.abi!=F338_ABI||reset.h.size!=sizeof(reset)||reset.h.session!=j->h.session||
   reset.h.sequence!=j->h.sequence||reset.h.generation!=j->h.generation||reset.request_id!=out->request_id||reset.sequence_emitted!=1||
   reset.actual_seconds<0||reset.actual_microseconds<0||reset.actual_microseconds>=1000000){
   (void)f330_confirm_reset(j->h.generation,out->request_id,0,0,0,out);return -1;
  }
  r->reset_sequences++;
  rc=f330_confirm_reset(j->h.generation,out->request_id,1,reset.actual_seconds,reset.actual_microseconds,out);
 }
 return rc==F330_OK&&out->committed&&!out->abi_fault?0:-1;
}
void f338_engine_close(void)
{
 if(active_generation)(void)f332_detect_end(active_generation);
 active_generation=active_session=last_generation=last_sequence=active_channel=active_bandwidth=0;overload_reset=fault=0;
}
void f338_engine_cancel(void)
{
 if(active_generation)(void)f332_detect_end(active_generation);
 /* Remember sequence/session to reject replay, but retire mutable math. */
 active_generation=0;overload_reset=0;
}
int f338_engine_job(const struct f338_job*j,struct f338_reply*r,f338_reset_rpc rpc,void*context)
{
 unsigned n;int rc,overload;
 if(!r)return -1;
 memset(r,0,sizeof(*r));if(j){r->h=j->h;r->h.size=sizeof(*r);}r->status=F338_WIRE_INPUT;
 if(!valid(j)||fault)return -1;
 /* Undelivered jobs can be canceled by a legitimate channel setter. The
  * kernel never wraps a session's sequence; gaps are valid, replay is not. */
 if(active_session==j->h.session&&j->h.sequence<=last_sequence)return -1;
 if(active_session==j->h.session&&j->h.generation<last_generation)return -1;
 if(active_generation==j->h.generation&&active_session==j->h.session&&(active_channel!=j->channel||active_bandwidth!=j->bandwidth))return -1;
 if(active_generation!=j->h.generation||active_session!=j->h.session){
  if(active_generation)(void)f332_detect_end(active_generation);
  active_generation=0;
  if(f332_detect_begin(j->h.generation,j->channel,j->bandwidth,j->legacy_ticks)||f330_begin(j->h.generation,j->timestamp_base,!!(j->flags&F338_JOB_TAG)))goto failed;
  active_generation=j->h.generation;active_session=j->h.session;active_channel=j->channel;active_bandwidth=j->bandwidth;overload_reset=0;
 }
 last_sequence=j->h.sequence;last_generation=j->h.generation;
 if(f332_detect_environment(j->h.generation,!!(j->flags&F338_JOB_OCAC),j->scan_channel,!!(j->flags&F338_JOB_WEATHER)))goto failed;
 for(n=0;n<j->raw_count;n++){
  raw[n].start=j->raw[n].start;raw[n].stop=j->raw[n].stop;raw[n].max_power=j->raw[n].max_power;
  raw[n].tagged=(unsigned char)j->raw[n].tagged;memset(raw[n].pad,0,3);
 }
 rc=prepare(j,r,raw,j->raw_count,&prepared,rpc,context);if(rc==F338_ENGINE_CANCELED)goto canceled;if(rc)goto failed;
 r->total_count=prepared.total_count;r->current_window_count=prepared.current_window_count;
 if(f332_detect_snapshot(j->h.generation,&detection))goto failed;
 overload=prepared.total_count>=le32(detection.configuration,256)||j->tx_bytes_per_second>=(int32_t)le32(detection.configuration,228);
 if(overload){
  if(!overload_reset&&detection.configuration[214]){if(f332_detect_reset(j->h.generation))goto failed;overload_reset=1;}
  if(f332_detect_snapshot(j->h.generation,&detection))goto failed;
  detection.candidate=0;detection.configuration[215]=0;
 }else{
  memcpy(crossing.samples,j->zc,sizeof(crossing.samples));crossing.accurate=(unsigned char)j->zc_accurate;memset(crossing.reserved,0,3);
  if(f332_detect_step(j->h.generation,(const struct f332_pulse*)prepared.pulses,prepared.total_count,prepared.current_window_count,
    prepared.zc_source_index,&crossing,!!(j->flags&F338_JOB_POLL_DETECTOR),j->legacy_ticks,&detection))goto failed;
  overload_reset=0;
 }
 r->candidate=!!detection.candidate;
 /* Save detector data and original counts BEFORE both OEM empty flushes. */
 memcpy(r->configuration,detection.configuration,300);memcpy(r->statistics,detection.statistics,700);
 if(r->candidate)for(n=0;n<2;n++){rc=prepare(j,r,0,0,&scratch,rpc,context);if(rc==F338_ENGINE_CANCELED)goto canceled;if(rc)goto failed;r->flushes++;}
 r->status=F338_WIRE_OK;return 0;
canceled:
 f338_engine_cancel();r->status=F338_WIRE_CANCELED;return F338_ENGINE_CANCELED;
failed:
 fault=1;r->status=F338_WIRE_ENGINE;return -1;
}
