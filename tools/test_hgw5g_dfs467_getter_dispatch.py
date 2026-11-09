"""Actual467WEXTcasefixture: sampledresult noterrno, preservesmaskedeventid."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_wireless.c';s=source.read_text();start=s.index('case OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE:',s.index('ieee80211_ioctl_getparam('));end=s.index('\n\tcase ',start);body=s[start:end];c='''#include <assert.h>
struct ic{int value,calls;};
#define OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE 467
static int om_ieee80211_dfs_channel_available(struct ic*ic){ic->calls++;return ic->value;}
static int get(struct ic*ic,int*param){switch(param[0]&0xffff){
'''+body+'''
default:return -1;}}
int main(void){struct ic ic;for(unsigned hi=0;hi<65536;hi++)for(unsigned result=0;result<2;result++){ic.value=result?1:-95;ic.calls=0;int param=(int)((hi<<16)|467);assert(get(&ic,&param)==0&&param==ic.value&&ic.calls==1);}return 0;}
''';f=a.output/'fixture.c';f.write_text(c);pins={str(source):sha(source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert r.returncode==0,r.stderr;assert all(sha(p)==h for p,h in pins.items());result=dict(status='PASS_ACTUAL_DFS467_WEXT_VALUE_RETURN_MASK_FIXTURE',hardware_accessed=False,firmware_eligible=False,cases=131072,source_sha256=sha(source),case_sha256=hashlib.sha256(body.encode()).hexdigest());(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
