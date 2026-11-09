"""Execute actual449 boolsetter; compare untouchedstate and signed boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);file=a.candidate/'source/wlan/ieee80211_wireless.c';text=file.read_text();start=text.index('case OM_OEM_PARAM_20_40_BSS_COEX:',text.index('ieee80211_ioctl_setparam('));end=text.index('case OM_OEM_PARAM_COC_MOVE_NDFS:',start);body=text[start:end];source='''#include <stdint.h>
#include <assert.h>
typedef uint8_t u8;
#define WRITE_ONCE(x,v) ((x)=(v))
#define OM_OEM_PARAM_20_40_BSS_COEX 449
struct ic {u8 om_20_40_bss_coex;uint32_t untouched;};
static int set(struct ic*ic,int param,int value){switch(param){
'''+body+'''
default:return -1;}}
int main(void){struct ic ic;for(unsigned x=0;x<65536;x++){uint32_t values[]={x,0x80000000U|x,0xffff0000U|x};for(unsigned i=0;i<3;i++){ic.om_20_40_bss_coex=9;ic.untouched=0x12345678;assert(set(&ic,449,(int)values[i])==0&&ic.om_20_40_bss_coex==(values[i]!=0)&&ic.untouched==0x12345678);}}ic.om_20_40_bss_coex=9;assert(set(&ic,450,1)==-1&&ic.om_20_40_bss_coex==9);return 0;}
''';fixture=a.output/'fixture.c';fixture.write_text(source);pins={str(file):sha(file),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(fixture),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert proc.returncode==0,proc.stderr;assert all(sha(p)==h for p,h in pins.items());result=dict(status='PASS_ACTUAL449_BOOL_SETTER_NO_OTHER_MUTATION',hardware_accessed=False,firmware_eligible=False,cases=196608,source_sha256=sha(file),case_sha256=hashlib.sha256(body.encode()).hexdigest());(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
