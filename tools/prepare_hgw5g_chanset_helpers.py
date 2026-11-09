"""Extend recovered461 tables with measured scan queue, edges and cost helpers.

New isolated source, no driver registration, no RF or regulatory mutation.
Preserve OEM constants and loop arithmetic; invalid inputs refuse atomically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

DECL = r'''
typedef struct { om_cs_u32 cells[7], current_bandwidth; } om_chanset_scan_queue;
struct om_chanset_rank_params {
    om_cs_u32 cci_instant_factor, aci_instant_factor;
    om_cs_u32 cci_longterm_factor, aci_longterm_factor;
    om_cs_u32 range_factor, dfs_factor;
    int min_cochannel_rssi;
    om_cs_u32 max_bandwidth_benefit, dense_cci_span;
};
int om_chanset_add_scan_type(om_chanset_scan_queue *queue,
                            enum om_chanset_band band, unsigned bandwidth);
int om_chanset_rank_defaults(enum om_chanset_band band, int alternate,
                             struct om_chanset_rank_params *output);
int om_chanset_edges(const struct om_chanset_entry *entry,
                     enum om_chanset_band band, unsigned neighborhood,
                     unsigned dense_span, int *low, int *high);
int om_chanset_cost(const struct om_chanset_entry *entry,
                    const struct om_chanset_rank_params *params,
                    om_cs_u32 *output);
'''

HELPERS = r'''
/* Recovered OEM 0x131a8: queue7, BW40 band24 uses ABOVE3/BELOW4.
 * OEM full queue restarts at0; this helper refuses instead of overwriting.
 * Invalid bandwidth leaves both queue and current_bandwidth unchanged.
 */
int om_chanset_add_scan_type(om_chanset_scan_queue *queue,
                            enum om_chanset_band band, unsigned bandwidth)
{
    unsigned index = 0, first, second = 0;
    if (!queue || (band != OM_CHANSET_BAND24 && band != OM_CHANSET_BAND5))
        return -22;
    if (bandwidth == 20) first = 1;
    else if (bandwidth == 40) {
        first = band == OM_CHANSET_BAND24 ? 3 : 2;
        if (band == OM_CHANSET_BAND24) second = 4;
    } else if (bandwidth == 80 && band == OM_CHANSET_BAND5) first = 5;
    else if (bandwidth == 160 && band == OM_CHANSET_BAND5) first = 6;
    else return -22;
    while (index < 7 && queue->cells[index]) index++;
    if (index == 7 || (second && index >= 6)) return -28;
    {
        unsigned tail;
        /* Require one populated prefix followed by unused zero slots. */
        for (tail=index;tail<7;tail++) if (queue->cells[tail]) return -22;
    }
    queue->cells[index] = first;
    if (second) queue->cells[index+1] = second;
    queue->current_bandwidth = bandwidth;
    return 0;
}

/* Exact nine-word defaults selected by OEM 0x13314. Channel-policy permissions
 * stay with the caller; constant template availability does not allow TX. */
int om_chanset_rank_defaults(enum om_chanset_band band, int alternate,
                             struct om_chanset_rank_params *output)
{
    struct om_chanset_rank_params value;
    if (!output) return -22;
    if (band == OM_CHANSET_BAND24) {
        value.cci_instant_factor=0; value.aci_instant_factor=0;
        value.cci_longterm_factor=100; value.aci_longterm_factor=0;
    } else if (band == OM_CHANSET_BAND5) {
        value.cci_instant_factor=alternate?100:10;
        value.aci_instant_factor=alternate?20:5;
        value.cci_longterm_factor=alternate?10:100;
        value.aci_longterm_factor=alternate?5:20;
    } else return -22;
    value.range_factor=10; value.dfs_factor=band==OM_CHANSET_BAND24?0:(om_cs_u32)-30;
    value.min_cochannel_rssi=-80; value.max_bandwidth_benefit=2;
    value.dense_cci_span=5; *output=value; return 0;
}

/* OEM helpers 0x13514/0x13598. Use signed 64-bit intermediates and refuse an
 * unrepresentable edge; the recovered static templates remain within bounds. */
int om_chanset_edges(const struct om_chanset_entry *entry,
                     enum om_chanset_band band, unsigned neighborhood,
                     unsigned dense_span, int *low, int *high)
{
    long long base, span, center, lo, hi;
    if (!entry || !low || !high ||
        (band != OM_CHANSET_BAND24 && band != OM_CHANSET_BAND5)) return -22;
    base=entry->primary<36?2407:(entry->primary<183?5000:4000);
    span=(band==OM_CHANSET_BAND24 && neighborhood==2)?dense_span:entry->bandwidth/2;
    center=(long long)entry->center*5+base;lo=center-span;hi=center+span;
    if (lo < (-2147483647LL-1) || lo>2147483647LL ||
        hi < (-2147483647LL-1) || hi>2147483647LL) return -34;
    *low=(int)lo;*high=(int)hi;return 0;
}

/* Exact 88-byte ARC hardware-loop body0x1488e..0x148e6. Ghidra omits this
 * non-procedure loop; original text bytes and ARC objdump supply the evidence.
 * ARC mpy/add/sub use low32 bits; preserve that wrap using unsigned arithmetic.
 * The final subtract is unconditional, even when entry->dfs is zero.
 */
int om_chanset_cost(const struct om_chanset_entry *entry,
                    const struct om_chanset_rank_params *params,
                    om_cs_u32 *output)
{
    om_cs_u32 cost;
    if (!entry || !params || !output) return -22;
    cost=entry->aci_instant*params->aci_instant_factor;
    cost+=entry->cci_instant*params->cci_instant_factor;
    cost+=entry->aci_longterm*params->aci_longterm_factor;
    cost+=entry->cci_longterm*params->cci_longterm_factor;
    cost+=entry->dfs*params->dfs_factor;
    cost+=entry->range_cost*params->range_factor;
    cost-=params->dfs_factor;
    *output=cost;return 0;
}
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    parent = json.loads((args.parent/"result.json").read_text())
    assert parent["status"] == "SOURCE_ONLY_EXACT130_OEM_CHANSET_ROWS_BOUNDED_LOOKUP"
    names = ["windows-oem-chanset-add-scan-type-20261022T165000Z-r1",
             "windows-oem-chanset-ranking-init-20261022T171500Z-r1",
             "windows-oem-chanset-edge-low-20261022T170000Z-r1",
             "windows-oem-chanset-edge-high-20261022T170000Z-r1"]
    evidence = []
    paths = [args.parent/"result.json"]
    for name in names:
        path = ROOT/"outputs/rea"/name/"rea.json"
        row = json.loads(path.read_text())["data"]
        assert row["subject"]["digest"]["sha256"] == "79fbcbd4634a9fc32fdf8ac0c997f3bd0329131162a1ea4948794e4986c7e40a"
        evidence.append(row["evidence_id"])
        paths.append(path)
    decode = ROOT/"outputs/rea/chanset461-cost-loop-with-register-context-20261022T170700Z-r2/result.json"
    assert json.loads(decode.read_text())["status"] == "PASS_EXACT_UNOWNED_ARC_COST_LOOP_DECODE"
    assert json.loads(decode.read_text())["register_setup_bound"]
    paths.append(decode)
    paths.extend([decode.parent/"assembly.txt", Path(__file__).resolve()])
    args.output.mkdir(parents=True)
    for name in ("openmitrastar_chanset_recovered.h", "openmitrastar_chanset_recovered.c", "openmitrastar_chanset_tables.h", "tables.json"):
        shutil.copyfile(args.parent/name, args.output/name)
        paths.append(args.parent/name)
    header = args.output/"openmitrastar_chanset_recovered.h"
    old = header.read_text()
    assert old.endswith("#endif\n")
    header.write_text(old[:-7]+DECL+"#endif\n", encoding="utf-8", newline="\n")
    source = args.output/"openmitrastar_chanset_recovered.c"
    source.write_text(source.read_text()+HELPERS, encoding="utf-8", newline="\n")
    result = dict(status="SOURCE_ONLY461_SCAN_QUEUE_EDGES_COST_HELPERS_NOT_DRIVER",
                  hardware_accessed=False, firmware_eligible=False, recovered_table_rows=130,
                  evidence_ids=evidence, inputs={str(p):sha(p) for p in paths},
                  source_hashes={p.name:sha(p) for p in args.output.iterdir()},
                  limits=["No461 table record registered; driver integration unrun.",
                          "Saturated scan queue and malformed arguments refuse without mutation.",
                          "Metric collection, final candidate choice and callbacks/lifetime remain open.",
                          "No regulatory allowlist or physical scan/RF claim."])
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(result["status"])


if __name__ == "__main__":
    main()
