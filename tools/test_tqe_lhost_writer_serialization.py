"""Host C fixture of actual four source writers and CPUIF bank publication.

Fake IRQ/MMIO/HBM only; no kernel module, no physical or timing qualification.
Interrupt arrivals are deferred until the actual local IRQ interval is restored.
A deliberately noncooperating foreign bank0 writer still demonstrates collision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import hashlib

from prepare_tqe_bounded_admission_prototype import function

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t uint8; typedef uint32_t uint32; typedef uint16_t uint16;
#define __sram_text
#define EXPORT_SYMBOL(x)
#define __iomem
#define TOPAZ_TQE_LOCAL_CPU 4
#define TOPAZ_TQE_LHOST_PORT 4
#define TOPAZ_TQE_WMAC_PORT 2
#define TOPAZ_TQE_CPUIF_TXSTART(x) (0xe1034038U+0x1000U*(x))
#define TOPAZ_TQE_CPUIF_TX_START_NOT_SUCCESS 0x40000000U
#define NET_XMIT_CN 2
#define NET_XMIT_SUCCESS 0
#define TOPAZ_HBM_EMAC_TX_DONE_POOL 2
#define TOPAZ_TQE_PORT_IS_EMAC(p) ((p)<2)
union topaz_tqe_cpuif_descr { struct { void *pkt; unsigned length; int buff_ptr_offset; int in_port; } data; };
union topaz_tqe_cpuif_ppctl { struct { void *pkt; unsigned length; int buff_ptr_offset,buff_pool_num,out_port; } data; struct { uint32_t ppctl0,ppctl1,ppctl2,ppctl3,ppctl4,ppctl5; } raw; };
typedef struct { int out_port,out_node,portal; } fwt_db_entry;
struct qtn_vlan_dev { int unused; };
struct { void (*fn)(void *,uint8_t); void *ctx; } update_multicast;
static struct qtn_vlan_dev *vport_tbl_lhost[8];
static int vlan_enabled,g_dscp_flag,g_dscp_value[2];
static unsigned irq_disabled,irq_saves,irq_restores,publications,collisions,queue_calls,drops,waits;
static unsigned pending_kind,scheduled_kind,inject_phase,injected,foreign_kind,foreign_inflight;
static uint32_t last_status;
static unsigned bank_writes[4],writes_in_transaction;
static union topaz_tqe_cpuif_descr incoming={.data={.pkt=(void*)64,.length=64}};
static fwt_db_entry fwt={.out_port=1,.out_node=3,.portal=1};
static void run_kind(unsigned kind);
static void phase(unsigned at){
 if(!injected&&inject_phase==at){
  injected=1;
  if(foreign_kind){foreign_inflight=1;bank_writes[foreign_kind==1?0:1]++;}
  else if(irq_disabled)pending_kind=scheduled_kind;
  else run_kind(scheduled_kind);
 }
}
static void irq_save(unsigned long *flags){*flags=irq_disabled;irq_disabled=1;irq_saves++;}
static void irq_restore(unsigned long flags){irq_disabled=(unsigned)flags;irq_restores++;if(!irq_disabled&&pending_kind){unsigned k=pending_kind;pending_kind=0;run_kind(k);}}
#define local_irq_save(f) irq_save(&(f))
#define local_irq_restore(f) irq_restore((f))
static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}
static void topaz_tqe_wait(void){waits++;while(topaz_tqe_cpuif_tx_nready());}
#define TOPAZ_TQE_PCIE_PORT 3
#define TOPAZ_TQE_CPUIF_PPCTL0(n) (0xe1034020U+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_PPCTL1(n) (0xe1034024U+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_PPCTL2(n) (0xe1034028U+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_PPCTL3(n) (0xe103402cU+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_PPCTL4(n) (0xe1034030U+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_PPCTL5(n) (0xe1034034U+0x1000U*(n))
#define TOPAZ_TQE_CPUIF_TX_START_NREADY 1
enum topaz_tqe_port { FIXTURE_PORT_ENUM = 0 };
static void qtn_mproc_sync_mem_write(uint32_t address,uint32_t value){
 (void)value;assert(irq_disabled);assert(address>=0xe1034020U&&address<=0xe1034038U);
 if(address==0xe1034038U){phase(8);if(foreign_inflight&&foreign_kind==1)collisions++;publications++;bank_writes[0]++;last_status=0;phase(9);}
 else{phase(2+(address-0xe1034020U)/4);bank_writes[0]++;writes_in_transaction++;}
}
static void qtn_mproc_sync_mem_write_wmb(uint32_t address,uint32_t value){qtn_mproc_sync_mem_write(address,value);}
static uint32_t qtn_mproc_sync_mem_read(uint32_t address){assert(address==0xe1034038U);phase(10);return last_status;}
static void wmb(void){phase(11);}
static int qtn_vlan_egress(struct qtn_vlan_dev*d,int n,void*b){(void)d;(void)n;(void)b;return 1;}
static void *bus_to_virt(uintptr_t a){return(void*)a;}
static uintptr_t virt_to_bus(const void*a){return(uintptr_t)a;}
static long topaz_hbm_payload_buff_ptr_offset_bus(void*a,int pool,void*n){(void)a;(void)pool;(void)n;return 64;}
static void tqe_rx_pkt_drop(const union topaz_tqe_cpuif_descr*d){(void)d;drops++;}
static void topaz_tqe_vlan_gettid(void*a,uint8_t*b,uint8_t*c){(void)a;*b=0;*c=0;}
static void topaz_tqe_cpuif_ppctl_init(union topaz_tqe_cpuif_ppctl*p,int port,uint8_t*node,int count,int tid,int portal,int alloc,int pool,int free_,int user){(void)node;(void)count;(void)tid;(void)portal;(void)alloc;(void)free_;(void)user;memset(p,0,sizeof(*p));p->data.out_port=port;p->data.buff_pool_num=pool;}
static void topaz_tqe_congest_queue_process(const union topaz_tqe_cpuif_descr*d,void*q,uint8_t n,uint8_t tid,union topaz_tqe_cpuif_ppctl*p,uint8_t unicast){(void)d;(void)q;(void)n;(void)tid;(void)p;(void)unicast;queue_calls++;}
'''

TESTS = r'''
static unsigned cases;
static void run_kind(unsigned kind){
 union topaz_tqe_cpuif_ppctl ctl={0};
 if(kind==1){assert(topaz_tqe_xmit(&ctl)==NET_XMIT_SUCCESS);}
 else if(kind==2){tqe_push_mcast(&incoming,NULL,1,3,0);}
 else if(kind==3){assert(topaz_swfwd_tqe_xmit(&fwt,&incoming,NULL)==1);}
 else if(kind==4){assert(tqe_tx_buf(&ctl,(void*)64,64,0)==0);}
 else assert(0);
}
static void reset(void){
 irq_disabled=irq_saves=irq_restores=publications=collisions=queue_calls=drops=waits=0;
 pending_kind=scheduled_kind=inject_phase=injected=foreign_kind=foreign_inflight=0;
 memset(bank_writes,0,sizeof(bank_writes));last_status=0;
}
int main(void){
 for(unsigned first=1;first<=4;first++)for(unsigned interrupt=1;interrupt<=4;interrupt++)for(unsigned at=1;at<=11;at++){
  reset();scheduled_kind=interrupt;inject_phase=at;run_kind(first);
  if(!injected)continue;
  assert(publications==2&&collisions==0&&!irq_disabled&&!pending_kind&&irq_saves==2&&irq_restores==2);cases++;
 }
 for(unsigned first=1;first<=4;first++){
  reset();inject_phase=3;foreign_kind=1;run_kind(first);assert(publications==1&&collisions==1);cases++;
  reset();inject_phase=3;foreign_kind=2;run_kind(first);assert(publications==1&&collisions==0&&bank_writes[1]==1);cases++;
 }
 reset();irq_disabled=1;run_kind(4);assert(irq_disabled==1&&publications==1&&irq_saves==1&&irq_restores==1);cases++;
 reset();tqe_push_mcast(&incoming,(void*)1,1,3,0);assert(queue_calls==1&&publications==0);cases++;
 reset();assert(topaz_swfwd_tqe_xmit(&fwt,&incoming,(void*)1)==1);assert(queue_calls==1&&publications==0);cases++;
 reset();fwt.out_port=4;assert(topaz_swfwd_tqe_xmit(&fwt,&incoming,NULL)==0);assert(!publications);cases++;
 printf("{\"executed_cases\":%u}\n",cases);
 return cases?0:1;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.candidate.read_text()
    root = Path(__file__).resolve().parents[1]
    header = root / "work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h"
    actual_header = header.read_text()
    publication = "\n".join(function(actual_header, signature) for signature in (
        "topaz_tqe_cpuif_port_to_num(", "__topaz_tqe_cpuif_ppctl_write(",
        "__topaz_tqe_cpuif_tx_start(", "\ntopaz_tqe_cpuif_tx_start("))
    publication = "static int " + publication
    publication = publication.replace("\n__topaz_tqe_cpuif_ppctl_write(", "\nstatic int __topaz_tqe_cpuif_ppctl_write(", 1)
    publication = publication.replace("\n__topaz_tqe_cpuif_tx_start(", "\nstatic void __topaz_tqe_cpuif_tx_start(", 1)
    publication = publication.replace("\ntopaz_tqe_cpuif_tx_start(", "\nstatic void topaz_tqe_cpuif_tx_start(", 1)
    chunks = [function(source, signature) for signature in (
        "static unsigned long omtqe_lhost_publish(", "static void omtqe_lhost_publish_end(",
        "int topaz_tqe_xmit(", "static void __sram_text tqe_push_mcast(",
        "static int topaz_swfwd_tqe_xmit(", "static int tqe_tx_buf(")]
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = args.output / "actual-four-writers.c"
    fixture.write_text(PRELUDE + publication + "\n".join(chunks) + TESTS)
    executable = args.output / "fixture.exe"
    command = [str(args.compiler), "-std=c11", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", str(fixture), "-o", str(executable)]
    (args.output / "compile.command.json").write_text(json.dumps(command, indent=2) + "\n")
    proc = subprocess.run(command, capture_output=True)
    (args.output / "compile.stderr").write_bytes(proc.stderr)
    assert proc.returncode == 0, proc.stderr.decode()
    run = subprocess.run([str(executable)], capture_output=True)
    (args.output / "run.stderr").write_bytes(run.stderr)
    (args.output / "run.stdout").write_bytes(run.stdout)
    assert run.returncode == 0, run.stderr.decode()
    executed = json.loads(run.stdout)
    result = {"schema": "openmitrastar.tqe-four-writer-irq-fixture/v1", "status": "PASS_SOURCE_ONLY_ACTUAL_FOUR_WRITERS",
              "hardware_accessed": False, "firmware_eligible": False,
              "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(), "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
              "source_writer_count": 4, "interrupt_arrival_slots_per_pair": 11, "writer_pairs": 16,
              "actual_bank_and_publication_header_functions_extracted": 4,
              "cpuif_header_sha256": hashlib.sha256(header.read_bytes()).hexdigest(),
              "executed_cases": executed["executed_cases"],
              "foreign_lhost_bank_collision_reproduced": True, "normal_muc_bank_independence_exercised": True,
              "prior_irq_state_restored": True, "queue_paths_preserved": True,
              "limits": ["Deterministic fake IRQ/MMIO/HBM fixture; no physical timing, RF or firmware acceptance.",
                         "Unbounded waits preserved, not exercised as hang; IRQ starvation remains NO_GO.",
                         "Cross-bank firmware writes do not honor local IRQ exclusion and still collide.",
                         "No complete module build or universal concurrency proof."]}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
