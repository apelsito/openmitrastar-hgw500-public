"""TestactualSOURCE20B descriptoradmission across every1000-byte arena state.

Fakehostfixture only: fullARC descriptorarena/allpaths qualification remains.
Exercises undershoot/overshoot/exactlastfit/refusal before payload or statewrite.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 src=a.candidate/'source/wlan';text=(src/'ieee80211_beacon_desc.c').read_text();start=text.index('\tcase 70:');end=text.index('\tcase IEEE80211_ELEMID_RATES:',start);block=text[start:end].replace('return pre_frm;','return 0;').replace('frm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);','return 1;')
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
typedef uint32_t u32;
struct beacon_shared_ie_t{u32 words[5];};
struct parameter{u32 curr;uint8_t *buf;u32 size;};
static int actual(struct parameter*param){switch(70){
'''+block+'''\n default:break;}return 2;}
int main(void){struct parameter p;unsigned size,used;for(size=0;size<=1000;size++)for(used=0;used<=1020;used++){
p.buf=(uint8_t*)(uintptr_t)0x10000;p.curr=0x10000+used;p.size=size;assert(actual(&p)==((used<=size&&size-used>=20)?1:0));assert(p.curr==0x10000+used&&p.size==size);}
p.curr=0xffff;assert(actual(&p)==0);p.curr=UINT32_MAX;assert(actual(&p)==0);return0;}
'''.replace('return0;','return 0;')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);proc=subprocess.run([str(a.compiler),'-std=c11','-O1',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr
 proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert proc.returncode==0,proc.stderr
 result=dict(status='PASS_HOST_ACTUAL_DESCRIPTOR_ADMISSION_FIXTURE',hardware_accessed=False,firmware_eligible=False,arena_sizes=1001,used_values=1021,cases=1022023,descriptor_bytes=20,capacity_bytes_max=1000,limits='Sourceadmissiononly; actualARCpointerlayout/worstbeaconpaths/runtimeacceptance gatespending')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
