"""Reconstruct bounded461 table/scan transaction state, no device operations.

Caller owns allocation and scan callbacks. Prepares only original templates;
regulatory and lifetime adapters remain mandatory before driver registration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

DECL=r'''
/* Per-radio transaction storage is caller-owned and bounded by original98
 * widest-band table records. It must not be allocated on a kernel stack. */
struct om_chanset_transaction {
    struct om_chanset_entry entries[98];
    om_chanset_scan_queue queue;
    struct om_chanset_rank_params params;
    unsigned count, generation, busy, active;
    enum om_chanset_band band;
};
int om_chanset_prepare(struct om_chanset_transaction *transaction,
                       enum om_chanset_band band, unsigned current_bandwidth,
                       int alternate_rank, int automatic_bandwidth);
int om_chanset_scan_request(const struct om_chanset_transaction *transaction,
                            unsigned initial_flags, unsigned *flags,
                            unsigned *secondary_offset);
int om_chanset_scan_advance(struct om_chanset_transaction *transaction);
int om_chanset_scan_sample(struct om_chanset_transaction *transaction,
                           unsigned channel, unsigned secondary_offset,
                           const struct om_chanset_scan_sample *input);
int om_chanset_end(struct om_chanset_transaction *transaction);
'''

SOURCE=r'''
int om_chanset_prepare(struct om_chanset_transaction *transaction,
                       enum om_chanset_band band, unsigned current_bandwidth,
                       int alternate_rank, int automatic_bandwidth)
{
    struct om_chanset_rank_params params;
    om_chanset_scan_queue queue={{0},0};
    struct om_chanset_view templates[4];
    unsigned width=current_bandwidth, groups=0, count=0, group, i;
    if(!transaction||transaction->busy||transaction->generation==~0U||
       (current_bandwidth!=20&&current_bandwidth!=40&&current_bandwidth!=80&&current_bandwidth!=160))return -22;
    if(om_chanset_rank_defaults(band,alternate_rank,&params))return -22;
    /* Validate the entire plan before changing transaction fields. */
    while(width>=20) {
        if(om_chanset_template(band,width,&templates[groups]))return -22;
        count+=templates[groups].count;
        if(count>98)return -28;
        groups++;width/=2;
    }
    width=(params.cci_instant_factor||params.aci_instant_factor)?current_bandwidth:20;
    if(om_chanset_add_scan_type(&queue,band,width))return -22;
    if(automatic_bandwidth&&width>20&&om_chanset_add_scan_type(&queue,band,width/2))return -22;
    /* Caller must serialize this state and keep its owning radio alive. */
    transaction->generation++;
    transaction->busy=1;
    transaction->active=1;
    transaction->band=band;
    transaction->params=params;
    transaction->queue=queue;
    transaction->count=count;
    count=0;
    for(group=0;group<groups;group++)for(i=0;i<templates[group].count;i++)
        transaction->entries[count++]=templates[group].entries[i];
    return 0;
}
int om_chanset_scan_request(const struct om_chanset_transaction *transaction,
                            unsigned initial_flags, unsigned *flags,
                            unsigned *secondary_offset)
{
    unsigned value, offset=0, selected;
    if(!transaction||!flags||!secondary_offset||flags==secondary_offset||
       !transaction->busy||!transaction->active)return -22;
    selected=transaction->queue.cells[0];value=initial_flags;
    if(selected<1||selected>6)return -22;
    if(selected>=2&&selected<=4)value|=0x100000U;
    else if(selected==5)value|=0x200000U;
    if(selected==3)offset=1;
    else if(selected==4)offset=3;
    /* OEM scan0x1361c: requests are returned to the caller. No scan is started
     * until a validated kernel/regulatory/lifetime adapter consumes them. */
    *flags=value;*secondary_offset=offset;return 0;
}
int om_chanset_scan_advance(struct om_chanset_transaction *transaction)
{
    unsigned i;
    if(!transaction||!transaction->busy||!transaction->active)return -22;
    for(i=0;i<6;i++)transaction->queue.cells[i]=transaction->queue.cells[i+1];
    transaction->queue.cells[6]=0;
    return transaction->queue.cells[0]?1:0;
}
int om_chanset_scan_sample(struct om_chanset_transaction *transaction,
                           unsigned channel, unsigned secondary_offset,
                           const struct om_chanset_scan_sample *input)
{
    struct om_chanset_scan_sample sample;
    struct om_chanset_view view;
    const struct om_chanset_entry *found;
    unsigned index;
    int result;
    if(!transaction||!input||!transaction->busy||!transaction->active||
       transaction->count>98||channel>=255)return -22;
    result=om_chanset_normalize_sample(input,&sample);
    if(result)return result;
    view.entries=transaction->entries;view.count=transaction->count;view.capacity=98;
    result=om_chanset_find(&view,channel,sample.bandwidth,secondary_offset,&found);
    if(result!=1)return result<0?result:-2;
    index=(unsigned)(found-transaction->entries);
    return om_chanset_update_scan_entry(&transaction->entries[index],&sample);
}
int om_chanset_end(struct om_chanset_transaction *transaction)
{
    if(!transaction||!transaction->busy)return -22;
    /* Does not release memory or buffers used by actual scan callbacks. The
     * kernel adapter must quiesce those callbacks before ending ownership. */
    transaction->active=0;transaction->busy=0;transaction->count=0;
    return 0;
}
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--parent",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    parent=json.loads((a.parent/"result.json").read_text());assert parent["status"]=="SOURCE_ONLY461_SCALED_SCAN_FINAL_CHOICE_ADAPTERS_NO_REGISTRATION"
    a.output.mkdir(parents=True)
    for f in a.parent.iterdir():
        if f.is_file():shutil.copyfile(f,a.output/f.name)
    header=a.output/"openmitrastar_chanset_recovered.h";text=header.read_text();assert text.endswith("#endif\n");header.write_text(text[:-7]+DECL+"#endif\n",encoding="utf-8",newline="\n")
    source=a.output/"openmitrastar_chanset_recovered.c";source.write_text(source.read_text()+SOURCE,encoding="utf-8",newline="\n")
    result=dict(status="SOURCE_ONLY461_CALLER_OWNED_SCAN_TRANSACTION_NO_KERNEL_ADAPTER",hardware_accessed=False,firmware_eligible=False,
                inputs={str(a.parent/"result.json"):sha(a.parent/"result.json"),str(Path(__file__).resolve()):sha(Path(__file__))},
                source_hashes={f.name:sha(f)for f in a.output.iterdir()if f.name!="result.json"},
                limits=["Caller-owned serialized memory; not a kernel module or stack allocation.",
                        "Callbacks/allowed channels/scan token cancellation require a real kernel adapter.",
                        "Table preparation/sample collection only; neighbor metrics/cost updates/finalchoice integration pending.",
                        "No461 WEXT records, RF/DFS, traffic or release acceptance."])
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(result["status"])


if __name__=="__main__":main()
