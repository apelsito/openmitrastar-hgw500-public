"""Actual bounded bank core and four writer fixture with fake IRQ/MMIO/HBM.

Demonstrates prepublication ownership, postpublication retention and no retry.
Source-only: HBM paths, module dependency/lifecycle and foreign writers remain
explicitly unqualified. No hardware or module loading is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import function
from test_tqe_lhost_writer_serialization import PRELUDE as IRQ_PRELUDE

BOUNDED = r'''
#define READ_ONCE(x) (x)
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
#define OMTQE_READY_READ_MAX 1024U
#define OMTQE_COMPLETE_READ_MAX 1024U
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 16
#define TOPAZ_HBM_BUF_EMAC_RX_SIZE 4096
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_OWNER_LH_TX_TQE 1
#define OPENMITRASTAR_QDRV_V89_PAIR 1
#define M_VLAN_TAGGED 1
#define M_FLAG_ISSET(s,f) ((s)->flags&(f))
#define QVLAN_PKTCTRL_LEN 4
#define unlikely(x) (x)
#define KERN_ERR ""
#define printk(...) ((void)0)
#define printk_ratelimit() 0
struct shinfo { int dataref; };
struct sk_buff { unsigned len; void *data; int users;struct shinfo sh;int hbm_no_free,freed,flags; };
#define skb_shinfo(s) (&(s)->sh)
#define refcount_read(p) (*(p))
#define atomic_read(p) (*(p))
static unsigned ready_reads,complete_reads,ready_on,complete_on,completed_status,postsubmit;
static unsigned free_count,alloc_count,hbm_available,relaxes,queue_dequeues,queue_frees,queue_retries;
static bool omtqe_bank_reserved,omtqe_bank_quarantined,omtqe_held_published;
static union topaz_tqe_cpuif_ppctl omtqe_held_descriptor;
static unsigned char original_buf[128],copy_buf[128];
static int direct_pool;
static void cpu_relax(void){relaxes++;}
static int ready_state(void){
 phase(1);
 if(postsubmit){complete_reads++;return !complete_on||complete_reads<complete_on;}
 ready_reads++;return !ready_on||ready_reads<ready_on;
}
static int status_state(uint32_t address){assert(address==0xe1034038U);return completed_status;}
static void *topaz_hbm_get_payload_virt(int pool){(void)pool;alloc_count++;return hbm_available?copy_buf:NULL;}
static int topaz_hbm_payload_get_pool_bus(void*p){(void)p;return direct_pool;}
static int topaz_hbm_pool_valid(int p){return p>=0&&p<4;}
static void topaz_hbm_flush_skb_cache(struct sk_buff*s){(void)s;}
static void topaz_hbm_filter_txdone_pool(void){}
static void topaz_hbm_debug_stamp(void*a,int b,unsigned c){(void)a;(void)b;(void)c;}
static void *qtn_vlan_get_info(void*p){return p;}
static void *align_buf_cache(void*p){return p;}
static size_t align_buf_cache_size(void*p,size_t n){(void)p;return n;}
static void flush_and_inv_dcache_range(uintptr_t a,uintptr_t b){assert(b>=a);}
static void kfree_skb(struct sk_buff*s){assert(!s->freed);s->freed=1;free_count++;}
#define dev_kfree_skb(s) kfree_skb(s)
'''

TESTS = r'''
static unsigned cases;
static void clear_all(void){
 reset();omtqe_bank_reserved=omtqe_bank_quarantined=omtqe_held_published=false;
 memset(&omtqe_held_descriptor,0,sizeof(omtqe_held_descriptor));
 ready_reads=complete_reads=free_count=alloc_count=relaxes=postsubmit=completed_status=0;
 ready_on=complete_on=1;hbm_available=1;direct_pool=-1;queue_dequeues=queue_frees=queue_retries=0;
}
static struct sk_buff fresh_skb(void){struct sk_buff s={.len=64,.data=original_buf,.users=1,.sh={1}};return s;}
static void assert_quarantined_no_future_submit(void){
 union topaz_tqe_cpuif_ppctl p={0};unsigned before=publications;
 assert(topaz_tqe_xmit(&p)==OMTQE_OWNERSHIP_REFUSED);
 assert(publications==before&&!irq_disabled&&!omtqe_bank_reserved);
}
static void run_kind(unsigned kind){
 union topaz_tqe_cpuif_ppctl ctl={0};
 if(kind==1){int r=topaz_tqe_xmit(&ctl);assert(r==NET_XMIT_SUCCESS||r==OMTQE_OWNERSHIP_REFUSED);}
 else if(kind==2)tqe_push_mcast(&incoming,NULL,1,3,0);
 else if(kind==3)(void)topaz_swfwd_tqe_xmit(&fwt,&incoming,NULL);
 else if(kind==4){struct sk_buff s=fresh_skb();(void)tqe_tx(&ctl,&s);}
}
static void reset(void){
 irq_disabled=irq_saves=irq_restores=publications=collisions=queue_calls=drops=waits=0;
 pending_kind=scheduled_kind=inject_phase=injected=foreign_kind=foreign_inflight=0;
 memset(bank_writes,0,sizeof(bank_writes));last_status=0;
}
int main(void){
 union topaz_tqe_cpuif_ppctl p={0};struct sk_buff s;int r;
 clear_all();ready_on=0;r=topaz_tqe_xmit(&p);assert(r==OMTQE_OWNERSHIP_REFUSED&&ready_reads==1024&&publications==0&&omtqe_bank_quarantined&&!irq_disabled);assert_quarantined_no_future_submit();cases++;
 clear_all();ready_on=1024;assert(topaz_tqe_xmit(&p)==0&&ready_reads==1024&&complete_reads==1&&publications==1&&!irq_disabled);cases++;
 clear_all();ready_on=1025;assert(topaz_tqe_xmit(&p)==OMTQE_OWNERSHIP_REFUSED&&publications==0);cases++;
 clear_all();complete_on=0;r=topaz_tqe_xmit(&p);assert(r==OMTQE_OWNERSHIP_UNCERTAIN&&publications==1&&complete_reads==1024&&omtqe_held_published&&omtqe_bank_quarantined&&!irq_disabled);assert_quarantined_no_future_submit();cases++;
 clear_all();complete_on=1024;assert(topaz_tqe_xmit(&p)==0&&complete_reads==1024&&!omtqe_bank_quarantined);cases++;
 clear_all();complete_on=1025;assert(topaz_tqe_xmit(&p)==OMTQE_OWNERSHIP_UNCERTAIN);cases++;
 clear_all();completed_status=0x40000000U;assert(topaz_tqe_xmit(&p)==NET_XMIT_CN&&!omtqe_bank_quarantined&&complete_reads==1);cases++;
 clear_all();ready_on=0;s=fresh_skb();assert(tqe_tx(&p,&s)==NETDEV_TX_BUSY&&!s.freed&&!s.hbm_no_free&&!alloc_count);cases++;
 clear_all();hbm_available=0;s=fresh_skb();assert(tqe_tx(&p,&s)==NETDEV_TX_BUSY&&!s.freed&&!omtqe_bank_reserved&&!omtqe_bank_quarantined);cases++;
 clear_all();s=fresh_skb();s.len=4096;assert(tqe_tx(&p,&s)==NETDEV_TX_OK&&s.freed&&!publications&&!omtqe_bank_reserved);cases++;
 clear_all();complete_on=0;s=fresh_skb();assert(tqe_tx(&p,&s)==NETDEV_TX_OK&&s.freed&&free_count==1&&publications==1&&omtqe_bank_quarantined);assert_quarantined_no_future_submit();cases++;
 clear_all();direct_pool=1;complete_on=0;s=fresh_skb();assert(tqe_tx(&p,&s)==0&&s.freed&&s.hbm_no_free&&free_count==1&&alloc_count==0);cases++;
 clear_all();complete_on=0;tqe_push_mcast(&incoming,NULL,1,3,0);assert(publications==1&&omtqe_bank_quarantined);tqe_push_mcast(&incoming,NULL,1,4,0);assert(publications==1);cases++;
 clear_all();complete_on=0;assert(topaz_swfwd_tqe_xmit(&fwt,&incoming,NULL)==1&&publications==1&&omtqe_bank_quarantined);assert(topaz_swfwd_tqe_xmit(&fwt,&incoming,NULL)==0&&publications==1);cases++;
 for(unsigned first=1;first<=4;first++)for(unsigned intr=1;intr<=4;intr++)for(unsigned at=1;at<=8;at++){
  clear_all();scheduled_kind=intr;inject_phase=at;run_kind(first);
  assert(!irq_disabled&&!omtqe_bank_reserved&&collisions==0&&publications<=2);cases++;
 }
 clear_all();irq_disabled=1;assert(topaz_tqe_xmit(&p)==0&&irq_disabled==1);cases++;
 clear_all();inject_phase=3;foreign_kind=1;assert(topaz_tqe_xmit(&p)==0&&collisions==1);cases++;
 printf("{\"executed_cases\":%u}\n",cases);return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = (args.candidate / "switch_tqe.c").read_text()
    root = Path(__file__).resolve().parents[1]
    header = (root / "work/sources/Quantenna-GPL/include/qtn/topaz_tqe_cpuif.h").read_text()
    publication = "\n".join(function(header, signature) for signature in (
        "topaz_tqe_cpuif_port_to_num(", "__topaz_tqe_cpuif_ppctl_write(",
        "__topaz_tqe_cpuif_tx_start(", "\ntopaz_tqe_cpuif_tx_start("))
    publication = "static int " + publication
    publication = publication.replace("\n__topaz_tqe_cpuif_ppctl_write(", "\nstatic int __topaz_tqe_cpuif_ppctl_write(", 1)
    publication = publication.replace("\n__topaz_tqe_cpuif_tx_start(", "\nstatic void __topaz_tqe_cpuif_tx_start(", 1)
    publication = publication.replace("\ntopaz_tqe_cpuif_tx_start(", "\nstatic void topaz_tqe_cpuif_tx_start(", 1)
    functions = [function(source, signature) for signature in (
        "int omtqe_lhost_quarantined(", "static int omtqe_lhost_reserve(", "static void omtqe_lhost_cancel_reservation(",
        "static int omtqe_lhost_submit_reserved(", "static int omtqe_lhost_submit(", "int topaz_tqe_xmit(",
        "static void __sram_text tqe_push_mcast(", "static int topaz_swfwd_tqe_xmit(", "static int tqe_tx_buf(", "int tqe_tx(")]
    prelude = IRQ_PRELUDE
    # Preserve the IRQ interleaving hooks, but READY and TX completion now follow
    # independently controlled finite fake hardware progress.
    prelude = prelude.replace("static int topaz_tqe_cpuif_tx_nready(void){phase(1);return 0;}", "static int ready_state(void);\nstatic int topaz_tqe_cpuif_tx_nready(void){return ready_state();}")
    prelude = prelude.replace("static uint32_t qtn_mproc_sync_mem_read(uint32_t address){assert(address==0xe1034038U);phase(10);return last_status;}", "static int status_state(uint32_t address);\nstatic uint32_t qtn_mproc_sync_mem_read(uint32_t address){return status_state(address);}")
    prelude = prelude.replace("static void run_kind(unsigned kind);", "static void run_kind(unsigned kind);\nstatic void reset(void);\nstatic unsigned postsubmit;")
    prelude = prelude.replace("publications++;bank_writes[0]++;last_status=0;phase(9);", "publications++;bank_writes[0]++;last_status=0;postsubmit=1;phase(9);")
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = args.output / "actual-bounded-writers.c"
    fixture.write_text(prelude + BOUNDED + publication + "\n".join(functions) + TESTS)
    command = [str(args.compiler), "-O1", "-std=c11", "-Wno-unused-function", str(fixture), "-o", str(args.output / "fixture.exe")]
    proc = subprocess.run(command, capture_output=True)
    (args.output / "compile.stderr").write_bytes(proc.stderr)
    assert proc.returncode == 0, proc.stderr.decode()
    run = subprocess.run([str(args.output / "fixture.exe")], capture_output=True)
    (args.output / "run.stderr").write_bytes(run.stderr)
    (args.output / "run.stdout").write_bytes(run.stdout)
    assert run.returncode == 0, run.stderr.decode()
    result = {"schema": "openmitrastar.tqe-bounded-ownership-fixture/v1", "status": "PASS_ACTUAL_BOUNDED_WRITER_CORE_SOURCE_ONLY",
              "hardware_accessed": False, "firmware_eligible": False, "executed_cases": json.loads(run.stdout)["executed_cases"],
              "source_sha256": hashlib.sha256((args.candidate / "switch_tqe.c").read_bytes()).hexdigest(),
              "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(), "postsubmit_timeout_never_retry_CN": True,
              "prepublication_skb_busy_untouched": True, "irq_poll_iterations_bounded": True,
              "foreign_bank_collision_reproduced": True,
              "limits": ["Source-only actual bank/4writer fixture; queue lifecycle and module cycle remain NO_GO.",
                         "Multicast missingrefs deliberately retained, not reclaimed; no throughput/recovery acceptance.",
                         "FakeMMIO/HBM progress; actual HBM waits and foreign writers remain unknown."]}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
