"""Exercise real recovered461 helpers: queue atomicity, edge and wrap cost.

Checks malformed and saturated queues without overwrites, original constants,
signed edge refusal and ARC low32 arithmetic against a 64-bit reference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


FIXTURE = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "openmitrastar_chanset_recovered.h"
static uint32_t seed=0x71b923ef;
static uint32_t random32(void){seed=seed*1664525U+1013904223U;return seed;}
int main(void) {
    unsigned band,width,fill,casecount=0,i,n=0,expectedcode,index;
    const unsigned widths[]={0,20,21,40,80,160,161};
    om_chanset_scan_queue queue,old;
    struct om_chanset_rank_params params;
    struct om_chanset_entry entry={0};
    const int32_t expected_defaults[3][9]={{0,0,100,0,10,0,-80,2,5},
        {10,5,100,20,10,-30,-80,2,5},{100,20,10,5,10,-30,-80,2,5}};
    for(band=0;band<3;band++)for(width=0;width<7;width++)for(fill=0;fill<8;fill++) {
        int result; memset(&queue,0,sizeof(queue));queue.current_bandwidth=1234;
        for(i=0;i<fill;i++)queue.cells[i]=6;old=queue;
        index=fill;
        if(band>1 || widths[width]==0 || widths[width]==21 || widths[width]==161 ||
           (band==0 && widths[width]>40))expectedcode=22;
        else if(fill==7 || (band==0 && widths[width]==40 && fill>=6))expectedcode=28;
        else expectedcode=0;
        result=om_chanset_add_scan_type(&queue,band,widths[width]);
        assert(result==-(int)expectedcode);
        if(result)assert(memcmp(&queue,&old,sizeof(queue))==0);
        else {
            assert(queue.current_bandwidth==widths[width]);
            for(i=0;i<fill;i++)assert(queue.cells[i]==old.cells[i]);
            if(widths[width]==40 && band==0)assert(queue.cells[index]==3 && queue.cells[index+1]==4);
            else assert(queue.cells[index]==(widths[width]==20?1:widths[width]==40?2:widths[width]==80?5:6));
        }
        casecount++;
    }
    memset(&queue,0,sizeof(queue));queue.cells[1]=5;old=queue;
    assert(om_chanset_add_scan_type(&queue,1,20)==-22 && memcmp(&queue,&old,sizeof(queue))==0);
    assert(om_chanset_add_scan_type(0,1,20)==-22);
    for(i=0;i<3;i++) {
        const int32_t *words;
        assert(om_chanset_rank_defaults(i?1:0,i==2,&params)==0);
        words=(const int32_t*)&params;
        for(n=0;n<9;n++)assert(words[n]==expected_defaults[i][n]);
    }
    assert(om_chanset_rank_defaults(2,0,&params)==-22);
    for(i=0;i<100000;i++) {
        uint32_t expected,cost=0; uint64_t sum;
        entry.cci_instant=random32();entry.aci_instant=random32();
        entry.cci_longterm=random32();entry.aci_longterm=random32();
        entry.range_cost=random32();entry.dfs=random32();
        params.cci_instant_factor=random32();params.aci_instant_factor=random32();
        params.cci_longterm_factor=random32();params.aci_longterm_factor=random32();
        params.range_factor=random32();params.dfs_factor=random32();
        /* Reduce each term modulo32 before adding, so the reference cannot
         * overflow64 while still matching ARC low32 multiply/add behavior. */
        sum=(uint32_t)((uint64_t)entry.cci_instant*params.cci_instant_factor);
        sum+=(uint32_t)((uint64_t)entry.aci_instant*params.aci_instant_factor);
        sum+=(uint32_t)((uint64_t)entry.cci_longterm*params.cci_longterm_factor);
        sum+=(uint32_t)((uint64_t)entry.aci_longterm*params.aci_longterm_factor);
        sum+=(uint32_t)((uint64_t)entry.range_cost*params.range_factor);
        sum+=(uint32_t)((uint64_t)entry.dfs*params.dfs_factor);
        expected=(uint32_t)sum-params.dfs_factor;
        assert(om_chanset_cost(&entry,&params,&cost)==0 && cost==expected);
    }
    entry.cci_instant=entry.aci_instant=entry.cci_longterm=entry.aci_longterm=entry.range_cost=entry.dfs=0;
    params.dfs_factor=(uint32_t)-30;
    {uint32_t cost;assert(om_chanset_cost(&entry,&params,&cost)==0&&cost==30);}
    {uint32_t cost=123;assert(om_chanset_cost(0,&params,&cost)==-22&&cost==123);}
    n=0;
    for(i=0;i<2;i++)for(width=0;width<4;width++) {
        struct om_chanset_view view;
        const unsigned bws[]={20,40,80,160};
        if(om_chanset_template(i,bws[width],&view))continue;
        for(index=0;index<view.count;index++)for(band=0;band<2;band++)for(fill=0;fill<3;fill++) {
            int low,high;unsigned span;
            entry=view.entries[index];span=(band==0&&fill==2)?5:entry.bandwidth/2;
            expectedcode=entry.primary<36?2407:entry.primary<183?5000:4000;
            assert(om_chanset_edges(&entry,band,fill,5,&low,&high)==0);
            assert(low==(int)(entry.center*5+expectedcode)- (int)span);
            assert(high==(int)(entry.center*5+expectedcode)+(int)span);n++;
        }
    }
    {int low=123,high=456;entry.center=~0U;
     assert(om_chanset_edges(&entry,1,0,5,&low,&high)==-34 && low==123 && high==456);}
    printf("{\"queue_cases\":%u,\"random_cost_cases\":100000,\"edge_cases\":%u,\"exact_default_words\":27,\"malformed_queue_atomic\":true}\n",casecount,n);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    inputs = {str(p):sha(p) for p in args.candidate.iterdir() if p.is_file()}
    inputs.update({str(Path(__file__).resolve()):sha(Path(__file__)), str(args.compiler):sha(args.compiler)})
    args.output.mkdir(parents=True)
    (args.output/"input-pins.json").write_text(json.dumps(inputs, indent=2)+"\n")
    source = args.output/"fixture.c"
    source.write_text(FIXTURE, encoding="utf-8")
    command = [str(args.compiler), "-std=c11", "-O1", "-fno-strict-aliasing", "-I"+str(args.candidate.resolve()),
               str(source), str(args.candidate/"openmitrastar_chanset_recovered.c"), "-o", str(args.output/"fixture.exe")]
    (args.output/"compile.command.json").write_text(json.dumps(command, indent=2)+"\n")
    compile = subprocess.run(command, capture_output=True, timeout=60)
    (args.output/"compile.stderr").write_bytes(compile.stderr)
    assert compile.returncode == 0, compile.stderr.decode(errors="replace")
    run = subprocess.run([str(args.output/"fixture.exe")], capture_output=True, timeout=30)
    (args.output/"fixture.stdout").write_bytes(run.stdout)
    (args.output/"fixture.stderr").write_bytes(run.stderr)
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    observed = json.loads(run.stdout)
    assert observed["queue_cases"] == 168 and observed["edge_cases"] == 780
    for path, digest in inputs.items():
        assert sha(Path(path)) == digest, "input drift " + path
    result = dict(status="PASS_HOST_ACTUAL461_QUEUE_EDGES_WRAP_COST_HELPERS", hardware_accessed=False,
                  firmware_eligible=False, inputs_unchanged=True, **observed,
                  limits="No scan collection/final candidate choice/driver registration or RF acceptance")
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
