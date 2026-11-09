"""Actual congestion consumer functions under fake published/refused outcomes.

No MMIO. Source-only caller contract tests cannot qualify module dependencies,
pending payload recovery, foreign writers or original HBM cleanup paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function

PRELUDE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t uint8;typedef uint8_t uint8_t_;typedef int8_t int8;
#define NET_XMIT_CN 2
#define NET_XMIT_SUCCESS 0
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
#define TOPAZ_SOFTIRQ_BUDGET 8
#define unlikely(x) (x)
#define __attribute__(x)
#define noinline
#define EXPORT_SYMBOL(x)
#define time_after(a,b) ((a)>(b))
union topaz_tqe_cpuif_ppctl{uint32_t words[6];};
union topaz_tqe_cpuif_descr{uint32_t words[4];};
struct topaz_congest_queue;
struct topaz_congest_q_elem{union topaz_tqe_cpuif_ppctl ppctl;};
struct topaz_congest_q_desc{struct topaz_congest_q_elem elems[4];unsigned qlen,head,last_retry_success,retry_timeout,congest_drop,congest_xmit;struct topaz_congest_queue *congest_queue;};
struct topaz_congest_queue{int(*xmit_func)(union topaz_tqe_cpuif_ppctl*);unsigned xmit_entry,cnt_retries,congest_timeout;int congest_tx;};
static unsigned quarantine,callback_result,callback_calls,enqueues,frees,dequeues,schedules,congested,jiffies;
static struct topaz_congest_q_desc desc;
static int omtqe_lhost_quarantined(void){return quarantine;}
static int omcgq_bank_quarantined(void){return quarantine;}
static int omcgq_bank_retain(const union topaz_tqe_cpuif_ppctl*p,int published){(void)p;(void)published;return 1;}
static int callback(union topaz_tqe_cpuif_ppctl*p){(void)p;callback_calls++;if(callback_result==OMTQE_OWNERSHIP_UNCERTAIN)quarantine=1;return callback_result;}
static int topaz_queue_congested(struct topaz_congest_queue*q,unsigned n,unsigned t){(void)q;(void)n;(void)t;return congested;}
static struct topaz_congest_q_desc*topaz_get_congest_queue(struct topaz_congest_queue*q,unsigned n,unsigned t){(void)q;(void)n;(void)t;return &desc;}
static struct topaz_congest_q_desc*topaz_congest_alloc_queue(struct topaz_congest_queue*q,unsigned n,unsigned t){(void)n;(void)t;desc.congest_queue=q;return &desc;}
static struct topaz_congest_q_desc*topaz_congest_alloc_unicast_queue(struct topaz_congest_queue*q,unsigned n,unsigned t){return topaz_congest_alloc_queue(q,n,t);}
static int topaz_congest_enqueue(struct topaz_congest_q_desc*d,union topaz_tqe_cpuif_ppctl*p){(void)p;enqueues++;d->qlen++;return 0;}
static void topaz_hbm_congest_queue_put_buf(const union topaz_tqe_cpuif_ppctl*p){(void)p;frees++;}
static union topaz_tqe_cpuif_ppctl*topaz_congest_peek(struct topaz_congest_q_desc*d){return d->qlen?&d->elems[d->head].ppctl:NULL;}
static void topaz_congest_dequeue(struct topaz_congest_q_desc*d){assert(d->qlen);dequeues++;d->qlen--;}
static void tasklet_schedule(int*p){(void)p;schedules++;}
'''

TESTS = r'''
int main(void){struct topaz_congest_queue queue={.xmit_func=callback,.congest_timeout=2};union topaz_tqe_cpuif_ppctl ctl={0};union topaz_tqe_cpuif_descr rx={0};unsigned cases=0;
for(unsigned code=0x40;code<=0x41;code++){
 quarantine=enqueues=frees=dequeues=schedules=callback_calls=congested=0;callback_result=code;memset(&desc,0,sizeof(desc));desc.congest_queue=&queue;
 topaz_tqe_congest_queue_process(&rx,&queue,0,0,&ctl,1);assert(callback_calls==1&&!enqueues&&!frees&&!dequeues&&!schedules);cases++;
 quarantine=enqueues=frees=dequeues=schedules=callback_calls=congested=0;callback_result=code;desc.qlen=1;desc.last_retry_success=1;
 assert(topaz_congest_queue_xmit(&desc,8)==0);assert(callback_calls==1&&desc.qlen==1&&!dequeues&&!frees&&!schedules);cases++;
}
quarantine=1;enqueues=frees=dequeues=schedules=callback_calls=0;desc.qlen=1;desc.last_retry_success=0;desc.retry_timeout=0;jiffies=10;
topaz_congest_queue_clear(&desc);assert(desc.qlen==1&&!frees&&!dequeues);cases++;
topaz_tqe_congest_queue_process(&rx,&queue,0,0,&ctl,1);assert(!callback_calls&&!enqueues&&!frees&&!schedules);cases++;
assert(topaz_congest_queue_xmit(&desc,8)==0&&desc.qlen==1&&!callback_calls&&!frees&&!dequeues);cases++;
quarantine=0;callback_result=NET_XMIT_CN;enqueues=frees=dequeues=schedules=callback_calls=congested=0;desc.qlen=1;desc.last_retry_success=1;
assert(topaz_congest_queue_xmit(&desc,8)==1);assert(desc.qlen==1&&callback_calls==1&&desc.last_retry_success==0&&!dequeues&&!frees);cases++;
quarantine=0;callback_result=0;enqueues=frees=dequeues=schedules=callback_calls=0;desc.qlen=1;desc.last_retry_success=1;
assert(topaz_congest_queue_xmit(&desc,8)==0&&desc.qlen==0&&callback_calls==1&&dequeues==1&&!frees);cases++;
printf("{\"executed_cases\":%u}\n",cases);return 0;}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tqe = (args.candidate / "switch_tqe.c").read_text()
    cgq = (args.candidate / "topaz_congest_queue.c").read_text()
    funcs = [function(cgq, "noinline static void topaz_congest_queue_clear("),
             function(cgq, '__attribute__((section(".sram.text"))) int topaz_congest_queue_xmit('),
             function(tqe, "void topaz_tqe_congest_queue_process(")]
    args.output.mkdir(parents=True, exist_ok=False)
    path = args.output / "actual-queue-consumers.c"
    path.write_text(PRELUDE + "\n".join(funcs) + TESTS)
    built = subprocess.run([str(args.compiler), "-std=c11", "-O1", str(path), "-o", str(args.output / "fixture.exe")], capture_output=True)
    (args.output / "compile.stderr").write_bytes(built.stderr)
    assert built.returncode == 0, built.stderr.decode()
    tested = subprocess.run([str(args.output / "fixture.exe")], capture_output=True)
    (args.output / "run.stderr").write_bytes(tested.stderr)
    assert tested.returncode == 0, tested.stderr.decode()
    result = {"status": "PASS_ACTUAL_QUEUE_CONSUMERS_REFUSAL_UNCERTAINTY_FIXTURE", "hardware_accessed": False,
              "firmware_eligible": False, "cases": json.loads(tested.stdout)["executed_cases"],
              "actual_source_functions": 3, "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "published_unknown_no_retry_no_free": True, "quarantined_queue_clear_retains": True,
              "legacy_confirmed_CN_retries": True, "legacy_success_dequeues": True,
              "limits": "Source-only consumer semantics; module cycle, retained payload/queue release, HBM paths and foreign bank writers remain NO_GO."}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
