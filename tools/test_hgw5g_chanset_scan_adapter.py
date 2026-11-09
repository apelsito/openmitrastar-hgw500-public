"""Test scaled sample and candidate choice using decoded OEM semantics.

Uses real C source, boundary truncation, wrap/signed selection counterexamples
and all eligibility states; no shared memory, radio or firmware execution.
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
static uint32_t state=0x62b75acf;
static uint32_t next32(void){state=state*1664525U+1013904223U;return state;}
static uint32_t scale(uint32_t v,uint32_t d){return v<4294967U?(uint32_t)((uint64_t)v*1000/d):(v/d)*1000U;}
static int64_t signed32(uint32_t v){return v<0x80000000U?v:(int64_t)v-4294967296LL;}
static const struct om_chanset_entry *reference(const struct om_chanset_entry *rows,unsigned n,unsigned band,unsigned maxbw,unsigned scan,int automatic,unsigned benefit){
    const struct om_chanset_entry *b20=0,*b40=0,*b80=0,*b160=0,*p;unsigned i;
    for(i=0;i<n;i++){
        const struct om_chanset_entry *e=&rows[i],**b=0;
        if(e->invalid||e->inactive||e->bandwidth>maxbw||e->bandwidth<scan)continue;
        switch(e->bandwidth){case20:b=&b20;break;case40:b=&b40;break;case80:b=&b80;break;case160:b=&b160;break;default:continue;}
        if(!*b||signed32(e->cost)<signed32((*b)->cost))*b=e;
    }
    p=b160?b160:b80?b80:b40?b40:b20;
    if(automatic){if(band==0){if(b40&&b20&&signed32(b20->cost*benefit)<signed32(b40->cost))p=b20;}
      else if(b160&&b80)p=signed32(b160->cost)<=signed32(b80->cost*benefit)?b160:b80;}
    return p;
}
int main(void){
    struct om_chanset_scan_sample input,output,sentinel;
    struct om_chanset_entry e,old,rows[8];
    const unsigned offsets[]={1,2,3,4,6,7,8,9,10,11,12};
    const uint32_t boundaries[]={0,1,4294966,4294967,4294968,0x7fffffffU,0x80000000U,0xffffffffU};
    unsigned i,j,k,n=0,selections=0;
    memset(&input,0,sizeof(input));memset(&output,0x5a,sizeof(output));sentinel=output;
    assert(om_chanset_normalize_sample(&input,&output)==-11 && memcmp(&output,&sentinel,sizeof(output))==0);
    for(i=0;i<8;i++)for(j=0;j<8;j++){
        uint32_t *words=(uint32_t*)&input,*result=(uint32_t*)&output;input.attempts=boundaries[j]?boundaries[j]:1;input.bandwidth=80;
        for(k=0;k<11;k++)words[offsets[k]]=boundaries[i];
        assert(om_chanset_normalize_sample(&input,&output)==0 && output.attempts==1000 && output.bandwidth==80);
        for(k=0;k<11;k++)assert(result[offsets[k]]==scale(boundaries[i],input.attempts));n++;
    }
    for(i=0;i<100000;i++){
        uint32_t *words=(uint32_t*)&input,*result=(uint32_t*)&output;
        input.attempts=next32()|1U;input.bandwidth=40;
        for(k=0;k<11;k++)words[offsets[k]]=next32();
        assert(om_chanset_normalize_sample(&input,&output)==0);
        for(k=0;k<11;k++)assert(result[offsets[k]]==scale(words[offsets[k]],input.attempts));n++;
    }
    memset(&e,0x33,sizeof(e));old=e;output.attempts=999;
    assert(om_chanset_update_scan_entry(&e,&output)==-22 && memcmp(&e,&old,sizeof(e))==0);
    output.attempts=1000;output.cca_interference=5;output.cca_primary=6;output.cca_secondary=7;output.cca_secondary40=8;
    assert(om_chanset_update_scan_entry(&e,&output)==0 && e.scan_cca==5 && e.cca[0]==6 && e.cca[1]==7 && e.cca[2]==8 && e.cca[3]==6 && e.primary_cca[0]==0);
    for(i=0;i<100000;i++){
        struct om_chanset_view view;const struct om_chanset_entry *actual,*expected;
        const unsigned widths[]={20,40,80,160};unsigned band=i&1,maxbw=widths[(i>>1)&3],scan=widths[(i>>3)&3],automatic=(i>>5)&1,benefit=next32();
        for(k=0;k<8;k++){memset(&rows[k],0,sizeof(rows[k]));rows[k].primary=k+1;rows[k].bandwidth=widths[k&3];rows[k].cost=next32();rows[k].invalid=(i>>(k&7))&1;rows[k].inactive=(i>>((k+2)&7))&1;}
        view.entries=rows;view.count=8;view.capacity=8;expected=reference(rows,8,band,maxbw,scan,automatic,benefit);
        assert(om_chanset_select(&view,band,maxbw,scan,automatic,benefit,&actual)==!!expected && actual==expected);selections++;
    }
    {struct om_chanset_view view={rows,2,2};const struct om_chanset_entry *actual;
     memset(rows,0,sizeof(rows));rows[0].bandwidth=rows[1].bandwidth=20;rows[0].cost=rows[1].cost=7;
     assert(om_chanset_select(&view,0,20,20,0,2,&actual)==1&&actual==rows);
     rows[1].cost=0x80000000U;assert(om_chanset_select(&view,0,20,20,0,2,&actual)==1&&actual==rows+1);
     rows[0].bandwidth=80;rows[1].bandwidth=160;rows[0].cost=10;rows[1].cost=20;
     assert(om_chanset_select(&view,1,160,20,1,2,&actual)==1&&actual==rows+1);}
    {struct om_chanset_view view={(const struct om_chanset_entry*)(uintptr_t)1,2,1};const struct om_chanset_entry *actual=(const struct om_chanset_entry*)(uintptr_t)3;
     assert(om_chanset_select(&view,0,20,20,0,2,&actual)==-22&&(uintptr_t)actual==3);}
    {int x=123;assert(om_chanset_edges(&e,0,0,5,&x,&x)==-22&&x==123);}
    printf("{\"normalized_samples\":%u,\"normalized_fields\":11,\"selection_cases\":%u,\"signed_wrap_and_tie_counterexamples\":true}\n",n,selections);return0;
}
'''.replace('case20:','case 20:').replace('case40:','case 40:').replace('case80:','case 80:').replace('case160:','case 160:').replace('return0;','return 0;')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--candidate",type=Path,required=True);p.add_argument("--compiler",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    pins={str(x):sha(x)for x in a.candidate.iterdir()if x.is_file()};pins[str(Path(__file__).resolve())]=sha(Path(__file__));pins[str(a.compiler)]=sha(a.compiler)
    a.output.mkdir(parents=True);(a.output/"input-pins.json").write_text(json.dumps(pins,indent=2)+"\n");f=a.output/"fixture.c";f.write_text(FIXTURE,encoding="utf-8")
    cmd=[str(a.compiler),"-std=c11","-O1","-fno-strict-aliasing","-I"+str(a.candidate.resolve()),str(f),str(a.candidate/"openmitrastar_chanset_recovered.c"),"-o",str(a.output/"fixture.exe")]
    (a.output/"compile.command.json").write_text(json.dumps(cmd,indent=2)+"\n");r=subprocess.run(cmd,capture_output=True,timeout=60);(a.output/"compile.stderr").write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors="replace")
    r=subprocess.run([str(a.output/"fixture.exe")],capture_output=True,timeout=30);(a.output/"fixture.stdout").write_bytes(r.stdout);assert not r.returncode,r.stderr.decode(errors="replace");observed=json.loads(r.stdout);assert observed["normalized_samples"]==100064 and observed["selection_cases"]==100000
    for path,h in pins.items():assert sha(Path(path))==h,"input drift "+path
    result=dict(status="PASS_HOST_ACTUAL461_NORMALIZATION_AND_FINAL_CHOICE_ADAPTERS",hardware_accessed=False,firmware_eligible=False,inputs_unchanged=True,**observed,limits="Pure caller-owned samples/candidates; no sharedread/realcallbacks/registration/RF")
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))


if __name__=="__main__":main()
