"""Execute actual491 dispatch snippets across signed32 low16 value boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_wireless.c';text=source.read_text();setter=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');getter=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');case='\tcase OM_OEM_PARAM_COC_MOVE_NDFS:';ss=text.index(case,setter);se=text.index('\n\tcase ',ss+len(case));gs=text.index(case,getter);ge=text.index('\n\tcase ',gs+len(case));sbody=text[ss:se];gbody=text[gs:ge];assert ss<getter<gs<text.index('\nstatic ',getter)
 fixture=r'''#include <stdint.h>
#include <assert.h>
#include <string.h>
typedef uint32_t u32;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define OM_OEM_PARAM_COC_MOVE_NDFS 491
struct ieee80211com {u32 om_coc_move_ndfs,unchanged;};
static int set(struct ieee80211com*ic,int param,int value){switch(param){
'''+sbody+r'''
default:return -1;}}
static int get(struct ieee80211com*ic,int*param){switch(param[0]&0xffff){
'''+gbody+r'''
default:return -1;}}
int main(void){struct ieee80211com ic;int v,p;unsigned lo;for(lo=0;lo<65536;lo++){uint32_t xs[]={lo,0xffff0000U|lo,0x7fff0000U|lo,0x80000000U|lo};for(unsigned i=0;i<4;i++){memset(&ic,0,sizeof(ic));ic.unchanged=0x12345678;p=491;v=(int)xs[i];assert(set(&ic,p,v)==0&&ic.om_coc_move_ndfs==xs[i]&&ic.unchanged==0x12345678);p=491|0x5a0000;assert(get(&ic,&p)==0&&(u32)p==xs[i]&&ic.unchanged==0x12345678);}}ic.om_coc_move_ndfs=123;p=490;assert(set(&ic,p,-5)==-1&&ic.om_coc_move_ndfs==123);assert(get(&ic,&p)==-1&&ic.om_coc_move_ndfs==123);return 0;}
'''
 f=a.output/'fixture.c';f.write_text(fixture);pins={str(source):sha(source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert r.returncode==0,r.stderr
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_COC491_IOCTL_SETGET_FULL_U32_BOUNDARY_FIXTURE',hardware_accessed=False,firmware_eligible=False,cases=262144,source_sha256=sha(source),setter_case_sha256=hashlib.sha256(sbody.encode()).hexdigest(),getter_case_sha256=hashlib.sha256(gbody.encode()).hexdigest(),limits='Actual491dispatch snippets; otherdispatcherconditions andphysicalWEXT separate');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
