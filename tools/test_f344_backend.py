"""Run the actual F344 action backend against explicit fake ioctl/daemons."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'work/kernel-port/f344'
PRE=r'''
#define _GNU_SOURCE
#include "f344_native.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/if_arp.h>
#include <linux/sockios.h>
#include <time.h>
#define AP_TOOL "ap-cli"
#define STA_TOOL "sta-cli"
#define AP_PROGRAM "ap-daemon"
#define STA_PROGRAM "sta-daemon"
static struct f344_state actual;
static unsigned checks,primitives,inject,scan_off,scan_no_dfs,malformed;
static uint64_t clock_ms=1000;
#define C(x) do{checks++;assert(x);}while(0)
uint64_t f344_now_ms(void){return ++clock_ms;}
static bool fail(void){primitives++;if(inject==primitives){inject=0;return true;}return false;}
static int fake_ioctl(int fd,unsigned long request,struct ifreq*ifr){(void)fd;C(request==SIOCSIFHWADDR);C(!strcmp(ifr->ifr_name,"br0"));return fail()?-1:0;}
#define ioctl fake_ioctl
static int fake_sleep(const struct timespec*a,void*b){(void)a;(void)b;clock_ms+=10;return 0;}
#define nanosleep fake_sleep
static int control_write(const char*p,const char*v){if(fail())return -1;if(strstr(p,"channel_hold")){actual.topology.channel_hold=*v=='1';if(*v=='1')actual.topology.csa_drained=false;}else if(strstr(p,"rf_enable"))actual.topology.open_gate=*v=='1';else return -1;return 0;}
static int stop_daemon(struct f344_native*n,struct f344_daemon*d,const char*p,const char*t,const char*i){(void)n;(void)p;(void)t;(void)i;if(fail())return -1;d->pid=0;actual.ap_enabled=actual.upstream_completed=false;return 0;}
int f344_if_flags(struct f344_native*n,const char*name,bool up){(void)n;if(fail())return -1;if(!strcmp(name,"wifi0"))actual.topology.primary_up=up;else actual.topology.secondary_up=up;return 0;}
int f344_bridge_member(struct f344_native*n,const char*name,bool add){(void)n;if(fail())return -1;if(!strcmp(name,"wifi0"))actual.primary_bridged=add;else actual.secondary_bridged=add;return 0;}
int f344_layout_observe(struct f344_state*s){*s=actual;return 0;}
int f344_radio_observe(struct f344_native*n,struct f344_state*s){(void)n;*s=actual;return 0;}
int f344_channel_set(struct f344_native*n,const uint8_t*m){(void)n;C(!actual.topology.primary_up&&!actual.topology.secondary_up);if(fail())return -1;memcpy(actual.channel_mask,m,32);return 0;}
int f344_run(char*const a[],char*out,size_t cap,uint64_t deadline){(void)deadline;if(fail())return -1;out[0]=0;
 if(strstr(a[0],"iwconfig")){C(!strcmp(a[1],"wifi0")&&!strcmp(a[2],"channel"));actual.frequency_mhz=atoi(a[3])?5000+5*atoi(a[3]):5180;return 0;}
 C(strstr(a[0],"iwpriv")!=NULL);C(!strcmp(a[1],"wifi0"));
 if(!strcmp(a[2],"mode")){actual.bandwidth=actual.configured_bandwidth=strstr(a[3],"80")?80:strstr(a[3],"40")?40:20;}
 else if(!strcmp(a[2],"repeater")){actual.topology.repeater=!!atoi(a[3]);}
 else if(!strcmp(a[2],"scan_no_dfs")){C(f344_mask_non_dfs(actual.channel_mask));scan_no_dfs=atoi(a[3]);}
 else if(!strcmp(a[2],"disablescan")){C(f344_mask_non_dfs(actual.channel_mask)&&scan_no_dfs);scan_off=atoi(a[3]);}
 else if(!strcmp(a[2],"get_scan_dfs"))snprintf(out,cap,"wifi0 get_scan_dfs:%u\n",scan_no_dfs);
 else if(!strcmp(a[2],"get_disablescan")){if(malformed)snprintf(out,cap,"wifi0 get_disablescan:  \n");else snprintf(out,cap,"wifi0 get_disablescan:%u\n",scan_off);}
 else return -1;
 return 0;
}
static int qdrv_command(const char*s){if(fail())return -1;
 if(!strcmp(s,"mode 0 drain-csa\n")){C(actual.topology.channel_hold&&!actual.topology.open_gate&&!actual.topology.primary_up&&!actual.topology.secondary_up);if(!actual.topology.csa_reuse_supported)return -1;actual.topology.csa_drained=true;return 0;}
 if(!strcmp(s,"stop 0 all\n")){C(actual.topology.csa_drained);actual.topology.primary_present=actual.topology.secondary_present=false;actual.mode=F344_MODE_NONE;return 0;}
 if(!strcmp(s,"start 0 ap wifi1\n")){C(actual.topology.primary_mode==F344_MODE_STA&&actual.topology.repeater);actual.topology.secondary_present=true;actual.topology.secondary_mode=F344_MODE_AP;actual.mode=F344_MODE_REPEATER;return 0;}
 if(!strncmp(s,"start 0 ",8)){C(!actual.topology.primary_present);actual.topology.primary_present=true;actual.topology.primary_mode=strstr(s," sta ")?F344_MODE_STA:F344_MODE_AP;actual.mode=actual.topology.primary_mode;return 0;}
 if(!strncmp(s,"bridge 0 ",9)){actual.three_address_bridge=strstr(s,"enable")!=NULL;return 0;}
 return -1;
}
int f344_render_profile(const struct f344_profile*p,const char*d,char*ap,size_t ac,char*sta,size_t sc){(void)d;if(fail())return -1;snprintf(ap,ac,"/fake/ap.conf");snprintf(sta,sc,"/fake/wpa.conf");memcpy(actual.profile_digest,p->target.profile_digest,32);return 0;}
int f344_render_ap_follow(const struct f344_profile*p,const char*d,char*ap,size_t ac){(void)d;C(p->target.ap_frequency_mhz==actual.frequency_mhz);if(fail())return -1;snprintf(ap,ac,"/fake/ap.conf");return 0;}
static int spawn_daemon(struct f344_native*n,struct f344_daemon*d,const char*p,bool repeater){(void)repeater;if(fail())return -1;d->pid=123;actual.topology.primary_up=true;if(!strcmp(p,STA_PROGRAM)){C(!scan_off&&scan_no_dfs);actual.upstream_completed=true;}else {actual.ap_enabled=true;if(n->running_profile->target.mode==F344_MODE_REPEATER)actual.topology.secondary_up=true;}return 0;}
static int station_ready(struct f344_native*n,const struct f344_profile*p,unsigned*f){(void)n;(void)p;if(fail())return -1;C(actual.upstream_completed);*f=actual.frequency_mhz;return 0;}
'''
TEST=r'''
static int snapshot(void*c,struct f344_state*s){(void)c;*s=actual;return 0;}
static int inspect(void*c,struct f344_state*s){(void)c;*s=actual;return 0;}
static int wait_target(void*c,const struct f344_target*t,struct f344_state*s){(void)c;(void)t;*s=actual;return 0;}
static void setup(struct f344_native*n,unsigned from,unsigned to){unsigned i;memset(n,0,sizeof(*n));memset(&actual,0,sizeof(actual));primitives=0;scan_off=from==F344_MODE_AP;scan_no_dfs=1;malformed=0;
 actual.valid=F344_SNAPSHOT_VALID;actual.snapshot_cookie=1;actual.mode=from;actual.frequency_mhz=5180;actual.bandwidth=actual.configured_bandwidth=80;
 actual.topology.valid=actual.topology.core_started=actual.topology.csa_known=actual.topology.csa_reuse_supported=true;
 actual.topology.primary_present=actual.topology.primary_up=actual.topology.open_gate=actual.primary_bridged=true;
 actual.topology.primary_mode=from==F344_MODE_AP?F344_MODE_AP:F344_MODE_STA;actual.topology.repeater=from==F344_MODE_REPEATER;actual.topology.secondary_present=actual.topology.secondary_up=actual.secondary_bridged=from==F344_MODE_REPEATER;actual.topology.secondary_mode=F344_MODE_AP;
 actual.ap_enabled=from!=F344_MODE_STA;actual.upstream_completed=from!=F344_MODE_AP;actual.three_address_bridge=true;actual.primary_mac[0]=2;actual.primary_mac[5]=1;actual.secondary_mac[0]=2;actual.secondary_mac[5]=2;
 memset(actual.profile_digest,1,32);memset(actual.management_digest,3,32);
 for(i=36;i<=48;i+=4)actual.channel_mask[i/8]|=1U<<(i%8);
 n->original.target.mode=from;n->original.target.bandwidth=80;n->original.target.ap_frequency_mhz=5180;n->original.target.profile_cookie=1;memcpy(n->original.target.channel_mask,actual.channel_mask,32);memcpy(n->original.target.profile_digest,actual.profile_digest,32);
 n->target=n->original;n->target.target.mode=to;n->target.target.profile_cookie=2;memset(n->target.target.profile_digest,2,32);
 n->running_profile=&n->original;n->ap.pid=from!=F344_MODE_STA?124:0;n->sta.pid=from!=F344_MODE_AP?125:0;
 n->global_deadline=f344_now_ms()+120000;n->phase_deadline=f344_now_ms()+60000;strcpy(n->transaction,"/fake/transaction");
}
int main(void){struct f344_native n;struct f344_ops o={&n,snapshot,inspect,execute,wait_target};struct f344_result r;unsigned a,b,total,k;
 for(a=1;a<=3;a++)for(b=1;b<=3;b++){setup(&n,a,b);C(!f344_apply(&o,&n.target.target,&r));C(r.outcome==F344_APPLIED_READBACK&&!r.traffic_verified);}
 setup(&n,1,3);C(!f344_apply(&o,&n.target.target,&r));total=primitives;
 for(k=1;k<=total;k++){setup(&n,1,3);inject=k;C(f344_apply(&o,&n.target.target,&r)!=0);C(r.outcome==F344_ROLLED_BACK_READBACK);C(actual.mode==F344_MODE_AP);}
 setup(&n,1,2);malformed=1;C(private_readback(&n,"get_disablescan",0)!=0);
 setup(&n,1,2);actual.topology.csa_reuse_supported=false;C(f344_apply(&o,&n.target.target,&r)==-95&&!primitives);
 printf("F344_ACTUAL_BACKEND_PASS checks=%u transitions=9 primitive_failures=%u fake_ioctls_and_daemons=1 hardware=0\n",checks,total);return 0;}
'''
def main():
 out=ROOT/'outputs/preflight'/('f344-native-backend-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 source=(S/'f344_backend.c').read_text();code=PRE+''.join(function(source,n) for n in ('join_path','run_private','private_readback','execute'))+TEST;(out/'test.c').write_bytes(code.encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -I'{linux(S)}' '{linux(out/'test.c')}' '{linux(S/'f344_transaction.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'status':'PASS_ACTUAL_ACTION_BACKEND_FAKE_TRANSPORTS' if not p.returncode else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'backend_sha256':hashlib.sha256((S/'f344_backend.c').read_bytes()).hexdigest(),'hardware':False,'physical_wifi':'USER_DEFERRED'};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
