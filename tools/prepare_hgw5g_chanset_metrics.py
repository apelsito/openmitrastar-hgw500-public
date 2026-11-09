"""Reconstruct caller-owned channel-set metric ranking from retained OEM code.

No MAC/SSID/client data is accepted or exported. Caller must prepare validated
channel eligibility, power cost and bounded neighboring channel observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

DECL=r'''
struct om_chanset_observation {
    unsigned channel, bandwidth, secondary_offset;
    int rssi_dbm;
};
struct om_chanset_channel_state {
    unsigned allowed, inactive, dfs;
    om_cs_u32 power_range_cost;
};
int om_chanset_rank(struct om_chanset_transaction *transaction,
                    const struct om_chanset_channel_state *channels,
                    unsigned channel_count,
                    const struct om_chanset_observation *neighbors,
                    unsigned neighbor_count, unsigned neighborhood);
'''

CODE=r'''
/* Recovered two-row proximity policy at OEM0x85f74: min RSSI, span, weight.
 * The weakest neighbor keeps the previous row, as in the recovered loop.
 * These constants are ranking policy, never regulatory transmit permission. */
static int om_cs_neighbor_record(const struct om_chanset_observation *neighbor,
                                 struct om_chanset_entry *record)
{
    struct om_chanset_view view;
    const struct om_chanset_entry *found;
    enum om_chanset_band band=neighbor->channel<36?OM_CHANSET_BAND24:OM_CHANSET_BAND5;
    if(om_chanset_template(band,neighbor->bandwidth,&view))return -22;
    if(om_chanset_find(&view,neighbor->channel,neighbor->bandwidth,
                       neighbor->secondary_offset,&found)!=1)return -2;
    *record=*found;return 0;
}
int om_chanset_rank(struct om_chanset_transaction *transaction,
                    const struct om_chanset_channel_state *channels,
                    unsigned channel_count,
                    const struct om_chanset_observation *neighbors,
                    unsigned neighbor_count, unsigned neighborhood)
{
    static const int rssi_threshold[2]={-30,-62};
    static const unsigned span[2]={80,20},weight[2]={5,1};
    unsigned i,j,k,proximity=1;
    int low,high;
    struct om_chanset_entry neighbor;
    if(!transaction||!channels||channel_count!=transaction->count||channel_count>98||
       !transaction->busy||!transaction->active||neighbor_count>255||
       (neighbor_count&&!neighbors))return -22;
    /* Validate all potentially failing conversions before any metric update. */
    for(i=0;i<channel_count;i++)
        if(om_chanset_edges(&transaction->entries[i],transaction->band,neighborhood,
                            transaction->params.dense_cci_span,&low,&high))return -22;
    for(i=0;i<neighbor_count;i++) {
        if(om_cs_neighbor_record(&neighbors[i],&neighbor))return -22;
        if(om_chanset_edges(&neighbor,transaction->band,neighborhood,
                            transaction->params.dense_cci_span,&low,&high))return -22;
        if(neighbors[i].rssi_dbm < -128||neighbors[i].rssi_dbm>127)return -22;
    }
    for(i=0;i<channel_count;i++) {
        struct om_chanset_entry *entry=&transaction->entries[i];
        entry->invalid=!channels[i].allowed;
        entry->inactive=!!channels[i].inactive;
        entry->dfs=!!channels[i].dfs;
        entry->range_cost=channels[i].power_range_cost;
        entry->cci_instant=entry->scan_cca;
        entry->aci_instant=entry->cci_longterm=entry->aci_longterm=0;
        (void)om_chanset_edges(entry,transaction->band,neighborhood,
                               transaction->params.dense_cci_span,&low,&high);
        for(j=0;j<channel_count;j++) {
            const struct om_chanset_entry *other=&transaction->entries[j];
            int other_low,other_high;
            (void)om_chanset_edges(other,transaction->band,neighborhood,
                                  transaction->params.dense_cci_span,&other_low,&other_high);
            /* Exact two half-open overlap bands, using signed wide math to
             * keep subtraction/addition defined at domain boundaries. */
            for(k=0;k<2;k++) {
                if((long long)low-(long long)span[k]<other_high&&other_high<=low)
                    entry->aci_instant+=other->primary_cca[k];
                if(other_low<(long long)high+(long long)span[k]&&high<=other_low)
                    entry->aci_instant+=other->primary_cca[k];
            }
        }
    }
    for(j=0;j<neighbor_count;j++) {
        int neighbor_low,neighbor_high;
        (void)om_cs_neighbor_record(&neighbors[j],&neighbor);
        (void)om_chanset_edges(&neighbor,transaction->band,neighborhood,
                               transaction->params.dense_cci_span,&neighbor_low,&neighbor_high);
        if(neighbors[j].rssi_dbm>=rssi_threshold[0])proximity=0;
        else if(neighbors[j].rssi_dbm>=rssi_threshold[1])proximity=1;
        for(i=0;i<channel_count;i++) {
            struct om_chanset_entry *entry=&transaction->entries[i];
            (void)om_chanset_edges(entry,transaction->band,neighborhood,
                                   transaction->params.dense_cci_span,&low,&high);
            if(neighbors[j].rssi_dbm>transaction->params.min_cochannel_rssi&&
               low<neighbor_high&&neighbor_low<high)entry->cci_longterm++;
            if(((long long)low-(long long)span[proximity]<neighbor_high&&neighbor_high<=low)||
               (neighbor_low<(long long)high+(long long)span[proximity]&&high<=neighbor_low))
                entry->aci_longterm+=weight[proximity];
        }
    }
    for(i=0;i<channel_count;i++)
        (void)om_chanset_cost(&transaction->entries[i],&transaction->params,
                              &transaction->entries[i].cost);
    return 0;
}
'''


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--parent",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    assert json.loads((a.parent/"result.json").read_text())["status"]=="SOURCE_ONLY461_CALLER_OWNED_SCAN_TRANSACTION_NO_KERNEL_ADAPTER"
    a.output.mkdir(parents=True)
    for x in a.parent.iterdir():
        if x.is_file():shutil.copyfile(x,a.output/x.name)
    h=a.output/"openmitrastar_chanset_recovered.h";old=h.read_text();h.write_text(old[:-7]+DECL+"#endif\n",encoding="utf-8",newline="\n")
    c=a.output/"openmitrastar_chanset_recovered.c";c.write_text(c.read_text()+CODE,encoding="utf-8",newline="\n")
    result=dict(status="SOURCE_ONLY461_CALLER_OWNED_RANK_TRANSACTION_PENDING_FIXTURE_ADAPTER",hardware_accessed=False,firmware_eligible=False,
                inputs={str(a.parent/"result.json"):sha(a.parent/"result.json"),str(Path(__file__).resolve()):sha(Path(__file__))},
                source_hashes={x.name:sha(x)for x in a.output.iterdir()if x.name!="result.json"},
                limits=["No driver registration or kernel callbacks/scan locks/lifetime integration.",
                        "Caller supplies eligibility/DFS/power range state from validated channels.",
                        "Neighbor observations bounded255 and contain no MAC/SSID/identity.",
                        "Ranking still needs independent assembly/reference/ABI/full module proof."])
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(result["status"])


if __name__=="__main__":main()
