"""Run actual candidate carrier syscall body, both ports and read failures."""
from pathlib import Path
import argparse,subprocess,json,hashlib
PRE=r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
#define AT_FDCWD (-100)
static unsigned which,fail,reads,closes,opens;
static char returned;
static long call5(long nr,long a,long b,long c,long d,long e){
 (void)d;(void)e;
 if(nr==56){
  const char*name=(void*)b;
  assert(a==AT_FDCWD&&c==0);
  assert(!strcmp(name,which?"/sys/class/net/eth1/carrier":"/sys/class/net/eth0/carrier"));
  opens++;return fail==1?-2:7;
 }
 if(nr==63){assert(a==7&&c==1);reads++;if(fail==2)return-5;if(fail==3)return0;*(char*)b=returned;return1;}
 assert(nr==57&&a==7);closes++;return0;
}
'''
TEST=r'''
int main(void){unsigned cases=0;
for(which=0;which<2;which++)for(fail=0;fail<4;fail++)for(unsigned value=0;value<3;value++){
 returned=value==0?'0':value==1?'1':'x';reads=closes=opens=0;
 int r=port_carrier(which);
 assert(r==(!fail&&returned=='1'));assert(opens==1);
 assert(reads==(fail==1?0:1)&&closes==(fail==1?0:1));cases++;
}
printf("PASS_ACTUAL_PORT_CARRIER_%u_CASES\n",cases);return0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise RuntimeError('Immutable output')
 text=a.source.read_text();start=text.index('static int port_carrier(');end=text.index('static void autostart(',start)
 a.output.mkdir();fixture=a.output/'fixture.c';fixture.write_text((PRE+text[start:end]+TEST).replace('return0','return 0').replace('return1','return 1'))
 subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(fixture),'-o',str(a.output/'fixture')],check=True)
 r=subprocess.run([str(a.output/'fixture')],capture_output=True,check=True)
 result={'status':r.stdout.decode().strip(),'hardware_accessed':False,'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'checks':'Actual openat/read/close path selection for bothports plus malformed/failed reads'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
