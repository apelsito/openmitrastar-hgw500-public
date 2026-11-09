"""Execute OEM mode parsing/ifmedia and the actual R8 observer shell."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,subprocess
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
PEER=ROOT/'work/linux510-radio-port/quantenna/wlan'
GPL=ROOT/'work/sources/Quantenna-GPL'
CONTROL=ROOT/'versions/lyoko-foundation-6.11.7-f367r8-mode-contract/overlay/usr/sbin/om-f367-control'
COMMON=ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay/usr/libexec/openmitrastar/f367-shell-common'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
PRE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
typedef unsigned int u_int;typedef unsigned long u_long;
#define IEEE80211_MODE_TURBO_STATIC_A IEEE80211_MODE_MAX
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_M_STA 1
#define IEEE80211_S_SCAN 1
#define CHIPID_DUAL 6
#define IEEE80211_11AC_ONLY 2
#define IEEE80211_11N_ONLY 1
#define IEEE80211_FIXED_RATE_NONE -1
#define SWFEAT_ID_VHT 1
#define SIOCSIFMEDIA 1
#define SIOCGIFMEDIA 2
#define IEEE80211_DEFAULT_2_4_GHZ_CHANNEL 1
#define IEEE80211_DEFAULT_5_GHZ_CHANNEL 36
#define IEEE80211_CSW_REASON_CONFIG 1
#define IEEE80211_PARAM_FIXED_TX_RATE 1
#define IEEE80211_PARAM_SET_MUC_BW 2
#define IEEE80211_PARAM_PHY_MODE 3
#define IEEE80211_PARAM_TX_AMSDU 4
#define IEEE80211_PARAM_AGGREGATION 5
#define IEEE80211_PARAM_RADAR_BW 235
#define IS_UP_AUTO(p) 0
#define IEEE80211_IS_CHAN_2GHZ(p) 0
#define IEEE80211_IS_CHAN_5GHZ(p) 1
#define IEEE80211_IS_CHAN_VHT80_EDGEPLUS(p) 1
#define IEEE80211_IS_CHAN_VHT80_CNTRPLUS(p) 0
#define IEEE80211_IS_CHAN_VHT80_CNTRMINUS(p) 0
#define IEEE80211_IS_CHAN_VHT80_EDGEMINUS(p) 0
#define KERN_INFO ""
#define printk(...) do{}while(0)
#define LIST_FOREACH(p,h,m) for((p)=(h)->first;(p);(p)=(p)->next)
struct net_device{int unused;};struct ifreq{int ifr_media;};struct ifmediareq;
struct ifmedia_entry{int ifm_media;struct ifmedia_entry*next;};
struct ifmedia{int ifm_mask,ifm_media;struct ifmedia_entry*ifm_cur;struct{struct ifmedia_entry*first;}ifm_list;int(*ifm_change)(void*);};
struct ieee80211_channel{int ic_ieee;};
struct ieee80211com{struct ifmedia ic_media;struct ieee80211_channel*ic_curchan,*ic_des_chan;int ic_rf_chipid,ic_opmode,ic_des_mode,ic_phymode,ic_curmode,ic_max_system_bw,ic_csw_reason,ic_radar_bw;void(*ic_set_channel)(struct ieee80211com*);};
struct ieee80211vap{struct ieee80211com*iv_ic;struct ifmedia iv_media;struct net_device*iv_dev;int iv_11ac_and_11n_flag,iv_opmode,iv_fixed_rate;};
struct iw_point{void*pointer;unsigned short length,flags;};struct iw_freq{int m;short e;};struct iw_request_info{int unused;};
static struct ieee80211com ic;static struct ieee80211vap vap;static struct net_device dev;static struct ieee80211_channel ch36={36};static struct ifmedia_entry entry20,entry80;static int bw_sent,phy_sent,params,feature=1,consistency;
static void*fixture_priv(void){return &vap;}
#define netdev_priv(p) fixture_priv()
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)-1)
static int copy_from_user(void*d,const void*s,size_t n){memcpy(d,s,n);return 0;}
static int ieee80211_media2mcs(int value){(void)value;assert(0);return 0;}
static int ieee80211_media2rate(int value){(void)value;assert(0);return 0;}
static int checkrate(struct ieee80211com*c,int m,int r){(void)c;(void)m;(void)r;assert(0);return 0;}
static int ieee80211_swfeat_is_supported(int f,int verbose){(void)f;(void)verbose;return feature;}
static int ieee80211_check_mode_consistency(struct ieee80211com*c,int m,struct ieee80211_channel*ch){(void)c;(void)m;(void)ch;return consistency;}
static void update_sta_profile(char*s,struct ieee80211vap*v){(void)s;(void)v;assert(0);}
static void ieee80211_wireless_reassoc(struct ieee80211vap*v,int a,int b){(void)v;(void)a;(void)b;}
static void ieee80211_new_state(struct ieee80211vap*v,int a,int b){(void)v;(void)a;(void)b;assert(0);}
static struct ieee80211_channel*findchannel_any(struct ieee80211com*c,int a,int b){(void)c;(void)a;(void)b;assert(0);return 0;}
static struct ieee80211_channel*find_alt_primary_chan_11ac80(struct ieee80211com*c,char*s){(void)c;(void)s;return &ch36;}
static void ieee80211_update_bw_capa(struct ieee80211vap*v,int bw){(void)v;assert(bw==20);}
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int param,int value,void*d,int n){(void)v;(void)d;(void)n;params++;if(param==IEEE80211_PARAM_SET_MUC_BW)bw_sent=value;if(param==IEEE80211_PARAM_PHY_MODE)phy_sent=value;}
static void ieee80211_reset_erp(struct ieee80211com*c,int m){(void)c;(void)m;}
static void ieee80211_start_obss_scan_timer(struct ieee80211vap*v){(void)v;}
'''
TEST=r'''
static void reset(void){memset(&ic,0,sizeof(ic));memset(&vap,0,sizeof(vap));entry20.ifm_media=IFM_MAKEMODE(11)|IFM_AUTO;entry20.next=&entry80;entry80.ifm_media=IFM_MAKEMODE(13)|IFM_AUTO;entry80.next=NULL;
 vap.iv_ic=&ic;vap.iv_dev=&dev;vap.iv_opmode=ic.ic_opmode=6;vap.iv_fixed_rate=-1;vap.iv_media.ifm_list.first=&entry20;vap.iv_media.ifm_cur=&entry80;vap.iv_media.ifm_media=entry80.ifm_media;vap.iv_media.ifm_change=ieee80211_media_change;ic.ic_media=vap.iv_media;ic.ic_curchan=&ch36;ic.ic_des_mode=ic.ic_phymode=ic.ic_curmode=13;feature=1;consistency=0;bw_sent=phy_sent=params=0;}
static int mode(const char*s){struct iw_point request={.pointer=(void*)s,.length=strlen(s)+1};return ieee80211_ioctl_setmode(&dev,NULL,&request,NULL);}
static const char*readmode(void){static char out[40],user[40];struct iw_point request={.pointer=user};memset(out,0,sizeof(out));assert(!ieee80211_ioctl_getmode(&dev,NULL,&request,out));return out;}
int main(int argc,char**argv){int checks=0;
#define CHECK(x) do{checks++;assert(x);}while(0)
 reset();
 if(argc==3&&!strcmp(argv[1],"mode")){int rc=mode(argv[2]);if(rc)return 1;printf("%d %d %s\n",ic.ic_phymode,bw_sent,readmode());return 0;}
 if(argc==3&&!strcmp(argv[1],"filter")){apply_filter(atoi(argv[2]));printf("%d\n",ic.ic_radar_bw);return 0;}
 if(argc==3&&!strcmp(argv[1],"freq")){printf("%d\n",parse_frequency(atoi(argv[2]),0));return 0;}
 CHECK(ieee80211_convert_mode("11ac20")==-1);CHECK(mode("11ac20")==-EINVAL&&params==0&&ic.ic_phymode==13);
 CHECK(ieee80211_convert_mode("11ac")==11&&ieee80211_convert_mode("11AC")==11);CHECK(!mode("11ac"));CHECK(ic.ic_phymode==11&&ic.ic_des_mode==11&&ic.ic_curmode==11&&bw_sent==20&&phy_sent==11);CHECK(!strcmp(readmode(),"11ac20"));
 CHECK(ieee80211_get_bw_from_phymode(11)==20);apply_filter(20);CHECK(ic.ic_radar_bw==20);CHECK(parse_frequency(52,0)==52&&parse_frequency(52,2)==-EINVAL);
 reset();feature=0;CHECK(mode("11ac")==-EOPNOTSUPP&&params==0);reset();vap.iv_media.ifm_list.first=&entry80;CHECK(mode("11ac")!=0&&ic.ic_phymode==13);
 printf("F367R8_OEM_MODE_CONTRACT_PASS checks=%d parser=actual ifmedia_set=actual media_change=actual bandwidth_mapping=actual getter=actual next_filter_parser=actual next_channel_number_parser=actual\n",checks);return 0;}
'''
FIXTURE=r'''
import json,os,subprocess,sys
from pathlib import Path
root=Path(os.environ['FIXTURE']);state=root/'data.json';kind=os.environ['CASE'];data=json.loads(state.read_text());action=sys.argv[1:]
with (root/'trace.jsonl').open('a') as f:f.write(json.dumps(action)+'\n')
def save():state.write_text(json.dumps(data))
if action[0]=='status':
 if data.get('pending'):
  data['monotonic_ms']+=1000
  elapsed=data['monotonic_ms']-data['requested_ms']
  if (kind=='delayed' and elapsed>=2000) or (kind=='late' and elapsed>5000) or kind=='fault':data['channel']=52
  if kind=='fault':data['control_fault']=1
 save();print(json.dumps(data,separators=(',',':')));sys.exit(0)
if action[0]=='stage':sys.exit(0)
if action[0]=='profile':print('OMF367_PROFILE_READBACK channel=52 active=1 dfs=1');sys.exit(0)
if action[0]=='iwpriv':
 cmd=action[2]
 if cmd in ('doth','tpc'):data[cmd]=int(action[3]);save();sys.exit(0)
 if cmd=='mode':
  if kind=='mode-reject':sys.exit(7)
  r=subprocess.run([os.environ['OEM'],'mode',action[3]],capture_output=True,text=True)
  if r.returncode:sys.exit(r.returncode)
  mode,bw,label=r.stdout.strip().split();data['phymode']=int(mode);data['mode_label']=label;save();sys.exit(0)
 if cmd=='radar_bw':
  r=subprocess.run([os.environ['OEM'],'filter',action[3]],capture_output=True,text=True,check=True);data['filter_bw']=int(r.stdout);save();sys.exit(0)
 if cmd=='get_region':print('wifi0 get_region:21317');sys.exit(0)
 if cmd=='get_mode':print('wifi0 get_mode:'+data['mode_label']);sys.exit(0)
if action[0]=='iwconfig':
 r=subprocess.run([os.environ['OEM'],'freq',action[3]],capture_output=True,text=True,check=True);assert int(r.stdout)==52
 data['pending']=True;data['requested_ms']=data['monotonic_ms'];save();sys.exit(0)
raise RuntimeError(action)
'''
def main():
 out=ROOT/'outputs/preflight'/('f367r8-mode-contract-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 wireless=(PEER/'ieee80211_wireless.c').read_text();core=(PEER/'ieee80211.c').read_text();media=(PEER/'if_media.c').read_text();header=(GPL/'drivers/include/kernel/net80211/if_media.h').read_text();modes=(GPL/'drivers/include/shared/net80211/_ieee80211.h').read_text();comm=(GPL/'include/qtn/lhost_muc_comm.h').read_text()
 enum=modes[modes.index('enum ieee80211_phymode {'):];enum=enum[:enum.index('};')+2]
 functions=[extract(wireless,'ieee80211_convert_mode'),extract(core,'media2mode'),extract(core,'ieee80211_media_change'),extract(media,'ifmedia_match')]
 ioctl=extract(media,'ifmedia_ioctl');ioctl=ioctl[:ioctl.index('case  SIOCGIFMEDIA:')]+'default:return -EINVAL;\n}\nreturn error;\n}'
 functions+=[ioctl,extract(wireless,'ieee80211_get_bw_from_phymode'),extract(wireless,'ieee80211_update_bw_from_phymode'),extract(core,'ieee80211_setmode'),extract(wireless,'ieee80211_ioctl_setmode'),extract(wireless,'ieee80211_ioctl_getmode')]
 required=set(re.findall(r'\bIFM_[A-Z0-9_]+','\n'.join(functions)+TEST));defs={}
 for match in re.finditer(r'^#define[ \t]+(IFM_[A-Z0-9_]+)[^\n]*',header.replace('\\\n',' '),re.M):defs[match.group(1)]=match.group(0)
 while True:
  expanded=required|set(re.findall(r'\bIFM_[A-Z0-9_]+','\n'.join(defs[n] for n in required)))
  if expanded==required:break
  required=expanded
 bw=re.search(r'enum \{\s*BW_INVALID = 0,.*?\};',comm,re.S).group(0)
 freq=extract(wireless,'ieee80211_ioctl_siwfreq');freq=freq[freq.index('if (freq->e > 1)'):freq.index('if (i != 0)')]
 freq=freq.replace('(ic->ic_mhz2ieee)(ic, freq->m / 100000, 0)','0 /* GHz wire form is outside this fixed channel-number request */')
 filter_case='case IEEE80211_PARAM_RADAR_BW:\n\t\tic->ic_radar_bw = value;\n\t\tbreak;';assert filter_case in wireless
 code=PRE+'\n'+enum+'\n'+bw+'\n'+'\n'.join(defs[n] for n in sorted(required))+'\n'+'\n'.join(functions)+'\nstatic int parse_frequency(int m,int e){struct iw_freq f={m,e};struct iw_freq*freq=&f;int i;'+freq+'return i;}\nstatic void apply_filter(int value){struct ieee80211com*target=&ic;\n#define ic target\n switch(IEEE80211_PARAM_RADAR_BW){'+filter_case+'}\n#undef ic\n}\n'+TEST
 (out/'oem.c').write_bytes(code.encode())
 # The AP UP/RUN route queues a timer; only its completion updates current channel.
 from prepare_f344_csa_policy import closing
 start=wireless.index('int ieee80211_enter_csa(')
 csa=wireless[start:closing(wireless,start)+1];finish=extract(wireless,'ieee80211_finish_csa');freqfull=extract(wireless,'ieee80211_ioctl_siwfreq')
 assert 'ieee80211_enter_csa(ic, ic->ic_des_chan, NULL' in freqfull and 'mod_timer(&ic->ic_timer_csa' in csa and 'ic->ic_curchan =' not in csa
 assert 'ic->ic_curchan = ic->ic_csa_chan;' in finish and 'ic->ic_set_channel(ic);' in finish
 (out/'csa-source.txt').write_text(csa+'\n'+finish)
 script='set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-function -Wno-unused-variable -Wno-unused-parameter -Wno-sign-compare -Wno-stringop-truncation '+linux(out/'oem.c')+' -o '+linux(out/'oem')+'\n'+linux(out/'oem')+'\n';(out/'run.sh').write_bytes(script.encode())
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e'];run=subprocess.run(cmd+['sh',linux(out/'run.sh')],capture_output=True,text=True)
 cases=[]
 if not run.returncode:
  (out/'fixture.py').write_bytes(FIXTURE.encode());bindir=out/'bin';bindir.mkdir()
  for name,action in [('status','status'),('stage','stage'),('profile','profile'),('iwpriv','iwpriv'),('iwconfig','iwconfig')]:
   (bindir/name).write_bytes(('#!/bin/sh\nexec python3 '+linux(out/'fixture.py')+' '+action+' "$@"\n').encode())
  (bindir/'sleep').write_bytes(b'#!/bin/sh\nexit 0\n')
  subprocess.run(cmd+['chmod','-R','755',linux(bindir)],check=True)
  for name in ('delayed','timeout','late','fault','mode-reject'):
   folder=out/name;folder.mkdir();(folder/'bootstrap-ready').touch();(folder/'control').touch()
   row=dict(schema='openmitrastar.f367-state/v1',kernel_state_present=1,provider_present=1,channel=36,filter_bw=80,phymode=13,region_es=1,nop_active=0,quarantine_active=0,control_fault=0,tx_fault_latched=0,monotonic_ms=1000,doth=0,tpc=0)
   (folder/'data.json').write_text(json.dumps(row))
   env=['FIXTURE='+linux(folder),'CASE='+name,'OEM='+linux(out/'oem'),'OM_F367_STATE='+linux(folder),'OM_F367_KERNEL_CONTROL='+linux(folder/'control'),'OM_F367_COMMON='+linux(COMMON)]
   env += ['OM_F367_'+key+'='+linux(bindir/value) for key,value in [('STATUS','status'),('STAGE','stage'),('PROFILE','profile'),('IWPRIV','iwpriv'),('IWCONFIG','iwconfig')]]
   invocation='export PATH='+linux(bindir)+':$PATH\nexec sh '+linux(CONTROL)+' enter-dfs\n';(folder/'run.sh').write_bytes(invocation.encode())
   r=subprocess.run(cmd+['env',*env,'sh',linux(folder/'run.sh')],capture_output=True,text=True)
   trace=[json.loads(s) for s in (folder/'trace.jsonl').read_text().splitlines()]
   count=lambda op:sum(len(x)>2 and x[0]=='iwpriv' and x[2]==op for x in trace)
   channels=sum(x[0]=='iwconfig' for x in trace)
   passed=count('mode')==1 and count('radar_bw')==(0 if name=='mode-reject' else 1) and channels==(0 if name=='mode-reject' else 1)
   expected='result=pass' if name=='delayed' else 'result=fault' if name=='fault' else 'exit_code=7' if name=='mode-reject' else 'result=timeout'
   passed=passed and expected in r.stdout and ((r.returncode==0)==(name=='delayed'))
   if name!='delayed':passed=passed and 'OMF367_ENTER_DFS' not in r.stdout and 'result=pass' not in r.stdout
   cases.append(dict(case=name,passed=passed,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,mode_writes=count('mode'),filter_writes=count('radar_bw'),channel_writes=channels))
 result=dict(schema='openmitrastar.f367r8-mode-contract-test/v1',status='PASS_OEM_MODE_PARSER_AND_BOUNDED_CSA_OBSERVER' if not run.returncode and cases and all(x['passed'] for x in cases) else 'FAIL',parser_stdout=run.stdout,parser_stderr=run.stderr[-5000:],helper_cases=cases,source_pins={str(p):sha(p) for p in [Path(__file__),CONTROL,COMMON,PEER/'ieee80211_wireless.c',PEER/'ieee80211.c',PEER/'if_media.c',GPL/'drivers/include/kernel/net80211/if_media.h',GPL/'drivers/include/shared/net80211/_ieee80211.h',GPL/'include/qtn/lhost_muc_comm.h']},hardware_actions=False,coverage='Real mode parser/setmode/ifmedia SET branch/media-change/BW mapping/getter and integer filter/channel parsers; board capability and MuC programming are boundaries. CSA scheduling/completion source contract plus actual shell asynchronous observer. No RF/CAC execution claimed.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2));return 0 if result['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
