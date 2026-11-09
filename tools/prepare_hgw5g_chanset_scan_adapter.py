"""Add pure scaled-scan and final-choice adapters to the partial461 sources.

Exact thirteen-word v89 payload, no shared pointer or real scan access. Pure
selection consumes caller-owned records and does not change channel or radio.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

DECL=r'''
struct om_chanset_scan_sample {
    om_cs_u32 bandwidth, cca_idle, cca_busy, cca_tx, cca_interference, attempts;
    om_cs_u32 cca_primary, cca_secondary, cca_secondary40;
    om_cs_u32 beacons, crc_errors, long_preamble_errors, short_preamble_errors;
};
int om_chanset_normalize_sample(const struct om_chanset_scan_sample *input,
                                struct om_chanset_scan_sample *output);
int om_chanset_update_scan_entry(struct om_chanset_entry *entry,
                                const struct om_chanset_scan_sample *scaled);
int om_chanset_select(const struct om_chanset_view *view,
                      enum om_chanset_band band, unsigned maximum_bandwidth,
                      unsigned current_scan_bandwidth, int automatic_bandwidth,
                      unsigned minimum_benefit,
                      const struct om_chanset_entry **output);
'''

SOURCE=r'''
typedef char om_cs_scan_size_is_52[(sizeof(struct om_chanset_scan_sample)==52)?1:-1];
static om_cs_u32 om_cs_scale(om_cs_u32 value, om_cs_u32 denominator)
{
    /* Exact OEM threshold0x418937: preserve divide-first truncation above it. */
    return value<0x418937U?(value*1000U)/denominator:(value/denominator)*1000U;
}
int om_chanset_normalize_sample(const struct om_chanset_scan_sample *input,
                                struct om_chanset_scan_sample *output)
{
    struct om_chanset_scan_sample value;
    if(!input||!output||!input->attempts)return -11;
    value=*input;
    value.cca_idle=om_cs_scale(input->cca_idle,input->attempts);
    value.cca_busy=om_cs_scale(input->cca_busy,input->attempts);
    value.cca_tx=om_cs_scale(input->cca_tx,input->attempts);
    value.cca_interference=om_cs_scale(input->cca_interference,input->attempts);
    value.cca_primary=om_cs_scale(input->cca_primary,input->attempts);
    value.cca_secondary=om_cs_scale(input->cca_secondary,input->attempts);
    value.cca_secondary40=om_cs_scale(input->cca_secondary40,input->attempts);
    value.beacons=om_cs_scale(input->beacons,input->attempts);
    value.crc_errors=om_cs_scale(input->crc_errors,input->attempts);
    value.long_preamble_errors=om_cs_scale(input->long_preamble_errors,input->attempts);
    value.short_preamble_errors=om_cs_scale(input->short_preamble_errors,input->attempts);
    value.attempts=1000;*output=value;return 0;
}
int om_chanset_update_scan_entry(struct om_chanset_entry *entry,
                                const struct om_chanset_scan_sample *scaled)
{
    if(!entry||!scaled||scaled->attempts!=1000)return -22;
    entry->scan_cca=scaled->cca_interference;
    entry->cca[0]=scaled->cca_primary;
    entry->cca[1]=scaled->cca_secondary;
    entry->cca[2]=scaled->cca_secondary40;
    entry->primary_cca[0]=0;
    entry->cca[3]=scaled->cca_primary;
    return 0;
}
static int om_cs_signed_less(om_cs_u32 first, om_cs_u32 second)
{
    /* Order by the ARC signed branch without implementation-defined casts. */
    return (first^0x80000000U)<(second^0x80000000U);
}
static int om_cs_signed_le(om_cs_u32 first, om_cs_u32 second)
{
    return (first^0x80000000U)<=(second^0x80000000U);
}
int om_chanset_select(const struct om_chanset_view *view,
                      enum om_chanset_band band, unsigned maximum_bandwidth,
                      unsigned current_scan_bandwidth, int automatic_bandwidth,
                      unsigned minimum_benefit,
                      const struct om_chanset_entry **output)
{
    const struct om_chanset_entry *best[4]={0,0,0,0},*picked;
    unsigned i,index;
    if(!view||!output||!view->entries||view->count>view->capacity||view->capacity>98||
       (band!=OM_CHANSET_BAND24&&band!=OM_CHANSET_BAND5))return -22;
    for(i=0;i<view->count;i++) {
        const struct om_chanset_entry *entry=&view->entries[i];
        if(entry->bandwidth==20)index=0;
        else if(entry->bandwidth==40)index=1;
        else if(entry->bandwidth==80)index=2;
        else if(entry->bandwidth==160)index=3;
        else continue;
        if(entry->bandwidth>maximum_bandwidth||current_scan_bandwidth>entry->bandwidth||
           entry->invalid||entry->inactive)continue;
        if(!best[index]||om_cs_signed_less(entry->cost,best[index]->cost))best[index]=entry;
    }
    picked=best[3]?best[3]:(best[2]?best[2]:(best[1]?best[1]:best[0]));
    if(automatic_bandwidth) {
        if(band==OM_CHANSET_BAND24) {
            if(best[1]&&best[0]&&
               om_cs_signed_less(best[0]->cost*minimum_benefit,best[1]->cost))picked=best[0];
        } else if(best[3]&&best[2]) {
            picked=om_cs_signed_le(best[3]->cost,best[2]->cost*minimum_benefit)?best[3]:best[2];
        }
    }
    *output=picked;return picked?1:0;
}
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    proof=json.loads((args.parent/"result.json").read_text())
    assert proof["status"]=="SOURCE_ONLY461_SCAN_QUEUE_EDGES_COST_HELPERS_NOT_DRIVER"
    args.output.mkdir(parents=True)
    for p in args.parent.iterdir():
        if p.is_file():shutil.copyfile(p,args.output/p.name)
    header=args.output/"openmitrastar_chanset_recovered.h";text=header.read_text();assert text.endswith("#endif\n")
    header.write_text(text[:-7]+DECL+"#endif\n",encoding="utf-8",newline="\n")
    source=args.output/"openmitrastar_chanset_recovered.c";text=source.read_text()
    text=text.replace('while (index < 7 && queue->cells[index]) index++;','while (index < 7 && queue->cells[index]) {\n        if (queue->cells[index]>6U) return -22;\n        index++;\n    }',1)
    text=text.replace('if (!entry || !low || !high ||','if (!entry || !low || !high || low==high ||',1)
    source.write_text(text+SOURCE,encoding="utf-8",newline="\n")
    paths=[args.parent/"result.json",Path(__file__).resolve(),
           ROOT/"outputs/rea/windows-oem-chanset-scan-metrics-20261022T173500Z-r1/rea.json",
           ROOT/"outputs/rea/windows-oem-chanset-pick-20261022T165100Z-r1/rea.json"]
    for path in paths[2:]:
        obj=json.loads(path.read_text())["data"]
        assert obj["subject"]["digest"]["sha256"]=="79fbcbd4634a9fc32fdf8ac0c997f3bd0329131162a1ea4948794e4986c7e40a"
    result=dict(status="SOURCE_ONLY461_SCALED_SCAN_FINAL_CHOICE_ADAPTERS_NO_REGISTRATION",
                hardware_accessed=False,firmware_eligible=False,recovered_table_rows=130,
                inputs={str(p):sha(p)for p in paths},
                source_hashes={p.name:sha(p)for p in args.output.iterdir()if p.name!="result.json"},
                limits=["Shared-scan read, concurrency, F355 lifetime and real callbacks unconnected.",
                        "Pure selection consumes caller-owned candidates after metric/regulatory preparation.",
                        "No461 entry added, no runtime or RF/DFS acceptance.",
                        "No randomness callback here; normalization is pure math on a bounded local copy."])
    (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(result["status"])


if __name__=="__main__":main()
