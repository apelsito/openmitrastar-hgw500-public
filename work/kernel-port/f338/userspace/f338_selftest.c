/* Linux userspace selftest. No UAPI open, MMIO, radio, network or input data. */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <sys/resource.h>
#include "f332_detector.h"
#include "f330_preprocess.h"
static struct{uint32_t before;struct f332_pulse p[256];uint32_t after;}raw;
static struct{uint32_t before;struct f332_zc z;uint32_t after;}crossing;
static int32_t indices[128];
static struct f332_detection detection;
static struct f330_result prepared;
static unsigned checks;
static int check(int good){checks++;return good?0:-1;}
static int classifier_test(void)
{
 static const unsigned counts[]={0,1,2,8,16,32,64,100,128,200,256};
 static const uint32_t bases[]={0,0x07ffff00,0x08000000,0x10000000,0xffff0000};
 unsigned c,b,n,gen=1;
 memset(indices,0,sizeof(indices));memset(&crossing,0,sizeof(crossing));
 for(c=0;c<sizeof(counts)/sizeof(counts[0]);c++)for(b=0;b<sizeof(bases)/sizeof(bases[0]);b++){
  unsigned count=counts[c],current_count=count>128?128:count;
  raw.before=crossing.before=0x13579bdf;raw.after=crossing.after=0x2468ace0;
  memset(raw.p,0,sizeof(raw.p));
  for(n=0;n<count;n++){raw.p[n].start=bases[b]+n*10000;raw.p[n].stop=raw.p[n].start+40;raw.p[n].max_power=10;}
  if(check(!f332_detect_begin(gen,52,80,0))||check(!f332_detect_environment(gen,0,0,0)))return -1;
  if(check(!f332_detect_step(gen,raw.p,count,current_count,indices,&crossing.z,0,10,&detection)))return -1;
  if(check(detection.candidate==(count>=8))||check(!detection.fault))return -1;
  if(check(raw.before==0x13579bdf&&raw.after==0x2468ace0&&crossing.before==0x13579bdf&&crossing.after==0x2468ace0))return -1;
  if(check(!f332_detect_end(gen)))return -1;
  gen++;
 }
 return 0;
}
static int preprocess_test(void)
{
 int rc;
 struct f330_raw p[3]={{1000,1040,10,0,{0}},{11000,11040,10,0,{0}},{21000,21040,10,0,{0}}};
 if(check(f330_begin(1000,0,0)==F330_OK))return -1;
 if(check(f330_prepare(1000,p,3,1,100,&prepared)==F330_OK)||check(prepared.total_count==3&&prepared.current_window_count==3&&prepared.committed))return -1;
 if(check(f330_prepare(1000,0,0,1,200,&prepared)==F330_OK)||check(prepared.total_count==3&&prepared.current_window_count==0))return -1;
 if(check(f330_prepare(1000,0,0,1,300,&prepared)==F330_OK)||check(prepared.total_count==0&&prepared.current_window_count==0))return -1;
 f330_test_poll_count(100);
 /* OEM2ae2 keeps count100; quiet reset requires previous count>100.
  * Preserve both boundaries already proved by F330 quiet_100/quiet_101. */
 rc=f330_prepare(1000,0,0,2,100,&prepared);
 if(check(rc==F330_OK)||check(prepared.committed&&prepared.poll_before==100&&prepared.poll_after==101&&prepared.counter_writes==0)){
  fprintf(stderr,"F338_PREPROCESS_BOUNDARY count=100 rc=%d fault=%u before=%u after=%u writes=%u\n",rc,prepared.abi_fault,prepared.poll_before,prepared.poll_after,prepared.counter_writes);return -1;
 }
 rc=f330_prepare(1000,0,0,2,100,&prepared);
 if(check(rc==F330_RESET_REQUIRED)||check(!prepared.committed&&prepared.request_id&&prepared.counter_writes==2)){
  fprintf(stderr,"F338_PREPROCESS_BOUNDARY count=101 rc=%d fault=%u before=%u after=%u writes=%u\n",rc,prepared.abi_fault,prepared.poll_before,prepared.poll_after,prepared.counter_writes);return -1;
 }
 if(check(f330_confirm_reset(1000,prepared.request_id,1,2,101,&prepared)==F330_OK)||check(prepared.committed&&prepared.timestamp_after==20001010U))return -1;
 return 0;
}
int f338_run_selftest(void)
{
 struct timespec mono,real;
 if(sizeof(void*)!=4||getpid()<=0||clock_gettime(CLOCK_MONOTONIC,&mono)||clock_gettime(CLOCK_REALTIME,&real)||mono.tv_nsec<0||mono.tv_nsec>=1000000000||real.tv_nsec<0||real.tv_nsec>=1000000000)return 10;
 if(classifier_test())return 20;
 if(preprocess_test())return 30;
 printf("F338_SELFTEST_PASS checks=%u classifier_vectors=55 linux_syscalls=1 hardware=0 uapi_opened=0\n",checks);
 return 0;
}
int main(int argc,char**argv)
{
 int rc;
 struct rlimit cpu_limit={4,5};
 if(argc!=2||strcmp(argv[1],"--selftest")){fputs("Usage: om-radar-engine-f338 --selftest\n",stderr);return 64;}
 if(setrlimit(RLIMIT_CPU,&cpu_limit)){fputs("F338_SELFTEST_FAIL limit\n",stderr);return 11;}
 alarm(10);
 puts("F338_SELFTEST_BEGIN alarm_seconds=10 cpu_hard_seconds=5 hardware=0");fflush(stdout);
 rc=f338_run_selftest();if(rc)fprintf(stderr,"F338_SELFTEST_FAIL phase=%d checks=%u\n",rc,checks);return rc;
}
