// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "f338_protocol.h"
static unsigned checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL line%d: %s\n",__LINE__,#x);return 1;}}while(0)
static struct f338_job job;
static struct f338_reply reply;
static void job_init(unsigned gen)
{memset(&job,0,sizeof(job));job.h.magic=F338_MAGIC;job.h.abi=F338_ABI;job.h.size=sizeof(job);job.h.generation=gen;job.channel=52;job.bandwidth=80;job.real_seconds=100;}
int main(void)
{
 struct f338_protocol state={0};struct f338_reset reset={0},cached={0};unsigned session,n;
 CHECK(sizeof(struct f338_header)==24&&sizeof(job)==24072&&sizeof(reply)==1048&&sizeof(reset)==40);
 CHECK(!f338_protocol_attach(&state));session=state.session;
 CHECK(f338_protocol_attach(&state)==F338_PROTO_BUSY);
 job_init(1);CHECK(!f338_protocol_queue(&state,&job,100));
 /* Cancel before read: next job legitimately skips a sequence. */
 CHECK(job.h.sequence==1);f338_protocol_cancel(&state);job_init(2);
 CHECK(!f338_protocol_queue(&state,&job,110)&&job.h.sequence==2);
 CHECK(!f338_protocol_delivered(&state,&job.h,111));
 memset(&reply,0,sizeof(reply));reply.h=job.h;reply.h.size=sizeof(reply);
 f338_protocol_cancel(&state);CHECK(f338_protocol_reply(&state,&reply,112)==F338_PROTO_STALE);
 job_init(3);CHECK(!f338_protocol_queue(&state,&job,113));CHECK(!f338_protocol_delivered(&state,&job.h,114));
 reset.h=job.h;reset.h.size=sizeof(reset);reset.request_id=9;
 CHECK(!f338_protocol_reset_begin(&state,&reset,&cached,115));
 CHECK(f338_protocol_reset_begin(&state,&reset,&cached,116)==F338_PROTO_BUSY);
 reset.sequence_emitted=1;reset.actual_seconds=200;reset.actual_microseconds=777;
 CHECK(!f338_protocol_reset_end(&state,&reset,117));
 CHECK(f338_protocol_reset_begin(&state,&reset,&cached,118)==F338_PROTO_REPLAY);
 CHECK(!memcmp(&cached,&reset,sizeof(reset))&&state.reset_count==1);
 for(n=10;n<12;n++){reset.request_id=n;CHECK(!f338_protocol_reset_begin(&state,&reset,&cached,119));CHECK(!f338_protocol_reset_end(&state,&reset,120));}
 reset.request_id=12;CHECK(f338_protocol_reset_begin(&state,&reset,&cached,121)==F338_PROTO_INVALID);
 reply.h=job.h;reply.h.size=sizeof(reply);reply.candidate=1;reply.total_count=8;reply.current_window_count=8;reply.flushes=1;reply.reset_sequences=3;
 CHECK(f338_protocol_reply(&state,&reply,122)==F338_PROTO_INVALID);
 reply.flushes=2;CHECK(!f338_protocol_reply(&state,&reply,122));
 CHECK(f338_protocol_reply(&state,&reply,122)==F338_PROTO_STALE);
 job_init(4);CHECK(!f338_protocol_queue(&state,&job,0xfffffff0U));
 CHECK(!f338_protocol_delivered(&state,&job.h,0xfffffff1U));
 CHECK(!f338_protocol_check_timeout(&state,0x53));CHECK(f338_protocol_check_timeout(&state,0x54)==F338_PROTO_TIMEOUT);
 f338_protocol_cancel(&state);CHECK(state.state==F338_ABORTED);
 f338_protocol_detach(&state,session);CHECK(state.state==F338_OFF);
 CHECK(!f338_protocol_attach(&state));CHECK(state.session==session+1);
 f338_protocol_detach(&state,session);CHECK(state.state==F338_IDLE);
 job_init(5);CHECK(!f338_protocol_queue(&state,&job,200));CHECK(!f338_protocol_delivered(&state,&job.h,201));
 reset.h=job.h;reset.h.size=sizeof(reset);reset.request_id=1;CHECK(!f338_protocol_reset_begin(&state,&reset,&cached,202));
 f338_protocol_cancel(&state);CHECK(f338_protocol_reset_end(&state,&reset,203)==F338_PROTO_STALE);
 job_init(6);job.raw_count=129;CHECK(f338_protocol_queue(&state,&job,210)==F338_PROTO_INVALID);
 job_init(6);job.raw_count=1;job.raw[0].tagged=2;CHECK(f338_protocol_queue(&state,&job,210)==F338_PROTO_INVALID);
 job_init(6);job.real_microseconds=1000000;CHECK(f338_protocol_queue(&state,&job,210)==F338_PROTO_INVALID);
 job_init(6);job.h.magic=0;CHECK(f338_protocol_queue(&state,&job,210)==F338_PROTO_INVALID);
 job_init(6);state.sequence=~0U;CHECK(f338_protocol_queue(&state,&job,210)==F338_PROTO_EXHAUSTED);
 f338_protocol_detach(&state,state.session);state.session=~0U;CHECK(f338_protocol_attach(&state)==F338_PROTO_EXHAUSTED);
 printf("F338_PROTOCOL_PASS checks=%u\n",checks);return 0;
}
