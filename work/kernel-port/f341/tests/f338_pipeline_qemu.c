/* Private oracle, never a deployable service: exercises the real UAPI math
 * composition against the previously qualified original-byte F332 pipeline. */
#include <string.h>
#include "f338_pipeline.h"
#include "f338_service_core.h"
#include "f330_preprocess.h"
#include "oracle_contract.h"
#define COUNT 180
static struct f338_job input,job;
static struct f338_reply reply;
static struct f338_probe reference[COUNT],actual;
static struct f332_pipeline pipeline;
static struct f332_frame frame;
static struct f332_pipeline_result result;
static struct f332_zc zc;
static struct f332_pulse raw[128];
static uint32_t checks,failures,reset_calls,cancel_reset;
static void text(const char*s){volatile uint32_t*u=(void*)0x90000000;while(*s)*u=(unsigned char)*s++;}
static void hex(uint32_t n){char s[9];unsigned i;s[8]=0;for(i=0;i<8;i++)s[i]="0123456789abcdef"[(n>>((7-i)*4))&15];text(s);}
void *memset(void*p,int c,size_t n){unsigned char*x=p;size_t i;for(i=0;i<n;i++)x[i]=(unsigned char)c;return p;}
void *memcpy(void*d,const void*s,size_t n){unsigned char*x=d;const unsigned char*y=s;size_t i;for(i=0;i<n;i++)x[i]=y[i];return d;}
int memcmp(const void*a,const void*b,size_t n){const unsigned char*x=a,*y=b;size_t i;for(i=0;i<n;i++)if(x[i]!=y[i])return x[i]<y[i]?-1:1;return 0;}
uint32_t f338_hash(const void*p,unsigned n){const unsigned char*x=p;uint32_t hash=2166136261U;unsigned i;for(i=0;i<n;i++)hash=(hash^x[i])*16777619U;return hash;}
static int check(int yes){checks++;if(!yes){failures++;text("F338_ORACLE_FAIL check=");hex(checks);text("\n");}return yes;}
static int epoch(void*ctx,uint32_t gen){(void)ctx;return gen==input.h.generation;}
static int reset_unused(void*c,uint32_t g,uint32_t r,int32_t*s,int32_t*u){(void)c;(void)g;(void)r;(void)s;(void)u;return -1;}
static int reset_rpc(void*ctx,struct f338_reset*r)
{(void)ctx;reset_calls++;if(cancel_reset)return cancel_reset==1?F338_ENGINE_CANCELED:F338_ENGINE_FAILED;r->sequence_emitted=1;r->actual_seconds=input.real_seconds;r->actual_microseconds=input.real_microseconds+1;return 0;}
static void fixture(unsigned step)
{
 unsigned n,count=0;memset(&input,0,sizeof(input));input.h.magic=F338_MAGIC;input.h.abi=F338_ABI;input.h.size=sizeof(input);input.h.session=1;input.h.sequence=step+1;
 input.h.generation=step<150?1:step<160?2:3;input.channel=step<150?52:step<160?120:36;input.bandwidth=step<150?80:step<160?40:80;
 input.timestamp_base=step<150?0:0x10000000;input.legacy_ticks=step*10;input.real_seconds=step/20;input.real_microseconds=(step%20)*50000;
 input.tx_bytes_per_second=(step/20==1)?12345:(step/20==2)?9000000:0;
 if(step>=160){input.flags=F338_JOB_OCAC|F338_JOB_WEATHER;input.scan_channel=120;}
 if(step==0||step==132||step==151||step==161)count=8;
 if(step==121||step==122)count=128;
 if(step==130)count=1;
 if(step==131)count=2;
 input.raw_count=count;for(n=0;n<count;n++){input.raw[n].start=step*1000000+n*10000;input.raw[n].stop=input.raw[n].start+40;input.raw[n].max_power=10;}
}
static int composed(unsigned step)
{
 struct f332_backend backend={0,epoch,reset_unused};unsigned n;
 if(!pipeline.initialized||pipeline.generation!=input.h.generation){
  if(pipeline.initialized)f332_pipeline_end(&pipeline);
  if(f332_pipeline_begin(&pipeline,input.h.generation,input.channel,input.bandwidth,input.timestamp_base,input.legacy_ticks,0,&backend))return -1;
 }
 memset(&frame,0,sizeof(frame));frame.generation=input.h.generation;frame.channel=input.channel;frame.bandwidth=input.bandwidth;frame.legacy_ticks=input.legacy_ticks;frame.seconds=input.real_seconds;frame.microseconds=input.real_microseconds;
 frame.raw=raw;frame.raw_count=input.raw_count;frame.zc=&zc;frame.raw_valid=frame.zc_association_valid=frame.rate_valid=frame.callback_registered=true;frame.tx_bytes_per_second=input.tx_bytes_per_second;
 frame.ocac_filter=!!(input.flags&F338_JOB_OCAC);frame.ocac_weather=!!(input.flags&F338_JOB_WEATHER);frame.ocac_scan_channel=input.scan_channel;
 memcpy(zc.samples,input.zc,sizeof(zc.samples));zc.accurate=input.zc_accurate;
 for(n=0;n<input.raw_count;n++){raw[n].start=input.raw[n].start;raw[n].stop=input.raw[n].stop;raw[n].max_power=input.raw[n].max_power;raw[n].tagged=input.raw[n].tagged;}
 if(f338_pipeline_make_job(&pipeline,&frame,&job,&result))return -2;
 job.h.session=1;job.h.sequence=step+1;
 if(f338_engine_job(&job,&reply,reset_rpc,0))return -3;
 if(f338_pipeline_finish(&pipeline,&frame,&reply,&result))return -4;
 memset(&actual,0,sizeof(actual));actual.total=result.total_count;actual.current_count=result.current_window_count;actual.poll=result.poll_counter;actual.candidate=result.candidate_detected;actual.flushes=result.flushes;actual.resets=result.reset_sequences_emitted;actual.callback=result.callback_condition;
 actual.cfg_hash=f338_hash(pipeline.detection.configuration,300);actual.stats_hash=f338_hash(pipeline.detection.statistics,700);actual.history_hash=f338_hash(&pipeline.postfilter,sizeof(pipeline.postfilter));actual.rate_hash=f338_hash(&pipeline.rate,sizeof(pipeline.rate));return 0;
}
void f338_oracle_main(void)
{
 unsigned n;int rc;uint32_t completed_resets;
 text("F338_ORACLE_BEGIN original_math=1 hardware=0\n");
 for(n=0;n<COUNT;n++){fixture(n);if(n==151)f330_test_poll_count(100);if(!check(!f338_reference_step(&input,&reference[n])))goto done;}
 f338_reference_end();
 for(n=0;n<COUNT;n++){
  fixture(n);if(n==151)f330_test_poll_count(100);rc=composed(n);
  if(!check(!rc)){text("STEP=");hex(n);text(" RC=");hex(rc);text("\n");goto done;}
  if(!check(!memcmp(&actual,&reference[n],sizeof(actual)))){text("DIFF_STEP=");hex(n);text("\n");goto done;}
 }
 completed_resets=reset_calls;check(completed_resets>0);
 /* The service keeps running through all three legitimate cancellation
  * paths. Sequence gaps never permit a replay or a lower generation. */
 f338_engine_close();fixture(0);input.h.sequence=2;input.poll_counter=1;
 check(!f338_engine_job(&input,&reply,reset_rpc,0));
 input.h.generation=4;input.h.sequence=5;input.raw_count=0;
 check(!f338_engine_job(&input,&reply,reset_rpc,0));
 f338_engine_cancel();input.h.generation=5;input.h.sequence=6;
 check(!f338_engine_job(&input,&reply,reset_rpc,0));
 f330_test_poll_count(101);input.h.sequence=7;cancel_reset=1;
 check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_CANCELED&&reply.status==F338_WIRE_CANCELED);
 input.h.generation=6;input.h.sequence=8;cancel_reset=0;
 check(!f338_engine_job(&input,&reply,reset_rpc,0));
 check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_FAILED);
 input.h.generation=5;input.h.sequence=9;check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_FAILED);
 input.h.generation=6;input.channel=56;check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_FAILED);input.channel=52;
 f330_test_poll_count(101);input.h.sequence=9;cancel_reset=2;
 check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_FAILED&&reply.status==F338_WIRE_ENGINE);
 cancel_reset=0;input.h.generation=7;input.h.sequence=10;check(f338_engine_job(&input,&reply,reset_rpc,0)==F338_ENGINE_FAILED);
 f338_engine_close();
done:
 text("F338_ORACLE_DONE checks=");hex(checks);text(" failures=");hex(failures);text(" vectors=000000b4 hardware=0\n");
}
