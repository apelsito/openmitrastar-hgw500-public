"""Execute actual461 transaction preparation/scan/sample/end source cases.

Caller-owned state only. Verify immutable refusal, all original record plans,
scan flags/secondary order and sample placement without real kernel callbacks.
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
int main(void){
    const unsigned widths[]={20,40,80,160};
    unsigned band,w,alt,automatic,cases=0,flags,sec,i,n;
    struct om_chanset_scan_sample sample;
    for(band=0;band<2;band++)for(w=0;w<4;w++)for(alt=0;alt<2;alt++)for(automatic=0;automatic<2;automatic++){
        int ret;memset(&tx,0,sizeof(tx));ret=om_chanset_prepare(&tx,band,widths[w],alt,automatic);
        if(band==0&&widths[w]>40){assert(ret==-22&&!tx.busy&&!tx.generation);continue;}
        assert(ret==0&&tx.busy&&tx.active&&tx.generation==1);
        assert(tx.count==(band==0?(widths[w]==20?14:32):(widths[w]==20?30:widths[w]==40?58:widths[w]==80?82:98)));
        assert(tx.params.cci_longterm_factor==(band==0?100:alt?10:100));
        old=tx;assert(om_chanset_prepare(&tx,band,widths[w],alt,automatic)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
        for(n=0;n<7 && tx.queue.cells[0];n++){
            unsigned kind=tx.queue.cells[0],f=0x8000000U,s=0;
            flags=123;sec=456;assert(om_chanset_scan_request(&tx,f,&flags,&sec)==0);
            if(kind>=2&&kind<=4)f|=0x100000U;else if(kind==5)f|=0x200000U;
            if(kind==3)s=1;else if(kind==4)s=3;
            assert(flags==f&&sec==s);
            assert(om_chanset_scan_advance(&tx)>=0);
        }
        assert(!tx.queue.cells[0]);flags=123;sec=456;
        assert(om_chanset_scan_request(&tx,0,&flags,&sec)==-22&&flags==123&&sec==456);
        memset(&sample,0,sizeof(sample));sample.bandwidth=tx.entries[0].bandwidth;
        sample.attempts=1000;sample.cca_interference=5;sample.cca_primary=6;sample.cca_secondary=7;sample.cca_secondary40=8;
        assert(om_chanset_scan_sample(&tx,tx.entries[0].primary,tx.entries[0].secondary_offset,&sample)==0);
        assert(tx.entries[0].scan_cca==5&&tx.entries[0].cca[0]==6&&tx.entries[0].cca[1]==7&&tx.entries[0].cca[2]==8);
        old=tx;sample.attempts=0;
        assert(om_chanset_scan_sample(&tx,tx.entries[0].primary,tx.entries[0].secondary_offset,&sample)==-11&&memcmp(&tx,&old,sizeof(tx))==0);
        assert(om_chanset_scan_sample(&tx,255,0,&sample)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
        assert(om_chanset_end(&tx)==0&&!tx.busy&&!tx.active&&!tx.count&&tx.generation==1);
        assert(om_chanset_end(&tx)==-22);cases++;
    }
    memset(&tx,0,sizeof(tx));tx.generation=~0U;old=tx;
    assert(om_chanset_prepare(&tx,1,80,0,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    memset(&tx,0,sizeof(tx));old=tx;assert(om_chanset_prepare(&tx,1,21,0,0)==-22&&memcmp(&tx,&old,sizeof(tx))==0);
    assert(om_chanset_prepare(0,1,20,0,0)==-22);
    assert(om_chanset_prepare(&tx,1,80,0,1)==0);flags=123;
    assert(om_chanset_scan_request(&tx,0,&flags,&flags)==-22&&flags==123);
    tx.queue.cells[0]=7;flags=123;sec=456;
    assert(om_chanset_scan_request(&tx,0,&flags,&sec)==-22&&flags==123&&sec==456);
    printf("{\"plan_cases\":%u,\"table_max_records\":98,\"busy_overflow_and_invalid_refusal_atomic\":true,\"actual_scan_flags_order\":true,\"sample_target_exact\":true}\n",cases);
    return 0;
}
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--candidate",type=Path,required=True);p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    pins={str(f):sha(f)for f in a.candidate.iterdir()if f.is_file()};pins[str(Path(__file__).resolve())]=sha(Path(__file__));a.output.mkdir(parents=True);(a.output/"input-pins.json").write_text(json.dumps(pins,indent=2)+"\n")
    f=a.output/"fixture.c";f.write_text(FIXTURE,encoding="utf-8");cmd=[str(a.compiler),"-std=c11","-O1","-I"+str(a.candidate.resolve()),str(f),str(a.candidate/"openmitrastar_chanset_recovered.c"),"-o",str(a.output/"fixture.exe")]
    (a.output/"compile.command.json").write_text(json.dumps(cmd,indent=2)+"\n");r=subprocess.run(cmd,capture_output=True,timeout=60);(a.output/"compile.stderr").write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors="replace")
    r=subprocess.run([str(a.output/"fixture.exe")],capture_output=True,timeout=30);(a.output/"fixture.stdout").write_bytes(r.stdout);assert not r.returncode,r.stderr.decode(errors="replace");observed=json.loads(r.stdout);assert observed["plan_cases"]==24
    for f,h in pins.items():assert sha(Path(f))==h
    result=dict(status="PASS_HOST_CALLER_OWNED461_SCAN_TRANSACTION_SOURCE",hardware_accessed=False,firmware_eligible=False,inputs_unchanged=True,**observed,limits="Caller-owned serialization and memory; no kernel callback/quiesce/registration/real scan")
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))


if __name__=="__main__":main()
