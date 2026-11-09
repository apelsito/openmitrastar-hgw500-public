"""Execute actual candidate autostart controller with host fake hardware."""
from pathlib import Path
import argparse,json,subprocess,hashlib
PRE=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned long word;
struct module_input{const char*path,*parameters;};
static const struct module_input radio_modules[19]={{0}};
static unsigned radio_loaded;
static int loaded,driver_fail,radio_fail,carrier0,carrier1;
static unsigned ticks,eth_calls,service_calls,wlan_calls,ap_calls,dhcp_calls;
static int eth0,eth1;
static char last[64];
static void say(const char*s){strncpy(last,s,sizeof(last)-1);}
static void load_driver(void){loaded=!driver_fail;}
static void iface(unsigned which,int up){eth_calls++;if(which)eth1=up;else eth0=up;}
static int port_carrier(unsigned which){return which?carrier1:carrier0;}
static void pause_ms(long ms){assert(ms==100);ticks++;}
static void ssh_start(void){service_calls++;}
static void https_start(void){service_calls++;}
static void load_radio(void){radio_loaded=radio_fail?3:19;}
static void radio_country(void){}
static void radio_ap(void){ap_calls++;}
static long child(const char*const args[],int background){
 if(!strcmp(args[1],"ifconfig")){assert(!background);wlan_calls++;}
 else{assert(!strcmp(args[1],"udhcpd")&&background);dhcp_calls++;}
 return 0;
}
'''
TEST=r'''
int main(void){
 unsigned cases=0;
 for(unsigned bits=0;bits<16;bits++){
  loaded=radio_loaded=ticks=eth_calls=service_calls=wlan_calls=ap_calls=dhcp_calls=0;
  eth0=eth1=0;driver_fail=bits&1;radio_fail=bits&2;carrier0=bits&4;carrier1=bits&8;
  autostart();
  if(driver_fail){assert(!eth_calls&&!service_calls&&!wlan_calls&&!ap_calls&&!dhcp_calls);}
  else{
   assert(service_calls==2&&eth_calls==3);
   assert(carrier0?(eth0&&!eth1):carrier1?(!eth0&&eth1):(eth0&&!eth1));
   assert(ticks==(!carrier0&&!carrier1?30:0));
   assert(wlan_calls==(radio_fail?0:1)&&ap_calls==(radio_fail?0:1)&&dhcp_calls==(radio_fail?0:1));
   assert(!strcmp(last,"AUTOSTART_END\n"));
  }
  cases++;
 }
 puts("PASS_ACTUAL_AUTOSTART_16_FAILURE_PORT_RADIO_SERVICE_CASES");
 return cases==16?0:1;
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise RuntimeError('Immutable output exists')
 text=a.source.read_text();start=text.index('static void autostart(void)');end=text.index('static volatile u32 ram',start)
 body=text[start:end];a.output.mkdir();fixture=a.output/'fixture.c';fixture.write_text(PRE+body+TEST)
 subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(fixture),'-o',str(a.output/'fixture')],check=True)
 r=subprocess.run([str(a.output/'fixture')],capture_output=True,check=True)
 result={'status':r.stdout.decode().strip(),'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'cases':16,'hardware_accessed':False,'limits':['Actual controller ordering only; syscalls/driver/AP/DHCP/portcarriers are mocks; physical boot required.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
