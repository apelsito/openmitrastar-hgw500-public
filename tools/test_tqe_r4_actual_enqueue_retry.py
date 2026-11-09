"""Actual TQE typed initial callback and provider queue retry integration fixture.

Models MMIO/VLAN and queue allocation while extracting full actual marker,
credit, queueenqueue accounting and TQE initial/retry callback source functions.
No hardware release/reset; published unknown retains ownership.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_r3_actual_typed_publication import EXTRA
from test_tqe_lhost_writer_serialization import PRELUDE

QUEUES=r'''
#define TOPAZ_CONGEST_TOTAL_PKT_MAX 2048U
#define time_after(a,b) ((a)>(b))
typedef int(*omcgq_batch_xmit_fn)(const struct omcgq_batch_token*,union topaz_tqe_cpuif_ppctl*);
struct topaz_congest_queue;
struct topaz_congest_q_desc{union topaz_tqe_cpuif_ppctl elems[4];unsigned tail,head,qlen,last_retry_success,retry_timeout,congest_drop,congest_xmit;struct topaz_congest_queue*congest_queue;};
struct topaz_congest_queue{unsigned total_qlen,xmit_entry,cnt_retries,congest_timeout;int congest_tx;int(*xmit_func)(union topaz_tqe_cpuif_ppctl*);};
static struct topaz_congest_q_desc queue;
static unsigned jiffies,dequeues,schedules;
static int topaz_congest_enqueue(struct topaz_congest_q_desc*q,union topaz_tqe_cpuif_ppctl*p){if(q->qlen==4)return2;q->elems[q->tail]=*p;q->tail=(q->tail+1)%4;q->qlen++;q->congest_queue->total_qlen++;return0;}
static union topaz_tqe_cpuif_ppctl*topaz_congest_peek(struct topaz_congest_q_desc*q){return q->qlen?&q->elems[q->head]:NULL;}
static void topaz_congest_dequeue(struct topaz_congest_q_desc*q){assert(q->qlen);q->qlen--;q->head=(q->head+1)%4;q->congest_queue->total_qlen--;dequeues++;}
static void topaz_congest_queue_clear(struct topaz_congest_q_desc*q){(void)q;assert(0);}
static int topaz_queue_congested(struct topaz_congest_queue*q,unsigned n,unsigned tid){(void)q;(void)n;(void)tid;return queue.qlen!=0;}
static struct topaz_congest_q_desc*topaz_get_congest_queue(struct topaz_congest_queue*q,unsigned n,unsigned tid){(void)n;(void)tid;queue.congest_queue=q;return&queue;}
static struct topaz_congest_q_desc*topaz_congest_alloc_queue(struct topaz_congest_queue*q,unsigned n,unsigned tid){return topaz_get_congest_queue(q,n,tid);}
static void tasklet_schedule(int*p){(void)p;schedules++;}
'''

TEST=r'''
static void run_kind(unsigned k){(void)k;}
static int ordinary(union topaz_tqe_cpuif_ppctl*p){(void)p;assert(0);return0;}
static void clear(void){memset(omcgq_held,0,sizeof(omcgq_held));memset(&omcgq_batch,0,sizeof(omcgq_batch));memset(omcgq_queue_markers,0,sizeof(omcgq_queue_markers));memset(&queue,0,sizeof(queue));omcgq_held_count=omcgq_unrecorded=omcgq_generation=omcgq_batch_generation=omcgq_queue_pending=omcgq_queue_reserved=0;omcgq_reserved=omcgq_quarantined=omcgq_retained=false;omcgq_owner=omcgq_typed_owner=NULL;omcgq_typed_xmit=NULL;omcgq_credit_queue=NULL;omcgq_retry_marker=NULL;provider.refs=consumer.refs=0;provider.deny=consumer.deny=false;irq_disabled=publications=collisions=queue_calls=drops=waits=pending_kind=scheduled_kind=inject_phase=injected=foreign_kind=foreign_inflight=0;ready_reads=complete_reads=postsubmit=vlan_denied=egress_calls=schedules=dequeues=0;ready_on=complete_on=1;last_status=0;vlan_enabled=0;}
int main(void){unsigned cases=0;union topaz_tqe_cpuif_ppctl payload={0};struct omtqe_mcast_context context;struct topaz_congest_queue cgq;
payload.data.pkt=(void*)64;payload.data.length=64;
clear();memset(&cgq,0,sizeof(cgq));cgq.xmit_func=ordinary;context.queue=&cgq;assert(omcgq_batch_xmit_register(&consumer,omtqe_typed_queue_xmit));assert(omcgq_batch_queue_reserve(&cgq,1)&&omcgq_batch_admit(&consumer,&payload,1,&context.batch));last_status=0x40000000U;omtqe_push_mcast_batch(&incoming,&context,1,3,0);
assert(publications==1&&queue.qlen==1&&omcgq_queue_pending==1&&omcgq_batch.completed==1&&omcgq_batch.published==0&&!omcgq_quarantined&&schedules==1);assert(omcgq_batch_finish(&context.batch)&&omcgq_batch.active);cases++;
last_status=0;postsubmit=0;ready_reads=complete_reads=0;queue.last_retry_success=1;assert(topaz_congest_queue_xmit(&queue,1)==1);assert(publications==2&&queue.qlen==0&&dequeues==1&&!omcgq_queue_pending&&!omcgq_batch.active&&omcgq_held_count==0&&!irq_disabled);cases++;
clear();memset(&cgq,0,sizeof(cgq));cgq.xmit_func=ordinary;context.queue=&cgq;assert(omcgq_batch_xmit_register(&consumer,omtqe_typed_queue_xmit));assert(omcgq_batch_queue_reserve(&cgq,1)&&omcgq_batch_admit(&consumer,&payload,1,&context.batch));last_status=0x40000000U;omtqe_push_mcast_batch(&incoming,&context,1,3,0);assert(omcgq_batch_finish(&context.batch));postsubmit=0;complete_on=0;queue.last_retry_success=1;assert(topaz_congest_queue_xmit(&queue,1)==0);assert(publications==2&&queue.qlen==1&&omcgq_queue_pending==1&&omcgq_quarantined&&omcgq_held_count==1&&!dequeues&&!irq_disabled);cases++;
printf("{\"cases\":%u}\n",cases);return0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];t=(a.candidate/'switch_tqe.c').read_text();q=(a.candidate/'topaz_congest_queue.c').read_text();h=(root/'work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h').read_text();start=q.index('#define OMCGQ_HELD_MAX');end=q.index('struct topaz_congest_queue *g_congest_queue_ptr',start);provider=q[start:end].replace('try_module_get(THIS_MODULE)','try_module_get(&provider)');pub='\n'.join(function(h,s)for s in('topaz_tqe_cpuif_port_to_num(','__topaz_tqe_cpuif_ppctl_write(','__topaz_tqe_cpuif_tx_start(','\ntopaz_tqe_cpuif_tx_start('));pub='static int '+pub
 for name,typ in(('__topaz_tqe_cpuif_ppctl_write','int'),('__topaz_tqe_cpuif_tx_start','void'),('topaz_tqe_cpuif_tx_start','void')):pub=pub.replace('\n'+name+'(','\nstatic '+typ+' '+name+'(',1)
 funcs='\n'.join(function(t,s)for s in('static int omtqe_lhost_quarantined(','static int omtqe_lhost_submit_reserved(','static int omtqe_typed_queue_xmit(','static void omtqe_push_mcast_batch('));queuexmit=function(q,'__attribute__((section(".sram.text"))) int topaz_congest_queue_xmit(');pre=PRELUDE.replace('static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}','static int ready_state(void);static int topaz_tqe_cpuif_tx_nready(void){return ready_state();}').replace('static void run_kind(unsigned kind);','static void run_kind(unsigned kind);static unsigned postsubmit;').replace('publications++;bank_writes[0]++;last_status=0;phase(9);','publications++;bank_writes[0]++;postsubmit=1;phase(9);').replace('static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;return 1;}','static unsigned vlan_denied,egress_calls;static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;egress_calls++;return!vlan_denied;}');a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-enqueue-retry.c';f.write_text((pre+EXTRA+QUEUES+provider+pub+'struct omtqe_mcast_context{void*queue;struct omcgq_batch_token batch;};\n'+funcs+queuexmit+TEST).replace('return0','return 0').replace('return2','return 2'));b=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(b.stderr);assert not b.returncode,b.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();result={'status':'PASS_ACTUAL_INITIAL_TYPED_ENQUEUE_AND_ASYNC_RETRY_OWNER_FIXTURE','hardware_accessed':False,'firmware_eligible':False,'cases':json.loads(r.stdout)['cases'],'confirmed_CN_queue_then_success_owner_credit_once':True,'retry_publication_unknown_retains_head_marker_owner':True,'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':'FakeMMIO/queuecapacity/VLAN hooks; actualTQEinitial/retry provider/token/queuexmit source. Nohardware/foreign/recoveryacceptance.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
