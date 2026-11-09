/* Research-only F332 reference. Never linked into the F338 kernel/service. */
#include <string.h>
#include "f332_pipeline.h"
#include "oracle_contract.h"
static struct f332_pipeline pipeline;
static struct f332_frame frame;
static struct f332_zc zc;
static struct f330_raw raw[128];
static uint32_t generation;
static int epoch(void*ctx,uint32_t gen){(void)ctx;return generation==gen;}
static int reset(void*ctx,uint32_t gen,uint32_t id,int32_t*sec,int32_t*usec)
{(void)ctx;if(gen!=generation||!id)return -1;*sec=frame.seconds;*usec=frame.microseconds+1;return 0;}
int f338_reference_step(const struct f338_job*j,struct f338_probe*out)
{
 struct f332_backend backend={0,epoch,reset};struct f332_pipeline_result r;unsigned n;int rc;
 generation=j->h.generation;
 if(!pipeline.initialized||pipeline.generation!=generation){
  if(pipeline.initialized)f332_pipeline_end(&pipeline);
  if(f332_pipeline_begin(&pipeline,generation,j->channel,j->bandwidth,j->timestamp_base,j->legacy_ticks,0,&backend))return -1;
 }
 memset(&frame,0,sizeof(frame));
 frame.generation=generation;frame.channel=j->channel;frame.bandwidth=j->bandwidth;frame.legacy_ticks=j->legacy_ticks;frame.seconds=j->real_seconds;frame.microseconds=j->real_microseconds;
 frame.raw=raw;frame.raw_count=j->raw_count;frame.zc=&zc;memcpy(zc.samples,j->zc,sizeof(zc.samples));zc.accurate=j->zc_accurate;
 frame.raw_valid=frame.zc_association_valid=frame.rate_valid=frame.callback_registered=true;
 frame.tx_bytes_per_second=j->tx_bytes_per_second;frame.ocac_filter=!!(j->flags&F338_JOB_OCAC);frame.ocac_weather=!!(j->flags&F338_JOB_WEATHER);frame.ocac_scan_channel=j->scan_channel;
 for(n=0;n<j->raw_count;n++){raw[n].start=j->raw[n].start;raw[n].stop=j->raw[n].stop;raw[n].max_power=j->raw[n].max_power;raw[n].tagged=j->raw[n].tagged;}
 rc=f332_pipeline_run(&pipeline,&frame,&r);if(rc)return rc;
 memset(out,0,sizeof(*out));out->total=r.total_count;out->current_count=r.current_window_count;out->poll=r.poll_counter;out->candidate=r.candidate_detected;out->flushes=r.flushes;out->resets=r.reset_sequences_emitted;out->callback=r.callback_condition;
 out->cfg_hash=f338_hash(pipeline.detection.configuration,300);out->stats_hash=f338_hash(pipeline.detection.statistics,700);out->history_hash=f338_hash(&pipeline.postfilter,sizeof(pipeline.postfilter));out->rate_hash=f338_hash(&pipeline.rate,sizeof(pipeline.rate));return 0;
}
void f338_reference_end(void){if(pipeline.initialized)f332_pipeline_end(&pipeline);}
