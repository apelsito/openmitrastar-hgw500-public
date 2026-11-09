"""SOURCE-only UP LHOST publication serialization across all four TQE writers.

This changes no timeout/drop/refcount policy. Existing waits remain unbounded.
Linux UP/PREEMPT_NONE and non-PCIe baseline are the only admitted configuration.
It does not establish arbitration against firmware writing the LHOST bank.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import struct

from prepare_tqe_bounded_admission_prototype import function
from qualify_f370_qdrv_module import Elf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c"
MODULE = ROOT / "outputs/rea/arc700-20261021-r2/tqe-current/switch_tqe.ko"
CONFIG = Path("/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/kernel/.config")
SOURCE_SHA = "929d89801045c2b5f421d4d40ca312c32feaf93612de6a575b9b362ab97d9aef"
MODULE_SHA = "bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f"

HELPER = r'''/* SOURCE-ONLY: serializes the compiled UP Linux LHOST bank writers.
 * READY check and descriptor publication belong to one local IRQ interval.
 * Congestion xmit additionally owns completion/status until return.
 * Existing unbounded wait/ownership/drop semantics deliberately remain.
 * Firmware cross-bank writes and HBM latency remain unqualified.
 */
#if defined(CONFIG_SMP) || defined(CONFIG_PREEMPT) || defined(CONFIG_PREEMPT_VOLUNTARY) || defined(CONFIG_TOPAZ_PCIE_TARGET)
#error "SOURCE-only LHOST serialization requires exact UP/PREEMPT_NONE/non-PCIe baseline"
#endif
static unsigned long omtqe_lhost_publish(const union topaz_tqe_cpuif_ppctl *ppctl)
{
	unsigned long flags;
	local_irq_save(flags);
	topaz_tqe_wait();
	topaz_tqe_cpuif_tx_start(ppctl);
	return flags;
}

static void omtqe_lhost_publish_end(unsigned long flags)
{
	local_irq_restore(flags);
}

'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sha(SOURCE) == SOURCE_SHA and sha(MODULE) == MODULE_SHA
    config = CONFIG.read_text()
    assert "CONFIG_PREEMPT_NONE=y" in config and "# CONFIG_SMP is not set" in config
    assert "CONFIG_TOPAZ_PCIE_TARGET=y" not in config and "CONFIG_TOPAZ_PCIE_TARGET=m" not in config
    baseline = SOURCE.read_text()
    candidate = baseline
    old = function(baseline, "int topaz_tqe_xmit(")
    new = old.replace("\tint num = topaz_tqe_cpuif_port_to_num(TOPAZ_TQE_LOCAL_CPU);", "\tint num = topaz_tqe_cpuif_port_to_num(TOPAZ_TQE_LOCAL_CPU);\n\tunsigned long flags;\n\tint result;", 1)
    new = new.replace('\ttopaz_tqe_wait();\n\tswitch_tqe_multi_proc_sem_down("topaz_tqe_xmit",__LINE__);\n\ttopaz_tqe_cpuif_tx_start(pp_cntl);\n\tswitch_tqe_multi_proc_sem_up();', '\tflags = omtqe_lhost_publish(pp_cntl);', 1)
    new = new.replace("\t\treturn NET_XMIT_CN;\n\telse\n\t\treturn NET_XMIT_SUCCESS;", "\t\tresult = NET_XMIT_CN;\n\telse\n\t\tresult = NET_XMIT_SUCCESS;\n\tomtqe_lhost_publish_end(flags);\n\treturn result;", 1)
    assert new != old and new.count("omtqe_lhost_publish_end(flags)") == 1
    candidate = candidate.replace(old, HELPER + new, 1)
    replacements = {}
    for signature, old_block, new_block in (
        ("static void __sram_text tqe_push_mcast(", '\t\ttopaz_tqe_wait();\n\t\tswitch_tqe_multi_proc_sem_down("tqe_push_mcast",__LINE__);\n\t\ttopaz_tqe_cpuif_tx_start(&ppctl);\n\t\tswitch_tqe_multi_proc_sem_up();', '\t\tunsigned long flags = omtqe_lhost_publish(&ppctl);\n\t\tomtqe_lhost_publish_end(flags);'),
        ("static int topaz_swfwd_tqe_xmit(", '\t\twhile (topaz_tqe_cpuif_tx_nready());\n\t\tswitch_tqe_multi_proc_sem_down("topaz_swfwd_tqe_xmit",__LINE__);\n\t\ttopaz_tqe_cpuif_tx_start(&ctl);\n\t\tswitch_tqe_multi_proc_sem_up();', '\t\tunsigned long flags = omtqe_lhost_publish(&ctl);\n\t\tomtqe_lhost_publish_end(flags);'),
        ("static int tqe_tx_buf(", '\twhile (topaz_tqe_cpuif_tx_nready());\n\t\n\tswitch_tqe_multi_proc_sem_down("tqe_tx_buf",__LINE__);\n\ttopaz_tqe_cpuif_tx_start(ppctl);\n\tswitch_tqe_multi_proc_sem_up();', '\t{\n\t\tunsigned long flags = omtqe_lhost_publish(ppctl);\n\t\tomtqe_lhost_publish_end(flags);\n\t}'),
    ):
        before = function(candidate, signature)
        assert before.count(old_block) == 1, signature
        after = before.replace(old_block, new_block, 1)
        candidate = candidate.replace(before, after, 1)
        replacements[signature] = {"before_sha256": hashlib.sha256(before.encode()).hexdigest(), "after_sha256": hashlib.sha256(after.encode()).hexdigest()}
    # Every original direct publication moves through the one admitted helper.
    assert baseline.count("topaz_tqe_cpuif_tx_start(") == 4
    assert candidate.count("topaz_tqe_cpuif_tx_start(") == 1
    assert candidate.count("omtqe_lhost_publish(") == 5
    assert candidate.count("omtqe_lhost_publish_end(") == 5
    assert function(baseline, "int tqe_tx(") == function(candidate, "int tqe_tx("), "skb/HBM ownership changed"
    elf = Elf(MODULE)
    bank = bytes.fromhex("03e13840")
    hits = []
    code = elf.byname[".text"]["data"]
    for cursor in range(len(code) - len(bank) + 1):
        if code[cursor:cursor + len(bank)] == bank:
            owners = [s["name"] for s in elf.syms if s["type"] == 2 and elf.symsection(s) == ".text" and s["value"] <= cursor < s["value"] + s["size"]]
            hits.append({"offset": cursor, "owning_functions": owners})
    assert {name for row in hits for name in row["owning_functions"]} == {"topaz_tqe_xmit", "tqe_tx", "tqe_push_mcast", "tqe_rx_napi_handler"}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "switch_tqe.c").write_text(candidate, newline="\n")
    patch = "".join(difflib.unified_diff(baseline.splitlines(True), candidate.splitlines(True), fromfile="a/src/platform/topaz/switch_tqe.c", tofile="b/src/platform/topaz/switch_tqe.c"))
    (args.output / "lhost-writer-serialization.patch").write_text(patch)
    result = {"schema": "openmitrastar.tqe-lhost-writer-serialization/v1", "status": "SOURCE_ONLY_LHOST_PUBLICATION_NO_GO_MODULE",
              "hardware_accessed": False, "firmware_eligible": False, "source_sha256": SOURCE_SHA,
              "parent_module_sha256": MODULE_SHA, "candidate_sha256": sha(args.output / "switch_tqe.c"),
              "configuration": "Exact UP/PREEMPT_NONE/non-PCIe compile guards", "config_sha256": sha(CONFIG),
              "direct_source_writers": 4, "single_candidate_publication_site": 1, "binary_bank0_anchors": hits,
              "source_function_deltas": replacements, "skb_hbm_ownership_function_unchanged": True,
              "banks": {"LHOST": {"port": 4, "bank": 0, "TXSTART": "0xe1034038"}, "MUC": {"port": 5, "bank": 1, "TXSTART": "0xe1035038"}, "AUC": {"port": 7, "bank": 3, "TXSTART": "0xe1037038"}},
              "limits": ["Existing READY/HBM/MMIO waits remain unbounded; IRQ starvation remains possible.",
                         "No universal arbitration claim: firmware writing LHOST bank outside the source contract remains a counterexample.",
                         "The congest-queue completion/status IRQ interval is longer; no physical latency or throughput improvement proven.",
                         "All refcounts, skb consumption and queue/drop returns remain original; no BUSY backpressure fix.",
                         "Complete candidate module rebuild/code delta and physical gates UNRUN."]}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
