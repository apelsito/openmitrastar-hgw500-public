"""Exercise OEM publication, real lookup/readback, sysfs parser and PREPARE."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,shutil
from test_f355_lifetime import extract
import test_f367_functional as old
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f367r5-regulatory-profile'
PEER=ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c'
KERNEL='/home/user/openmitrastar-build/f358-flash-arbitration-20260921T173956Z/linux'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def wsl(*args):return subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',*args],capture_output=True,text=True,check=True).stdout
EXTRA=r'''
#include <stdlib.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stddef.h>
#include <stdarg.h>
#include <linux/wireless.h>
#include "f367r5_oem_ioctl.h"
#define IEEE80211_M_STA 1
#define IEEE80211_MODE_AUTO 0
#define IEEE80211_MODE_TURBO_A 1
#define IEEE80211_MODE_TURBO_G 2
#define IEEE80211_MODE_11G 3
#define IEEE80211_CHANNEL_STATUS_NON_AVAILABLE 0
#define IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED 1
#define IEEE80211_CHAN_DFS_CAC_DONE 0x00200000
#define IEEE80211_CHAN_DFS_CAC_IN_PROGRESS 0x01000000
#define CTRY_DEFAULT 0
#define IEEE80211_IS_CHAN_B(c) 0
#define IEEE80211_IS_CHAN_ANYG(c) 0
#define IEEE80211_IS_CHAN_A(c) 0
#define isset(a,n) ((a)[(n)/8]&(1u<<((n)%8)))
#define isclr(a,n) (!isset(a,n))
#define setbit(a,n) ((a)[(n)/8]|=1u<<((n)%8))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define __user
#define EXPORT_SYMBOL(x)
#define TAILQ_FIRST(p) (&fixture_vap)
#define netdev_priv(p) (&fixture_vap)
#define IEEE80211_DPRINTF(...) do{}while(0)
#define printk(...) do{}while(0)
static char reject_reason[120];
static void trace_warning(const char *format,const char *reason,int error){(void)format;(void)error;snprintf(reject_reason,sizeof(reject_reason),"%s",reason);}
#define pr_warn_ratelimited trace_warning
struct ieee80211_channel{unsigned ic_ieee,ic_flags,ic_freq,ic_radardetected;};
struct ieee80211com{struct ieee80211_channel*ic_curchan;unsigned ic_opmode,ic_radar_bw,ic_phymode,ic_flags,ic_flags_ext,ic_country_code;bool repeater;int ic_nchans,ic_des_mode,ic_vaps;
 struct ieee80211_channel ic_channels[3];unsigned char ic_chan_active[32],ic_chan_dfs_required[32];
 unsigned ic_chan_availability_status[256];int(*ic_mark_dfs_channels)(struct ieee80211com*,int,struct ieee80211_channel*);void(*ic_mark_channel_dfs_cac_status)(struct ieee80211com*,struct ieee80211_channel*,unsigned,bool);};
struct ieee80211vap{struct ieee80211com*iv_ic;unsigned iv_opmode;};
static struct ieee80211vap fixture_vap;struct net_device{int unused;};static struct net_device dev;struct iw_request_info{int unused;};
static int copy_from_user(void*d,const void*s,size_t n){memcpy(d,s,n);return 0;}
static unsigned ieee80211_get_chanflags(int mode){(void)mode;return 0;}
static bool qdrv_radar_first_call=true;
'''
IO=r'''
struct module_attribute{int unused;};struct module_kobject{void*mod;};
struct param_attribute{struct module_attribute mattr;const struct kernel_param*param;};
#define to_param_attr(p) ((struct param_attribute*)(p))
static void kernel_param_lock(void*m){(void)m;}static void kernel_param_unlock(void*m){(void)m;}
static bool param_check_unsafe(const struct kernel_param*p){return !p->flags;}
static int published,claimed,fail_ioctl,alter_active;
static int mock_socket(int domain,int type,int protocol){assert(domain==AF_INET&&type==SOCK_DGRAM&&!protocol);return 99;}
static int mock_close(int fd){assert(fd==99||fd==98);return 0;}
static uid_t mock_geteuid(void){return 0;}
static int mock_open(const char*path,int flags,...){assert(!strcmp(path,"/run/openmitrastar/f367/dfs-profile-publication"));assert((flags&(O_CREAT|O_EXCL|O_NOFOLLOW))==(O_CREAT|O_EXCL|O_NOFOLLOW));if(claimed){errno=EEXIST;return -1;}claimed=1;return 98;}
static ssize_t mock_write(int fd,const void*p,size_t n){assert(fd==98&&n==22&&!memcmp(p,"OEM_SUBIO14_CHANNEL52\n",n));return n;}
static FILE*mock_fopen(const char*path,const char*mode){FILE*f=tmpfile();char b[4096];assert(!strcmp(path,"/sys/module/qdrv/parameters/openmitrastar_dfs_state")&&!strcmp(mode,"r"));f367_state_get(b,NULL);fputs(b,f);rewind(f);return f;}
static int mock_ioctl(int fd,unsigned long command,...){va_list args;struct iwreq*wr;int rc=0;va_start(args,command);wr=va_arg(args,struct iwreq*);va_end(args);assert(fd==99&&!strcmp(wr->ifr_name,"wifi0"));
 if(command==IEEE80211_IOCTL_GETPARAM){unsigned key;memcpy(&key,wr->u.name,4);assert(key==115);key=ic.ic_country_code==724?21317:0;memcpy(wr->u.name,&key,4);}
 else if(command==IEEE80211_IOCTL_GETCHANLIST)rc=ieee80211_ioctl_getchanlist(&dev,NULL,&wr->u,wr->u.data.pointer);
 else if(command==IEEE80211_IOCTL_GETCHANINFO)rc=ieee80211_ioctl_getchaninfo(&dev,NULL,&wr->u,wr->u.data.pointer);
 else if(command==IEEE80211_IOCTL_EXT){assert(wr->u.data.flags==14&&wr->u.data.length==1&&*(int*)wr->u.data.pointer==52);published++;if(fail_ioctl){errno=EIO;return -1;}rc=dispatch_regulatory(&dev,wr);if(alter_active)setbit(ic.ic_chan_active,100);}
 else assert(!"unexpected ioctl or mutation");
 if(rc){errno=-rc;return -1;}return 0;}
#define socket mock_socket
#define close mock_close
#define geteuid mock_geteuid
#define open mock_open
#define write mock_write
#define fopen mock_fopen
#define ioctl mock_ioctl
#define main profile_main
#include "om-f367-dfs-profile.c"
#undef main
#undef socket
#undef close
#undef geteuid
#undef open
#undef write
#undef fopen
#undef ioctl
static void reset(void){memset(&ic,0,sizeof(ic));memset(&f367_policy,0,sizeof(f367_policy));memset(&qdrv_f338_health,0,sizeof(qdrv_f338_health));memset(&qdrv_radar_cb,0,sizeof(qdrv_radar_cb));
 ic.ic_channels[0]=(struct ieee80211_channel){36,0,5180,0};ic.ic_channels[1]=(struct ieee80211_channel){52,0,5260,0};ic.ic_channels[2]=(struct ieee80211_channel){56,0,5280,0};
 ic.ic_nchans=3;ic.ic_curchan=&ic.ic_channels[0];ic.ic_opmode=6;ic.ic_radar_bw=80;ic.ic_phymode=13;ic.ic_country_code=724;setbit(ic.ic_chan_active,36);setbit(ic.ic_chan_active,52);setbit(ic.ic_chan_active,56);
 ic.ic_mark_dfs_channels=qdrv_wlan_80211_mark_dfs;fixture_vap.iv_ic=&ic;fixture_vap.iv_opmode=6;qdrv_radar_cb.ic=&ic;qdrv_radar_cb.region=2;qdrv_radar_configured=true;qdrv_radar_first_call=true;
 f367_control_fault=f367_transition_prepared=f367_on_dfs=f367_switch_inflight=false;f367_software_injections=f367_native_callbacks=published=claimed=fail_ioctl=alter_active=stops=0;
 f367_nop_start_ns=f367_nop_deadline_ns=0;now_ns=100000000;jiffies=20;qdrv_f367_init();reject_reason[0]=0;stop_fails=false;}
static int call_profile(const char*action){char*argv[]={"profile",(char*)action,NULL};return profile_main(2,argv);}
static long store_value(const char*value){struct kernel_param p={.ops=&f367_control_ops,.flags=0};struct param_attribute a={.param=&p};struct module_kobject m={0};return param_attr_store(&a.mattr,&m,value,strlen(value));}
static void matured(void){now_ns=1900000000000ULL;jiffies=380000;}
#define CHECK(x) do{checks++;assert(x);}while(0)
int main(int argc,char**argv){unsigned char active_before[32];u64 deadline;
 if(argc>1){reset();if(!getenv("F367R5_MISSING")){int saved=dup(1);FILE*quiet=tmpfile();fflush(stdout);dup2(fileno(quiet),1);assert(!call_profile("publish"));fflush(stdout);dup2(saved,1);close(saved);fclose(quiet);}qdrv_radar_first_call=false;qdrv_radar_cb.enabled=true;matured();
  if(!strcmp(argv[1],"check"))return call_profile("check");
  if(!strcmp(argv[1],"snapshot")){char b[4096];int n=f367_state_get(b,NULL);b[n-2]=0;printf("%s,\"kernel_state_present\":1,\"provider_present\":1}\n",b);return 0;}
  if(!strcmp(argv[1],"store")){long rc;if(getenv("F367R5_MISSING_STORE"))ic.ic_channels[1].ic_flags=0;rc=store_value(argv[2]);fprintf(stderr,"REAL_SYSFS_STORE value=%s result=%ld reason=%s\n",argv[2],rc,reject_reason);return rc<0?1:0;}return 2;
 }
 reset();matured();CHECK(store_value("PREPARE52\n")==-EBUSY&&!strcmp(reject_reason,"prepare-target52-not-dfs")&&!stops);
 reset();memcpy(active_before,ic.ic_chan_active,32);deadline=f367_quarantine_deadline_ns;CHECK(!call_profile("publish")&&published==1);CHECK(!memcmp(active_before,ic.ic_chan_active,32)&&f367_quarantine_deadline_ns==deadline);
 CHECK((ic.ic_channels[1].ic_flags&(IEEE80211_CHAN_DFS|IEEE80211_CHAN_PASSIVE))==(IEEE80211_CHAN_DFS|IEEE80211_CHAN_PASSIVE));CHECK(!ic.ic_channels[0].ic_flags&&!ic.ic_channels[2].ic_flags&&!stops);
 CHECK(call_profile("publish")&&published==1);CHECK(!call_profile("check"));CHECK(store_value("PREPARE52\n")==-EBUSY&&!stops);
 matured();CHECK(store_value("PREPARE52\n")==10&&stops==1&&f367_transition_prepared);CHECK(store_value("PREPARE52 extra\n")==-EINVAL&&!strcmp(reject_reason,"unknown-command"));
 reset();ic.ic_chan_active[52/8]=0;CHECK(call_profile("publish")&&!published&&!claimed);CHECK(store_value("PREPARE52\n")==-EBUSY&&!strcmp(reject_reason,"prepare-target52-inactive-or-missing"));
 reset();qdrv_radar_first_call=false;CHECK(call_profile("publish")&&!published);
 reset();ic.ic_country_code=826;CHECK(call_profile("publish")&&!published);
 reset();fail_ioctl=1;CHECK(call_profile("publish")&&published==1&&claimed&&!ic.ic_channels[1].ic_flags);
 reset();alter_active=1;CHECK(call_profile("publish")&&published==1);
 reset();CHECK(!call_profile("publish"));qdrv_radar_first_call=false;qdrv_radar_cb.enabled=true;matured();qdrv_f367_mark_radar();deadline=f367_nop_deadline_ns;
 CHECK(call_profile("publish")&&published==1&&f367_nop_deadline_ns==deadline);CHECK(store_value("PREPARE52\n")==-EBUSY&&!stops&&f367_nop_deadline_ns==deadline);
 reset();CHECK(!call_profile("publish"));matured();stop_fails=true;CHECK(store_value("PREPARE52\n")==-EIO&&!strcmp(reject_reason,"prepare-tx-off-unconfirmed"));
 printf("F367R5_OEM_REGULATORY_ROUTE_PASS checks=%u producer=actual lookup=actual readback=actual sysfs_store=actual parser=actual hardware=0\n",checks);return 0;
}
'''
def main():
 out=ROOT/'outputs/preflight'/('f367r5-regulatory-route-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for p in (SRC/'userspace').iterdir():shutil.copyfile(p,out/p.name)
 for name in ('f367_ap_policy.h','qdrv_f367_ap.inc','qdrv_f367_control.inc'):shutil.copyfile(SRC/'qdrv/qdrv'/name,out/name)
 peer=PEER.read_text();wlan=(SRC/'qdrv/qdrv/qdrv_wlan.c').read_text();params=wsl('cat',KERNEL+'/kernel/params.c');string=wsl('cat',KERNEL+'/lib/string.c')
 pre=old.PRE
 pre=pre.replace('#include <assert.h>','#define _GNU_SOURCE\n#include <assert.h>')
 pre=pre.replace('#define IEEE80211_CHAN_DFS 4','').replace('#define IEEE80211_CHAN_RADAR 8','#define IEEE80211_CHAN_RADAR 8')
 a=pre.index('struct kernel_param{');b=pre.index('static struct{struct ieee80211com*ic;',a)
 pre=pre[:a]+EXTRA+'\nstruct kernel_param;struct kernel_param_ops{int(*get)(char*,const struct kernel_param*);int(*set)(const char*,const struct kernel_param*);};struct kernel_param{const struct kernel_param_ops*ops;unsigned flags;};\nstatic struct ieee80211com ic;\n'+pre[b:]
 pre=pre.replace(extract(pre,'ieee80211_find_channel_by_ieee'),'').replace(extract(pre,'sysfs_streq'),extract(string,'sysfs_streq'))
 source='\n'.join(extract(peer,n) for n in ('find11gchannel','findchannel','ieee80211_find_channel_by_ieee','ieee80211_subioctl_set_chan_dfs_required','ieee80211_ioctl_getchanlist','ieee80211_ioctl_getchaninfo'))+'\n'+extract(wlan,'qdrv_wlan_80211_mark_dfs')
 dispatch='case SIOCDEV_SUBIO_SET_MARK_DFS_CHAN:\n\t\tretval = ieee80211_subioctl_set_chan_dfs_required(dev, iwr->u.data.pointer, iwr->u.data.length);\n\t\tbreak;'
 assert dispatch in peer
 source+='\nstatic int dispatch_regulatory(struct net_device*dev,struct iwreq*iwr){int retval;switch(iwr->u.data.flags){'+dispatch+'default:return -EINVAL;}return retval;}\n'
 pre=pre.replace('#include "qdrv_f367_ap.inc"',source+'\n#include "qdrv_f367_ap.inc"')
 pre=pre[:pre.index('static void qdrv_radar_detected(struct ieee80211com*p')]+'''static void qdrv_radar_detected(struct ieee80211com*p,u8 escape){(void)p;(void)escape;software_dispatches++;}\n'''
 pivot=IO.index('static int published,')
 code=pre+IO[:pivot]+extract(params,'param_attr_store')+'\n'+IO[pivot:]
 (out/'route.c').write_bytes(code.encode())
 (out/'run.sh').write_bytes(('set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-const-variable -Wno-unused-variable -Wno-unused-parameter -Wno-sign-compare '+linux(out/'route.c')+' -o '+linux(out/'route')+'\n'+linux(out/'route')+'\n').encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 helper_proof=[]
 if not run.returncode:
  overlay=ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay'
  (out/'stage').write_bytes(b'#!/bin/sh\n[ "$1" != purpose ] || exit 77\nexit 0\n')
  for name,action in [('snapshot','snapshot'),('profile','check')]:
   (out/name).write_bytes(('#!/bin/sh\nexec "'+linux(out/'route')+'" '+action+'\n').encode())
  script='''#!/bin/bash
set -eu
export OM_F367_STATE="$fixture"
mkdir -p "$fixture";touch "$fixture/bootstrap-ready" "$fixture/control"
export OM_F367_KERNEL_CONTROL="$fixture/control"
export OM_F367_STAGE="$testdir/stage" OM_F367_STATUS="$testdir/snapshot" OM_F367_PROFILE="$testdir/profile"
export OM_F367_COMMON="$overlay/usr/libexec/openmitrastar/f367-shell-common"
# The sole replaced shell operation is the write transport. Its bytes and
# return status pass through the actual kernel sysfs parser and handler.
printf() {
 if [ "$1" = 'PREPARE52\\n' ] || [ "$1" = 'ABORT\\n' ]; then
  local value
  value=$(builtin printf "$@";builtin printf x);value=${value%x}
  "$testdir/route" store "$value"
 else builtin printf "$@";fi
}
source "$overlay/usr/sbin/om-f367-control" enter-dfs
'''
  (out/'helper-route.sh').write_bytes(script.encode())
  wsl('chmod','755',linux(out/'stage'),linux(out/'snapshot'),linux(out/'profile'))
  for label,environment in [('classified',[]),('classification-absent',['F367R5_MISSING=1']),('kernel-rejection',['F367R5_MISSING_STORE=1'])]:
   args=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','env','fixture='+linux(out/label),'testdir='+linux(out),'overlay='+linux(overlay),*environment,'bash',linux(out/'helper-route.sh')]
   r=subprocess.run(args,capture_output=True,text=True)
   expected={'classified':'reason=cac-phase','classification-absent':'reason=target52-regulatory-readback','kernel-rejection':'reason=prepare52'}[label]
   passed=r.returncode==1 and expected in r.stdout
   if label=='classified':passed=passed and 'result=10' in r.stderr
   if label=='classification-absent':passed=passed and 'REAL_SYSFS_STORE value=PREPARE52' not in r.stderr
   if label=='kernel-rejection':passed=passed and 'reason=prepare-target52-not-dfs' in r.stderr
   helper_proof.append(dict(case=label,passed=passed,stdout=r.stdout,stderr=r.stderr,exit_code=r.returncode))
  if not all(r['passed'] for r in helper_proof):run.returncode=1
 result=dict(schema='openmitrastar.f367r5-regulatory-route-test/v1',status='PASS_ACTUAL_OEM_REGULATORY_SYSFS_ROUTE' if not run.returncode else 'FAIL',stdout=run.stdout,stderr=run.stderr[-6000:],helper_route=helper_proof,source_pins={str(p):sha(p) for p in [Path(__file__),PEER,SRC/'qdrv/qdrv/qdrv_wlan.c',SRC/'qdrv/qdrv/qdrv_f367_control.inc',ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay/usr/sbin/om-f367-control',ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay/usr/libexec/openmitrastar/f367-shell-common',*list((SRC/'userspace').iterdir())]},kernel_params_sha256=hashlib.sha256(params.encode()).hexdigest(),kernel_string_sha256=hashlib.sha256(string.encode()).hexdigest(),hardware_actions=False,fake_boundary='socket transport, user copy, filesystem claim and MMIO TX primitive; actual OEM dispatch case/producer/lookup/getters, qdrv handler, kernel sysfs store and parser execute; actual shell helper/common parser runs to PREPARE boundary with substituted write transport and stopped next phase')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
