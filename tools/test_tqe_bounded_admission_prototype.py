"""Compile actual isolated prototype functions with fake skb/HBM/MMIO, no hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_tqe_bounded_admission_prototype import ROOT, function, sha

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define EXPORT_SYMBOL(x)
#define __iomem
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 16
#define KERN_ERR ""
#define TOPAZ_HBM_BUF_EMAC_RX_SIZE 4096
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_EMAC_TX_DONE_POOL 2
#define TOPAZ_HBM_OWNER_LH_TX_TQE 1
#define QVLAN_PKTCTRL_LEN 4
#define M_VLAN_TAGGED 1
#define M_FLAG_ISSET(s, f) ((s)->flags & (f))
#define unlikely(x) (x)
#define refcount_read(x) (*(x))
#define atomic_read(x) (*(x))
#define printk_ratelimit() 0
#define printk(...) ((void)0)
#define QTN_MULTI_PROCESS_TQE_SEMA 15U
#define QTN_MULTI_PROCESSOR_SEMA_KEY_SHIFT 28U
#define TOPAZ_MPROC_SEMA 1U
#define TQE_SEMA_GET_MAX 65535U
enum topaz_mproc_tqe_sem_id { TOPAZ_MPROC_TQE_SEM_LHOST = 1 };

union topaz_tqe_cpuif_ppctl {
 struct { void *pkt; long buff_ptr_offset; unsigned long length; int buff_pool_num; int out_port; } data;
};
struct fake_shinfo { int dataref; };
struct sk_buff { unsigned int len; unsigned char *data; int users; struct fake_shinfo sh;
 int flags; int hbm_no_free; int freed; };
#define skb_shinfo(s) (&(s)->sh)
static unsigned char original_buf[5008], copy_buf[5008];
static bool vlan_enabled;
static int pool_of_original, hbm_available, irq_disabled, tqe_sem_en;
static unsigned ready_reads, ready_on, relax_count, alloc_count, copy_count,
 cache_count, stamp_count, free_count, submit_count, hbm_direct_held, warnings,
 sem_reads, sem_writes, sem_claim_writes, sem_release_writes, sem_owner,
 sem_claim_after, toggle_sem_on_submit, stolen_on_submit, foreign_publish_during_alloc, foreign_inflight, collision_submits;
static void irq_save(unsigned long *flags) { *flags = irq_disabled; irq_disabled=1; }
static void irq_restore(unsigned long flags) { irq_disabled=(int)flags; }
#define local_irq_save(f) irq_save(&(f))
#define local_irq_restore(f) irq_restore((f))
#define WARN_ONCE(c, ...) do { if (c) warnings++; } while (0)
static void cpu_relax(void) { relax_count++; }
static uint32_t qtn_mproc_sync_mem_read(uint32_t reg) { assert(reg==TOPAZ_MPROC_SEMA); sem_reads++; return sem_owner; }
static void qtn_mproc_sync_mem_write(uint32_t reg, uint32_t value) {
 assert(reg==TOPAZ_MPROC_SEMA); sem_writes++;
 if (value & QTN_MULTI_PROCESS_TQE_SEMA) {
  sem_claim_writes++;
  if (!sem_owner && (!sem_claim_after || sem_claim_writes>=sem_claim_after)) sem_owner=value&15U;
  if (sem_owner!=1 && sem_claim_after && sem_claim_writes>=sem_claim_after) sem_owner=1;
 } else {
  sem_release_writes++; assert(sem_owner==1); sem_owner=0;
 }
}
static uintptr_t virt_to_bus(const void *p) { return (uintptr_t)p; }
static int8_t topaz_hbm_payload_get_pool_bus(void *p) {
 return p==original_buf+4 ? (int8_t)pool_of_original : 0;
}
static bool topaz_hbm_pool_valid(int8_t pool) { return pool>=0 && pool<4; }
static long topaz_hbm_payload_buff_ptr_offset_bus(void *p, int8_t pool, void *unused) {
 (void)p; (void)pool; (void)unused; return 64;
}
static void topaz_hbm_flush_skb_cache(struct sk_buff *s) { (void)s; cache_count++; }
static void topaz_hbm_filter_txdone_pool(void) { }
static void *topaz_hbm_get_payload_virt(int8_t pool) { assert(pool==0); alloc_count++; if(foreign_publish_during_alloc) foreign_inflight=1; return hbm_available ? copy_buf+4 : NULL; }
static void topaz_hbm_debug_stamp(void *p, int owner, unsigned int len) { (void)p; (void)owner; (void)len; stamp_count++; }
static void *qtn_vlan_get_info(void *p) { return (unsigned char *)p-4; }
static void *align_buf_cache(void *p) { return p; }
static size_t align_buf_cache_size(void *p, size_t n) { (void)p; return n; }
static void flush_and_inv_dcache_range(uintptr_t a, uintptr_t b) { assert(b>=a); cache_count++; }
static void *test_memcpy(void *to, const void *from, size_t n) { copy_count++; return memcpy(to,from,n); }
#define memcpy test_memcpy
static void kfree_skb(struct sk_buff *s) { assert(!s->freed); s->freed=1; free_count++; if(s->hbm_no_free) hbm_direct_held++; }
#define dev_kfree_skb(s) kfree_skb(s)
static int topaz_tqe_cpuif_tx_nready(void) {
 assert(irq_disabled); ready_reads++; return !ready_on || ready_reads<ready_on;
}
static void topaz_tqe_cpuif_tx_start(const union topaz_tqe_cpuif_ppctl *ctl) {
 assert(irq_disabled); assert(free_count==1); assert(ctl->data.pkt); submit_count++; if(foreign_inflight) collision_submits++;
 if(toggle_sem_on_submit) tqe_sem_en=0;
 if(stolen_on_submit) sem_owner=2;
}
'''

TESTS = r'''
static unsigned checks, cases;
#define CHECK(x) do { checks++; assert(x); } while (0)
static struct sk_buff fresh(void) {
 struct sk_buff s = { .len=64,.data=original_buf+4,.users=1,.sh={1} };
 pool_of_original=-1; hbm_available=1; irq_disabled=0; tqe_sem_en=0;
 ready_reads=relax_count=alloc_count=copy_count=cache_count=stamp_count=free_count=submit_count=hbm_direct_held=warnings=0;
 sem_reads=sem_writes=sem_claim_writes=sem_release_writes=sem_owner=sem_claim_after=toggle_sem_on_submit=stolen_on_submit=foreign_publish_during_alloc=foreign_inflight=collision_submits=0;
 ready_on=1; vlan_enabled=false; cases++; return s;
}
static void verify_untouched(struct sk_buff *s) {
 CHECK(!s->freed); CHECK(!s->hbm_no_free); CHECK(!alloc_count); CHECK(!copy_count);
 CHECK(!cache_count); CHECK(!stamp_count); CHECK(!submit_count); CHECK(!hbm_direct_held);
}
static void run(void) {
 union topaz_tqe_cpuif_ppctl ctl = {0}; struct sk_buff s; int r;
 s=fresh(); ready_on=0; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(ready_reads==1024); CHECK(relax_count==1024); CHECK(!irq_disabled); verify_untouched(&s);
 /* Exercise actual qdrv BUSY handling: exactly one caller free. */
 if(r==NETDEV_TX_BUSY) kfree_skb(&s); CHECK(free_count==1);
 s=fresh(); ready_on=1024; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(ready_reads==1024); CHECK(relax_count==1023); CHECK(submit_count==1); CHECK(free_count==1); CHECK(!irq_disabled);
 s=fresh(); ready_on=1025; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(ready_reads==1024); verify_untouched(&s);
 s=fresh(); hbm_available=0; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(alloc_count==1); CHECK(!s.freed); CHECK(!s.hbm_no_free); CHECK(!submit_count); CHECK(!copy_count); CHECK(!irq_disabled);
 s=fresh(); r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(s.freed); CHECK(alloc_count==1); CHECK(copy_count==1); CHECK(cache_count==1); CHECK(stamp_count==1); CHECK(ctl.data.pkt==copy_buf+4); CHECK(ctl.data.length==64); CHECK(submit_count==1); CHECK(!irq_disabled);
 s=fresh(); pool_of_original=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(s.hbm_no_free); CHECK(hbm_direct_held==1); CHECK(free_count==1); CHECK(!alloc_count); CHECK(!copy_count); CHECK(ctl.data.pkt==s.data); CHECK(submit_count==1);
 s=fresh(); pool_of_original=1; ready_on=0; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); verify_untouched(&s);
 s=fresh(); pool_of_original=1; s.users=2; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(!s.hbm_no_free); CHECK(alloc_count==1); CHECK(copy_count==1); CHECK(submit_count==1);
 s=fresh(); pool_of_original=1; s.sh.dataref=2; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(!s.hbm_no_free); CHECK(alloc_count==1); CHECK(copy_count==1);
 s=fresh(); pool_of_original=1; vlan_enabled=true; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(!s.hbm_no_free); CHECK(alloc_count==1); CHECK(copy_count==1);
 s=fresh(); s.flags=M_VLAN_TAGGED; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(copy_count==2); CHECK(submit_count==1);
 s=fresh(); s.len=4096; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(s.freed); CHECK(!alloc_count); CHECK(!submit_count); CHECK(!irq_disabled);
 s=fresh(); irq_disabled=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(irq_disabled==1);
 /* Deliberate NO_GO counterexample: a writer on another CPU which does not
  * honor our exclusion can publish after READY and before this publication.
  * IRQ exclusion alone cannot prevent it. A passing test documents the hazard,
  * it does not assert safe multiwriter operation. */
 s=fresh(); foreign_publish_during_alloc=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(foreign_inflight==1); CHECK(collision_submits==1);
#ifdef CONFIG_TOPAZ_PCIE_TARGET
 s=fresh(); tqe_sem_en=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(sem_claim_writes==1); CHECK(sem_release_writes==1); CHECK(sem_owner==0); CHECK(!irq_disabled);
 s=fresh(); tqe_sem_en=1; ready_on=0; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(sem_claim_writes==1); CHECK(sem_release_writes==1); CHECK(!sem_owner); verify_untouched(&s);
 s=fresh(); tqe_sem_en=1; sem_owner=2; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(sem_claim_writes==65535); CHECK(!sem_release_writes); CHECK(sem_owner==2); CHECK(!ready_reads); CHECK(!irq_disabled); verify_untouched(&s);
 s=fresh(); tqe_sem_en=1; sem_owner=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(!sem_writes); CHECK(sem_owner==1); CHECK(!ready_reads); verify_untouched(&s);
 s=fresh(); tqe_sem_en=1; sem_owner=2; sem_claim_after=4; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(sem_claim_writes==4); CHECK(sem_release_writes==1); CHECK(!sem_owner);
 s=fresh(); tqe_sem_en=1; hbm_available=0; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_BUSY); CHECK(!s.freed); CHECK(sem_release_writes==1); CHECK(!sem_owner);
 s=fresh(); tqe_sem_en=1; s.len=4096; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(s.freed); CHECK(sem_release_writes==1); CHECK(!sem_owner);
 s=fresh(); tqe_sem_en=1; toggle_sem_on_submit=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(sem_release_writes==1); CHECK(!sem_owner); CHECK(tqe_sem_en==0);
 s=fresh(); tqe_sem_en=1; stolen_on_submit=1; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(!sem_release_writes); CHECK(sem_owner==2); CHECK(warnings==1); CHECK(!irq_disabled);
#else
 s=fresh(); tqe_sem_en=1; sem_owner=2; r=tqe_tx(&ctl,&s); CHECK(r==NETDEV_TX_OK); CHECK(!sem_writes); CHECK(sem_owner==2);
#endif
 printf("{\"cases\":%u,\"checks\":%u}\n",cases,checks);
}
int main(void) { run(); return 0; }
'''


def linux(path: Path) -> str:
    path = path.resolve()
    return "/mnt/" + path.drive[0].lower() + str(path)[2:].replace("\\", "/")


def test(candidate: Path, out: Path) -> dict:
    source = candidate.read_text(encoding="utf-8")
    primitives = (ROOT / "work/sources/Quantenna-GPL/include/qtn/mproc_sync.h").read_text()
    primitive_functions = "\n".join(function(primitives, name) for name in (
        "_qtn_mproc_3way_tqe_sem_down(", "_qtn_mproc_3way_tqe_sem_up("))
    # Add actual return types and RUBY_INLINE declarators: the parser starts at name.
    primitive_functions = primitive_functions.replace("_qtn_mproc_3way", "static int _qtn_mproc_3way", 1)
    primitive_functions = primitive_functions.replace("\n_qtn_mproc_3way_tqe_sem_up", "\nstatic int _qtn_mproc_3way_tqe_sem_up", 1)
    helper_start = source.index("#define OMTQE_READY_POLL_MAX")
    helper_end = source.index("static int tqe_tx_buf(", helper_start)
    extracted = source[helper_start:helper_end] + function(source, "static int tqe_tx_buf(") + "\n" + function(source, "int tqe_tx(")
    out.mkdir(parents=True, exist_ok=False)
    harness = out / "actual-functions-fixture.c"
    harness.write_text(PRELUDE + primitive_functions + "\n" + extracted + TESTS, encoding="utf-8", newline="\n")
    lanes = {}
    for lane in ("local", "pcie"):
        exe = out / (lane + "-fixture")
        command = ["wsl.exe", "-d", "REA-Linux", "-e", "gcc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Wno-unused-function", "-Wno-unused-label", "-Wno-misleading-indentation", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-DOPENMITRASTAR_QDRV_V89_PAIR=1"]
        if lane == "pcie":
            command += ["-DCONFIG_TOPAZ_PCIE_TARGET=1"]
        command += [linux(harness), "-o", linux(exe)]
        built = subprocess.run(command, capture_output=True, timeout=60)
        (out / (lane + "-build.stdout")).write_bytes(built.stdout)
        (out / (lane + "-build.stderr")).write_bytes(built.stderr)
        if built.returncode:
            raise RuntimeError(built.stderr.decode())
        run = subprocess.run(["wsl.exe", "-d", "REA-Linux", "-e", linux(exe)], capture_output=True, timeout=60)
        (out / (lane + "-run.stdout")).write_bytes(run.stdout)
        (out / (lane + "-run.stderr")).write_bytes(run.stderr)
        if run.returncode:
            raise RuntimeError(run.stderr.decode())
        lanes[lane] = json.loads(run.stdout)
    result = {"status": "PASS_ACTUAL_FUNCTION_FAULT_FIXTURE_SOURCE_ONLY", "candidate_sha256": sha(candidate),
              "harness_sha256": sha(harness), "mproc_primitives_source_sha256": sha(ROOT / "work/sources/Quantenna-GPL/include/qtn/mproc_sync.h"), "lanes": lanes, "hardware_accessed": False,
              "counterexample": "A noncooperating foreign CPUIF writer publishes between admission and TXSTART. Both lanes reproduce collision; universal arbitration remains NO_GO.",
              "module_status": "NO_GO_MODULE_FULL_PROVENANCE_AND_UNIVERSAL_ARBITRATION_UNPROVEN",
              "not_proved": ["Hardware performance or elapsed time", "Bounded HBM operations", "SMP or competing CPUIF writer serialization", "Firmware/radio/client/release acceptance"]}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(test(args.candidate, args.out), indent=2))
