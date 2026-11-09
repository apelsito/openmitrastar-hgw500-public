"""SOURCE-only bounded LHOST bank admission with fail-closed ownership retention.

All four compiled writer paths use the same bounded READY/complete admission.
Post-publication uncertainty quarantines the bank; never retries or frees the
published payload. This is NOT a finished driver: retained multicast/queue
ownership needs a release/recovery contract, and HBM/MMIO waits remain separate.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

from prepare_tqe_bounded_admission_prototype import function

ROOT = Path(__file__).resolve().parents[1]
TQE = ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c"
CGQ = ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/topaz_congest_queue.c"
CONFIG = Path("/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/kernel/.config")

HEADER = r'''#ifndef OPENMITRASTAR_TQE_BOUNDED_OWNERSHIP_H
#define OPENMITRASTAR_TQE_BOUNDED_OWNERSHIP_H
/* Private SOURCE-only caller contract. Neither value is a kernel NET_XMIT code.
 * UNCERTAIN owns/retains payload; NEVER enqueue, retry, or call HBM cleanup.
 * REFUSED did not publish but payload may already have multicast refs: retain.
 */
#define OMTQE_OWNERSHIP_UNCERTAIN 0x40
#define OMTQE_OWNERSHIP_REFUSED 0x41
int omtqe_lhost_quarantined(void);
#endif
'''

CORE = r'''/* SOURCE-ONLY bounded local bank ownership. Exact UP/PREEMPT_NONE build.
 * Quarantine permanently refuses new publications; no reset/recovery exists.
 * HBM allocator/filter waits and foreign firmware bank writes remain unknown.
 * The retained descriptor is evidence/ownership only; it is never submitted again.
 */
#if defined(CONFIG_SMP) || defined(CONFIG_PREEMPT) || defined(CONFIG_PREEMPT_VOLUNTARY) || defined(CONFIG_TOPAZ_PCIE_TARGET)
#error "SOURCE-only ownership protocol requires UP/PREEMPT_NONE/non-PCIe"
#endif
#define OMTQE_READY_READ_MAX 1024U
#define OMTQE_COMPLETE_READ_MAX 1024U
static bool omtqe_bank_reserved;
static bool omtqe_bank_quarantined;
static bool omtqe_held_published;
static union topaz_tqe_cpuif_ppctl omtqe_held_descriptor;

int omtqe_lhost_quarantined(void)
{
	return READ_ONCE(omtqe_bank_quarantined);
}
EXPORT_SYMBOL(omtqe_lhost_quarantined);

static int omtqe_lhost_reserve(void)
{
	unsigned long flags;
	unsigned int count;
	int acquired = 0;
	local_irq_save(flags);
	if (omtqe_bank_quarantined || omtqe_bank_reserved)
		goto out;
	for (count = 0; count < OMTQE_READY_READ_MAX; count++) {
		if (!topaz_tqe_cpuif_tx_nready()) {
			omtqe_bank_reserved = true;
			acquired = 1;
			goto out;
		}
		cpu_relax();
	}
	/* READY refusal is known prepublication. Caller ownership stays unchanged.
	 * Permanently latch so later outputs cannot overwrite an unknown bank state. */
	omtqe_bank_quarantined = true;
out:
	local_irq_restore(flags);
	return acquired;
}

static void omtqe_lhost_cancel_reservation(void)
{
	unsigned long flags;
	local_irq_save(flags);
	omtqe_bank_reserved = false;
	local_irq_restore(flags);
}

static int omtqe_lhost_submit_reserved(const union topaz_tqe_cpuif_ppctl *ppctl)
{
	unsigned long flags;
	unsigned int count;
	int result = OMTQE_OWNERSHIP_UNCERTAIN;
	local_irq_save(flags);
	if (!omtqe_bank_reserved || omtqe_bank_quarantined) {
		/* An already-consumed direct/copy or pre-refcounted multicast output
		 * cannot be handed back. Retain its payload without any HBM operation. */
		if (!omtqe_bank_quarantined) {
			omtqe_held_descriptor = *ppctl;
			omtqe_held_published = false;
		}
		omtqe_bank_quarantined = true;
		goto out;
	}
	topaz_tqe_cpuif_tx_start(ppctl);
	wmb();
	for (count = 0; count < OMTQE_COMPLETE_READ_MAX; count++) {
		if (!topaz_tqe_cpuif_tx_nready()) {
			/* Preserve the original congestion result only after completion is
			 * observed. Never return CN for an uncompleted publication. */
			result = (qtn_mproc_sync_mem_read(TOPAZ_TQE_CPUIF_TXSTART(0)) &
				TOPAZ_TQE_CPUIF_TX_START_NOT_SUCCESS) ? NET_XMIT_CN : NET_XMIT_SUCCESS;
			goto out;
		}
		cpu_relax();
	}
	omtqe_held_descriptor = *ppctl;
	omtqe_held_published = true;
	omtqe_bank_quarantined = true;
out:
	omtqe_bank_reserved = false;
	local_irq_restore(flags);
	return result;
}

static int omtqe_lhost_submit(const union topaz_tqe_cpuif_ppctl *ppctl)
{
	if (!omtqe_lhost_reserve())
		return OMTQE_OWNERSHIP_REFUSED;
	return omtqe_lhost_submit_reserved(ppctl);
}

'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sha(TQE) == "929d89801045c2b5f421d4d40ca312c32feaf93612de6a575b9b362ab97d9aef"
    config = CONFIG.read_text()
    assert "CONFIG_PREEMPT_NONE=y" in config and "# CONFIG_SMP is not set" in config and "CONFIG_TOPAZ_PCIE_TARGET=y" not in config
    old_tqe, old_cgq = TQE.read_text(), CGQ.read_text()
    tqe = old_tqe.replace("#include <linux/module.h>", '#include <linux/module.h>\n#include "openmitrastar_tqe_bounded_ownership.h"', 1)
    old = function(tqe, "int topaz_tqe_xmit(")
    new = "int topaz_tqe_xmit(union topaz_tqe_cpuif_ppctl *pp_cntl)\n{\n\treturn omtqe_lhost_submit(pp_cntl);\n}"
    tqe = tqe.replace(old, CORE + new, 1)
    old = function(tqe, "void topaz_tqe_congest_queue_process(")
    new = old.replace("\tif (topaz_queue_congested", "\tif (omtqe_lhost_quarantined())\n\t\treturn; /* pre-owned multicast ref stays retained; no enqueue/free */\n\tif (topaz_queue_congested", 1)
    new = new.replace("\t\tret = congest_queue->xmit_func(ppctl);", "\t\tret = congest_queue->xmit_func(ppctl);\n\t\tif (ret == OMTQE_OWNERSHIP_UNCERTAIN || ret == OMTQE_OWNERSHIP_REFUSED)\n\t\t\treturn; /* retain; no requeue/retry/free on uncertainty */", 1)
    tqe = tqe.replace(old, new, 1)
    for signature, block in (
        ("static void __sram_text tqe_push_mcast(", '\t\ttopaz_tqe_wait();\n\t\tswitch_tqe_multi_proc_sem_down("tqe_push_mcast",__LINE__);\n\t\ttopaz_tqe_cpuif_tx_start(&ppctl);\n\t\tswitch_tqe_multi_proc_sem_up();'),
        ("static int topaz_swfwd_tqe_xmit(", '\t\twhile (topaz_tqe_cpuif_tx_nready());\n\t\tswitch_tqe_multi_proc_sem_down("topaz_swfwd_tqe_xmit",__LINE__);\n\t\ttopaz_tqe_cpuif_tx_start(&ctl);\n\t\tswitch_tqe_multi_proc_sem_up();'),
    ):
        old = function(tqe, signature)
        assert old.count(block) == 1
        operand = "&ppctl" if "mcast" in signature else "&ctl"
        new = old.replace(block, "\t\t(void)omtqe_lhost_submit(" + operand + ");\n\t\t/* Existing void/consumed return retains pre-owned payload on refusal. */", 1)
        if "mcast" in signature:
            new = new.replace("\t/*\n\t * VLAN egress", "\tif (omtqe_lhost_quarantined())\n\t\treturn; /* counted ref retained; never enter VLAN/HBM/queue cleanup */\n\t/*\n\t * VLAN egress", 1)
        tqe = tqe.replace(old, new, 1)
    old = function(tqe, "static uint32_t __sram_text tqe_push_mc_ports(")
    new = old.replace("\tmcast_ent = *mcast_ent_shared;", "\t/* On a quarantined bank, refuse before creating multicast refcounts. */\n\tif (omtqe_lhost_quarantined())\n\t\treturn 0;\n\tmcast_ent = *mcast_ent_shared;", 1)
    tqe = tqe.replace(old, new, 1)
    old = function(tqe, "static int topaz_swfwd_tqe_xmit(")
    new = old.replace("\tif (fwt_ent->out_port == TOPAZ_TQE_LHOST_PORT)", "\tif (omtqe_lhost_quarantined())\n\t\treturn 0; /* no publication; ordinary RX caller still owns descriptor */\n\tif (fwt_ent->out_port == TOPAZ_TQE_LHOST_PORT)", 1)
    tqe = tqe.replace(old, new, 1)
    old = function(tqe, "static int tqe_tx_buf(")
    start = old.index("\twhile (topaz_tqe_cpuif_tx_nready());")
    end = old.index("\n\treturn 0;", start)
    new = old[:start] + "\t(void)omtqe_lhost_submit_reserved(ppctl);\n\t/* skb was consumed: postsubmit uncertainty remains retained, never BUSY. */" + old[end:]
    tqe = tqe.replace(old, new, 1)
    old = function(tqe, "int tqe_tx(")
    new = old.replace("\tif (hbm_can_use) {", "\t/* Admission precedes skb/HBM mutation. A refused skb remains caller-owned. */\n\tif (!omtqe_lhost_reserve())\n\t\treturn NETDEV_TX_BUSY;\n\n\tif (hbm_can_use) {", 1)
    new = new.replace("\t\t\tkfree_skb(skb);\n\t\t\treturn NETDEV_TX_OK;", "\t\t\tkfree_skb(skb);\n\t\t\tomtqe_lhost_cancel_reservation();\n\t\t\treturn NETDEV_TX_OK;", 1)
    new = new.replace("\t\t\t/* buffer will be stored in gso_skb and re-attempted for xmit */\n\t\t\treturn NETDEV_TX_BUSY;", "\t\t\t/* Prepublication: skb/HBM ownership is unchanged. */\n\t\t\tomtqe_lhost_cancel_reservation();\n\t\t\treturn NETDEV_TX_BUSY;", 1)
    tqe = tqe.replace(old, new, 1)
    assert tqe.count("topaz_tqe_cpuif_tx_start(") == 1
    # Do not let queued payload cleanup or queue retry run on quarantined bank.
    cgq = old_cgq.replace("#include <linux/module.h>", '#include <linux/module.h>\n#include "openmitrastar_tqe_bounded_ownership.h"', 1)
    old = function(cgq, "__attribute__((section(\".sram.text\"))) int topaz_congest_queue_xmit(")
    new = old.replace("\tcongest_queue->xmit_entry++;", "\tif (omtqe_lhost_quarantined())\n\t\treturn 0; /* retain queue and stop retry scheduling */\n\tcongest_queue->xmit_entry++;", 1)
    new = new.replace("\t\tret = congest_queue->xmit_func(pp_cntl);", "\t\tret = congest_queue->xmit_func(pp_cntl);\n\t\tif (ret == OMTQE_OWNERSHIP_UNCERTAIN || ret == OMTQE_OWNERSHIP_REFUSED)\n\t\t\treturn 0; /* keep head: NEVER retry, dequeue or free uncertain ownership */", 1)
    cgq = cgq.replace(old, new, 1)
    old = function(cgq, "noinline static void topaz_congest_queue_clear(")
    new = old.replace("\tqueue->congest_drop += queue->qlen;", "\tif (omtqe_lhost_quarantined())\n\t\treturn; /* no HBM release while a bank output is uncertain */\n\tqueue->congest_drop += queue->qlen;", 1)
    cgq = cgq.replace(old, new, 1)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("switch_tqe.c", tqe), ("topaz_congest_queue.c", cgq), ("openmitrastar_tqe_bounded_ownership.h", HEADER)):
        (args.output / name).write_text(value, newline="\n")
    patch = "".join("".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), fromfile="a/" + name, tofile="b/" + name)) for name, a, b in (("switch_tqe.c", old_tqe, tqe), ("topaz_congest_queue.c", old_cgq, cgq)))
    (args.output / "bounded-local-ownership.patch").write_text(patch)
    result = {"schema": "openmitrastar.tqe-bounded-local-ownership/v1", "status": "SOURCE_ONLY_BOUNDED_TQE_RETENTION_NO_GO_MODULE",
              "hardware_accessed": False, "firmware_eligible": False, "ready_read_budget": 1024, "completion_read_budget": 1024,
              "source_sha256": sha(TQE), "queue_source_sha256": sha(CGQ), "config_sha256": sha(CONFIG),
              "candidate_files": {name: sha(args.output / name) for name in ("switch_tqe.c", "topaz_congest_queue.c", "openmitrastar_tqe_bounded_ownership.h")},
              "ownership": "Prepublication tqe_tx refusal preserves skb; publication timeout retains descriptor/payload and quarantines bank, never CN retry. Multicast pre-refcounts remain held on midbatch refusal. Quarantined congestion queue cannot retry or clear/free.",
              "limits": ["Retained multicast refs/queue memory are deliberate fail-closed leaks; no release/recovery lifecycle qualified.",
                         "Existing HBM allocation/filter/VLAN drop paths may still wait unbounded outside TQE poll interval.",
                         "Foreign firmware LHOST bank writes remain an unqualified collision counterexample.",
                         "Private quarantine symbol creates a module dependency cycle with congestion queue; complete closure/lifecycle needs restructuring before module build.",
                         "Core source/fixture only; no module build, hardware timing, RF/client traffic, persistence or release acceptance."]}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
