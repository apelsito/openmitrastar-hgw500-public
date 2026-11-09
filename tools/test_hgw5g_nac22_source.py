"""ActualNAC22 setter/prefixgetter fixtures with asynchronousread counterexample."""
import argparse
import json
from pathlib import Path
import subprocess

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=(a.candidate/'source/wlan/ieee80211_wireless.c').read_text()
 start=text.index('struct om_nac_prefix {');end=text.index('\nstatic int\nieee80211_ioctl_getparam(',start);helper=text[start:end]
 start=text.index('\tcase OM_OEM_PARAM_NAC_MODE:');end=text.index('\n\tcase ',start+1);setter=text[start:end]
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
typedef uint16_t u16;typedef uint8_t u8;typedef uint32_t u32;
#define EAGAIN 11
#define READ_ONCE(x) (x)
#define OM_OEM_PARAM_NAC_MODE 457
#define IEEE80211_M_HOSTAP 6
struct ieee80211vap{int iv_opmode;};
static int observedvalue;static unsigned sends;
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int id,int value,void*d,int n){sends++;observedvalue=value;assert(id==457&&d==NULL&&n==0);}
'''+helper+'''static int actual_set(struct ieee80211vap*vap,int param,int value){switch(param){
'''+setter+'''\n default:break;}return0;}
int main(void){struct om_nac_prefix n;struct ieee80211vap v;unsigned a,b,e;int result;uint32_t expected;
result=123;assert(om_nac_prefix_sample(NULL,&result)==-11&&result==123);n.value1=0;result=123;assert(om_nac_prefix_sample(&n,&result)==-11&&result==123);
for(a=0;a<65536;a++)for(b=1;b<65536;b+=257){n.value0=a;n.value1=b;n.enabled=(a^b);n.reserved=0xbeef;result=-1;expected=(b<<16)|(((a*100U/b)&255U)<<8)|((a^b)&255U);assert(om_nac_prefix_sample(&n,&result)==0&&(uint32_t)result==expected);assert(n.value0==a&&n.value1==b&&n.reserved==0xbeef);}
for(a=0;a<16;a++)for(b=0;b<65536;b++){v.iv_opmode=a;sends=0;assert(actual_set(&v,457,b)==0&&sends==(a==6));if(sends)assert(observedvalue==(int)b);}
return0;}
'''.replace('return0;','return 0;')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);p=subprocess.run([str(a.compiler),'-std=c11','-O1',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr;p=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert p.returncode==0,p.stderr
 result=dict(status='PASS_ACTUAL_HOST_NAC22_SET_PREFIX_GET_FIXTURE',hardware_accessed=False,firmware_eligible=False,prefix_samples=16711680,setter_cases=1048576,missing_or_zero_refusal=True,lifecycle_acceptance=False,coherent_snapshot_claim=False,limits='Scalarpackingonly,nocrossMuCgenerationcoherence; noNACmonitorphysicalverification')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
