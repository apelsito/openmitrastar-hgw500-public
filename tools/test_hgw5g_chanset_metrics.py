"""Exercise real461 ranking on caller-owned templates and bounded observations.

Checks semantic counterexamples, overlap policy, refusal atomicity and signed
cost wrapping. No real scan, channel/regulatory mutation or neighbor identity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

FIXTURE=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "openmitrastar_chanset_recovered.h"
static struct om_chanset_transaction tx,old;
static struct om_chanset_channel_state channels[98];
static const unsigned widths[]={20,40,80,160};
static uint32_t rng=0x651a23b7;
static uint32_t random32(void){rng=rng*1664525U+1013904223U;return rng;}
int main(void){
    unsigned band,width,i,j,cases=0;
    struct om_chanset_observation observation={36,20,0,-20};
    const struct om_chanset_entry *selected;
    struct om_chanset_view view;
    for(band=0;band<2;band++)for(width=0;width<4;width++){
        memset(&tx,0,sizeof(tx));
        if(om_chanset_prepare(&tx,band,widths[width],0,0))continue;
        for(i=0;i<tx.count;i++){
            memset(&channels[i],0,sizeof(channels[i]));channels[i].allowed=1;
            tx.entries[i].scan_cca=3;
        }
        assert(om_chanset_rank(&tx,channels,tx.count,0,0,0)==0);
        for(i=0;i<tx.count;i++){
            uint32_t expected=3U*tx.params.cci_instant_factor-tx.params.dfs_factor;
            assert(tx.entries[i].cci_instant==3&&tx.entries[i].aci_instant==0&&tx.entries[i].cci_longterm==0&&tx.entries[i].aci_longterm==0&&tx.entries[i].cost==expected);
        }
        view.entries=tx.entries;view.count=tx.count;view.capacity=98;
        assert(om_chanset_select(&view,band,widths[width],20,0,2,&selected)==1);
        assert(selected->bandwidth==widths[width]);cases++;
        assert(om_chanset_end(&tx)==0);
    }
    memset(&tx,0,sizeof(tx));assert(om_chanset_prepare(&tx,1,20,0,0)==0);
    for(i=0;i<tx.count;i++){memset(&channels[i],0,sizeof(channels[i]));channels[i].allowed=1;tx.entries[i].scan_cca=0;}
    assert(om_chanset_rank(&tx,channels,tx.count,&observation,1,0)==0);
    assert(tx.entries[0].primary==36&&tx.entries[0].cci_longterm==1&&tx.entries[0].aci_longterm==0&&tx.entries[0].cost==130);
    /* Channel40 loweredge5190 touches the upperedge of neighbor36: near-band
     * comparison includes equality only on one side, adding one weight5. */
    assert(tx.entries[1].primary==40&&tx.entries[1].cci_longterm==0&&tx.entries[1].aci_longterm==5&&tx.entries[1].cost==130);
    observation.rssi_dbm=-80;
    assert(om_chanset_rank(&tx,channels,tx.count,&observation,1,0)==0);
    assert(tx.entries[0].cci_longterm==0);
    channels[0].allowed=0;channels[1].inactive=1;
    assert(om_chanset_rank(&tx,channels,tx.count,0,0,0)==0);
    assert(tx.entries[0].invalid==1&&tx.entries[1].inactive==1);
    old=tx;observation.channel=255;
    assert(om_chanset_rank(&tx,channels,tx.count,&observation,1,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    observation.channel=36;observation.rssi_dbm=-129;
    assert(om_chanset_rank(&tx,channels,tx.count,&observation,1,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    assert(om_chanset_rank(&tx,channels,tx.count+1,0,0,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    assert(om_chanset_rank(&tx,channels,tx.count,0,1,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    for(j=0;j<1000;j++){
        memset(&tx,0,sizeof(tx));assert(om_chanset_prepare(&tx,1,80,0,1)==0);
        for(i=0;i<tx.count;i++){
            memset(&channels[i],0,sizeof(channels[i]));channels[i].allowed=1;
            channels[i].dfs=i&1;channels[i].power_range_cost=random32();
            tx.entries[i].scan_cca=random32();
        }
        assert(om_chanset_rank(&tx,channels,tx.count,0,0,0)==0);
        for(i=0;i<tx.count;i++){
            uint32_t expected=tx.entries[i].scan_cca*tx.params.cci_instant_factor;
            expected+=channels[i].power_range_cost*tx.params.range_factor;
            expected+=channels[i].dfs*tx.params.dfs_factor;
            expected-=tx.params.dfs_factor;
            assert(tx.entries[i].cost==expected);
        }
    }
    printf("{\"table_plan_cases\":%u,\"random_cost_tables\":1000,\"overlap_tie_RSSI_counterexamples\":true,\"refusal_atomicity_cases\":4}\n",cases);return 0;
}
'''


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--candidate",type=Path,required=True);p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    pins={str(x):sha(x)for x in a.candidate.iterdir()if x.is_file()};pins[str(Path(__file__).resolve())]=sha(Path(__file__));pins[str(a.compiler)]=sha(a.compiler)
    a.output.mkdir(parents=True);(a.output/"input-pins.json").write_text(json.dumps(pins,indent=2)+"\n");f=a.output/"fixture.c";f.write_text(FIXTURE,encoding="utf-8")
    cmd=[str(a.compiler),"-std=c11","-O1","-I"+str(a.candidate.resolve()),str(f),str(a.candidate/"openmitrastar_chanset_recovered.c"),"-o",str(a.output/"fixture.exe")]
    (a.output/"compile.command.json").write_text(json.dumps(cmd,indent=2)+"\n");r=subprocess.run(cmd,capture_output=True,timeout=60);(a.output/"compile.stderr").write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors="replace")
    r=subprocess.run([str(a.output/"fixture.exe")],capture_output=True,timeout=60);(a.output/"fixture.stdout").write_bytes(r.stdout);(a.output/"fixture.stderr").write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors="replace");observed=json.loads(r.stdout)
    assert observed["table_plan_cases"]==6
    for x,h in pins.items():assert sha(Path(x))==h
    result=dict(status="PASS_HOST461_CALLER_OWNED_CHANNEL_RANKING_SOURCE",hardware_accessed=False,firmware_eligible=False,inputs_unchanged=True,**observed,limits="No kernel callback/scan/policy/lifetime/driver registration or RF acceptance")
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))


if __name__=="__main__":main()
