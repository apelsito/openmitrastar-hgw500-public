"""Actual R4 provider markers/credits + queuexmit typed token fixture, host only.

No actual HBM/MMIO. Original queue enqueue is controlled fake capacity/pool;
typed retries, head bookkeeping and quarantine are real extracted candidate C.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
#define EXPORT_SYMBOL(x)
#define READ_ONCE(x) (x)
#define __attribute__(x)
#define NET_XMIT_SUCCESS 0
#define NET_XMIT_CN 2
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
#define TOPAZ_CONGEST_TOTAL_PKT_MAX 2048U
#define time_after(a,b) ((a)>(b))
struct module{unsigned refs;bool deny;};static struct module provider,owner;
#define THIS_MODULE (&provider)
static bool try_module_get(struct module*m){if(m->deny)return false;m->refs++;return true;}
static void module_put(struct module*m){assert(m->refs);m->refs--;}
static unsigned irq;
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
union topaz_tqe_cpuif_ppctl{u32 words[6];};
struct omcgq_bank_token{u32 generation;struct module*owner;};
struct omcgq_batch_token{u32 generation;struct module*owner;};
typedef int(*omcgq_batch_xmit_fn)(const struct omcgq_batch_token*,union topaz_tqe_cpuif_ppctl*);
struct topaz_congest_queue;
struct topaz_congest_q_desc{union topaz_tqe_cpuif_ppctl elems[4];u32 tail,head,qlen,last_retry_success,retry_timeout,congest_drop,congest_xmit;struct topaz_congest_queue*congest_queue;};
struct topaz_congest_queue{u32 total_qlen,xmit_entry,cnt_retries,congest_timeout;int(*xmit_func)(union topaz_tqe_cpuif_ppctl*);};
static unsigned jiffies,callback_result,callback_calls,dequeues,clears;
static struct topaz_congest_q_desc *nested_queue;
static unsigned nested_arrival,nested_result;
static int topaz_congest_queue_xmit(struct topaz_congest_q_desc*,uint32_t);
static int topaz_congest_enqueue(struct topaz_congest_q_desc*q,union topaz_tqe_cpuif_ppctl*p){if(q->qlen==4)return2;q->elems[q->tail]=*p;q->tail=(q->tail+1)%4;q->qlen++;q->congest_queue->total_qlen++;return0;}
static union topaz_tqe_cpuif_ppctl*topaz_congest_peek(struct topaz_congest_q_desc*q){return q->qlen?&q->elems[q->head]:NULL;}
static void topaz_congest_dequeue(struct topaz_congest_q_desc*q){assert(q->qlen);q->qlen--;q->head=(q->head+1)%4;q->congest_queue->total_qlen--;dequeues++;}
static void topaz_congest_queue_clear(struct topaz_congest_q_desc*q){(void)q;clears++;}
static int typed(const struct omcgq_batch_token*b,union topaz_tqe_cpuif_ppctl*p);
'''
TEST=r'''
static int typed(const struct omcgq_batch_token*b,union topaz_tqe_cpuif_ppctl*p){(void)p;assert(omcgq_batch_valid(b));struct omcgq_bank_token acquired;assert(omcgq_batch_retry_acquire(b,&acquired));callback_calls++;if(nested_arrival){nested_arrival=0;nested_result=topaz_congest_queue_xmit(nested_queue,1);assert(callback_calls==1);}if(callback_result==OMTQE_OWNERSHIP_UNCERTAIN)assert(omcgq_bank_quarantine(&acquired,p,true));else assert(omcgq_bank_cancel(&acquired));return callback_result;}
static int ordinary(union topaz_tqe_cpuif_ppctl*p){(void)p;assert(0);return0;}
static void reset(void){memset(omcgq_held,0,sizeof(omcgq_held));memset(&omcgq_batch,0,sizeof(omcgq_batch));memset(omcgq_queue_markers,0,sizeof(omcgq_queue_markers));omcgq_held_count=omcgq_unrecorded=omcgq_generation=omcgq_batch_generation=omcgq_queue_pending=omcgq_queue_reserved=0;omcgq_retained=omcgq_reserved=omcgq_quarantined=false;omcgq_owner=omcgq_typed_owner=NULL;omcgq_typed_xmit=NULL;omcgq_credit_queue=NULL;owner.refs=provider.refs=0;callback_calls=callback_result=dequeues=clears=irq=0;}
int main(void){unsigned cases=0;struct topaz_congest_queue cgq;struct topaz_congest_q_desc q;union topaz_tqe_cpuif_ppctl p={{1,2,3,4,5,6}};struct omcgq_batch_token b;
reset();memset(&cgq,0,sizeof(cgq));memset(&q,0,sizeof(q));q.congest_queue=&cgq;cgq.xmit_func=ordinary;assert(omcgq_batch_xmit_register(&owner,typed));assert(omcgq_batch_queue_reserve(&cgq,1));assert(omcgq_batch_admit(&owner,&p,1,&b));assert(omcgq_batch_queue_admit(&b,&q,&p)&&q.qlen==1&&omcgq_queue_pending==1);assert(omcgq_batch_finish(&b)&&omcgq_batch.active);struct omcgq_bank_token wrong;assert(!omcgq_batch_acquire(&b,&wrong)&&!omcgq_batch_retry_acquire(&b,&wrong));cases++;
callback_result=NET_XMIT_CN;assert(topaz_congest_queue_xmit(&q,1)==1&&q.qlen==1&&callback_calls==1&&!dequeues&&omcgq_queue_pending==1);cases++;
callback_result=0;q.last_retry_success=1;assert(topaz_congest_queue_xmit(&q,1)==1&&q.qlen==0&&callback_calls==2&&dequeues==1&&!omcgq_queue_pending&&!omcgq_batch.active&&omcgq_held_count==0);cases++;
reset();memset(&cgq,0,sizeof(cgq));cgq.total_qlen=2048;assert(!omcgq_batch_queue_reserve(&cgq,1)&&!omcgq_queue_reserved&&!owner.refs);cases++;
reset();memset(&cgq,0,sizeof(cgq));assert(omcgq_batch_queue_reserve(&cgq,1)&&omcgq_batch_admit(&owner,&p,1,&b));assert(omcgq_batch_complete(&b,true)&&omcgq_batch_finish(&b)&&!omcgq_queue_reserved&&!omcgq_credit_queue);cases++;
reset();memset(&cgq,0,sizeof(cgq));memset(&q,0,sizeof(q));q.congest_queue=&cgq;cgq.xmit_func=ordinary;assert(omcgq_batch_xmit_register(&owner,typed));assert(omcgq_batch_queue_reserve(&cgq,1));assert(omcgq_batch_admit(&owner,&p,1,&b));assert(omcgq_batch_queue_admit(&b,&q,&p));assert(omcgq_batch_finish(&b));callback_result=OMTQE_OWNERSHIP_UNCERTAIN;assert(topaz_congest_queue_xmit(&q,1)==0&&q.qlen==1&&omcgq_queue_pending==1&&omcgq_quarantined&&!dequeues);cases++;
reset();owner.deny=true;assert(!omcgq_batch_xmit_register(&owner,typed)&&!omcgq_typed_xmit&&!provider.refs&&!owner.refs);owner.deny=false;cases++;
reset();provider.deny=true;assert(!omcgq_batch_xmit_register(&owner,typed)&&!omcgq_typed_xmit&&!provider.refs&&!owner.refs);provider.deny=false;cases++;
reset();assert(omcgq_batch_xmit_register(&owner,typed)&&provider.refs==1&&owner.refs==1);assert(omcgq_batch_xmit_register(&owner,typed)&&provider.refs==1&&owner.refs==1);cases++;
reset();memset(&cgq,0,sizeof(cgq));memset(&q,0,sizeof(q));q.congest_queue=&cgq;cgq.xmit_func=ordinary;assert(omcgq_batch_xmit_register(&owner,typed)&&omcgq_batch_queue_reserve(&cgq,1)&&omcgq_batch_admit(&owner,&p,1,&b)&&omcgq_batch_queue_admit(&b,&q,&p));assert(omcgq_batch_finish(&b));nested_queue=&q;nested_arrival=1;callback_result=0;assert(topaz_congest_queue_xmit(&q,1)==1&&nested_result==1&&callback_calls==1&&dequeues==1&&q.qlen==0&&!omcgq_queue_processing);cases++;
printf("{\"cases\":%u}\n",cases);return0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();src=(a.candidate/'topaz_congest_queue.c').read_text();start=src.index('#define OMCGQ_HELD_MAX');end=src.index('struct topaz_congest_queue *g_congest_queue_ptr',start);provider=src[start:end];queue=function(src,'__attribute__((section(".sram.text"))) int topaz_congest_queue_xmit(');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-typed-queue.c';f.write_text((PRE+provider+queue+TEST).replace('return0','return 0').replace('return2','return 2'));b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_TYPED_PROVIDER_QUEUE_RETRY_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'confirmed_CN_keeps_same_marker_and_owner':True,'successful_retry_consumes_marker_and_credit_once':True,'published_unknown_keeps_head_no_retry':True,'pre_ec_global_capacity_refusal':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'Queueenqueuecapacity fake; provider/token/queuexmit actualcandidateC. Furtherallwriter/fullmodule/ABI/globaldelta required.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
