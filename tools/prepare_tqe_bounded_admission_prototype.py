"""Create an isolated, SOURCE-ONLY TQE admission prototype. Never touches hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c"
MODULE = ROOT / "outputs/rea/arc700-20261021-r2/tqe-current/switch_tqe.ko"
REA = ROOT / "outputs/rea/arc700-20261021-r2/tqe-rea-tx/rea.json"
SOURCE_SHA = "929d89801045c2b5f421d4d40ca312c32feaf93612de6a575b9b362ab97d9aef"
MODULE_SHA = "bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f"

HELPERS = r'''/* SOURCE-ONLY PROTOTYPE: not a qualified module or hardware release.
 * Bound READY polling before changing skb/HBM ownership. IRQ exclusion only
 * serializes this CPU; all CPUIF writers and SMP require separate qualification.
 * This does NOT bound the existing HBM allocator/filter waits or MMIO bus stalls.
 */
#define OMTQE_READY_POLL_MAX 1024U

struct omtqe_tx_admission {
	unsigned long irq_flags;
	bool sem_owned;
};

static void omtqe_tx_admission_release(struct omtqe_tx_admission *admission)
{
#ifdef CONFIG_TOPAZ_PCIE_TARGET
	if (admission->sem_owned) {
		/* Release only an ownership acquired by this call, independent of a
		 * later tqe_sem_en change. Never unlock somebody else's semaphore. */
		WARN_ONCE(!_qtn_mproc_3way_tqe_sem_up(TOPAZ_MPROC_TQE_SEM_LHOST),
			"omtqe admission lost semaphore ownership\n");
		admission->sem_owned = false;
	}
#endif
	local_irq_restore(admission->irq_flags);
}

static int omtqe_tx_admit(struct omtqe_tx_admission *admission)
{
	unsigned int poll;

	admission->sem_owned = false;
	local_irq_save(admission->irq_flags);
#ifdef CONFIG_TOPAZ_PCIE_TARGET
	if (tqe_sem_en) {
		/* The OEM primitive accepts an already-owned LHOST semaphore.
		 * Refuse stale/nested ownership rather than stealing and releasing it. */
		if ((qtn_mproc_sync_mem_read(TOPAZ_MPROC_SEMA) &
		     QTN_MULTI_PROCESS_TQE_SEMA) == TOPAZ_MPROC_TQE_SEM_LHOST)
			goto busy;
		/* Exactly one internally bounded attempt (TQE_SEMA_GET_MAX=65535).
		 * The legacy wrapper retries this primitive forever; do not call it. */
		if (!_qtn_mproc_3way_tqe_sem_down(TOPAZ_MPROC_TQE_SEM_LHOST))
			goto busy;
		admission->sem_owned = true;
	}
#endif
	for (poll = 0; poll < OMTQE_READY_POLL_MAX; poll++) {
		if (!topaz_tqe_cpuif_tx_nready())
			return 1;
		cpu_relax();
	}
busy:
	omtqe_tx_admission_release(admission);
	return 0;
}

'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function(text: str, signature: str) -> str:
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def create(out: Path) -> dict:
    if sha(SOURCE) != SOURCE_SHA or sha(MODULE) != MODULE_SHA:
        raise ValueError("source/module pin drift")
    evidence = json.loads(REA.read_text(encoding="utf-8"))
    assembly = evidence["data"]["raw_result"]["value"]["assembly"]
    for required in ("0x10f8e: jl 0xf0001b0", "0x1100c: ld_s r0, r1",
                     "0x11010: bne_s 0x00011002", "0x1106c: st_s r0, r1"):
        if required not in assembly:
            raise ValueError("exact REA assembly anchor missing: " + required)
    original = SOURCE.read_bytes().decode()
    old_buf = function(original, "static int tqe_tx_buf(")
    new_buf = old_buf.replace(
        '\twhile (topaz_tqe_cpuif_tx_nready());\n\t\n\tswitch_tqe_multi_proc_sem_down("tqe_tx_buf",__LINE__);\n\ttopaz_tqe_cpuif_tx_start(ppctl);\n\tswitch_tqe_multi_proc_sem_up();',
        '\t/* Caller holds admission through this first publication. */\n\ttopaz_tqe_cpuif_tx_start(ppctl);')
    if old_buf == new_buf:
        raise ValueError("source wait/submit anchor drift")
    old_tx = function(original, "int tqe_tx(")
    new_tx = old_tx.replace("\tunsigned int data_len = skb->len;", "\tstruct omtqe_tx_admission admission;\n\tunsigned int data_len = skb->len;", 1)
    new_tx = new_tx.replace("\tif (hbm_can_use) {", "\t/* On refusal the skb, hbm_no_free and pool ownership are untouched. */\n\tif (!omtqe_tx_admit(&admission))\n\t\treturn NETDEV_TX_BUSY;\n\n\tif (hbm_can_use) {", 1)
    new_tx = new_tx.replace("\t\t\tkfree_skb(skb);\n\t\t\treturn NETDEV_TX_OK;", "\t\t\tkfree_skb(skb);\n\t\t\tomtqe_tx_admission_release(&admission);\n\t\t\treturn NETDEV_TX_OK;", 1)
    new_tx = new_tx.replace("\t\t\t/* buffer will be stored in gso_skb and re-attempted for xmit */\n\t\t\treturn NETDEV_TX_BUSY;", "\t\t\t/* Caller still owns skb: qdrv drops it; EMAC may retry it. */\n\t\t\tomtqe_tx_admission_release(&admission);\n\t\t\treturn NETDEV_TX_BUSY;", 1)
    new_tx = new_tx.replace("\ttqe_tx_buf(ppctl, buf_virt, data_len, pool);", "\ttqe_tx_buf(ppctl, buf_virt, data_len, pool);\n\tomtqe_tx_admission_release(&admission);", 1)
    if new_tx.count("omtqe_tx_admission_release(&admission)") != 3:
        raise ValueError("all acquired-admission return sites must release")
    candidate = original.replace(old_buf, HELPERS + new_buf, 1).replace(old_tx, new_tx, 1)
    out.mkdir(parents=True, exist_ok=False)
    (out / "switch_tqe.c").write_bytes(candidate.encode())
    result = {
        "status": "SOURCE_ONLY_PROTOTYPE_NO_GO_MODULE", "hardware_accessed": False,
        "original_module_sha256": sha(MODULE), "source_sha256": sha(SOURCE),
        "candidate_sha256": sha(out / "switch_tqe.c"), "rea_sha256": sha(REA),
        "module_provenance": "Exact F365 module pinned; matching critical source/assembly path only. Full baseline reconstruction UNPROVEN.",
        "change": "Bound TQE READY admission before skb/HBM mutation; retain legacy success/NO_HBM ownership; one semaphore primitive attempt, reject preowned LHOST.",
        "ready_read_bound": 1024, "semaphore_attempt_call_bound": 1,
        "semaphore_internal_attempt_bound": 65535,
        "limitations": ["Local IRQ exclusion is not a universal CPUIF lock; audit all other writers and SMP before module promotion.",
                        "HBM allocator/filter and MMIO hardware accesses may still block; no physical latency bound.",
                        "No automatic reset, recovery, queue retry or throughput improvement proved.",
                        "qdrv intentionally frees BUSY skb and returns NET_XMIT_SUCCESS; this prototype preserves that policy."]}
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create(args.out), indent=2))
