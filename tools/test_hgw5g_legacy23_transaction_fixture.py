"""Execute actual op490 helper versus an independent transaction reference.

Exhaust every u16 current mode and 13 admitted rates, verify wire/callback
order, explicit target selection, saved-state retention, restore-any-negative,
both VAP profiles and invalid no-mutation exits. Host callbacks are fakes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_wireless.c';text=source.read_text();start=text.index('static int om_fix_legacy_rate(');end=text.index('\nstatic int\nieee80211_ioctl_setparam(',start);helper=text[start:end]
 c=r'''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <limits.h>
typedef uint32_t u32;typedef uint16_t u16;
#define EINVAL 22
#define CHIPID_DUAL 2
#define IEEE80211_M_STA 1
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_PARAM_FIXED_TX_RATE 62
#define IEEE80211_CSW_REASON_CONFIG 4
struct profile {int vht;};
struct ieee80211com {int om_legacy_rate_fixed,om_legacy_rate_saved_mode;u16 ic_curmode,ic_des_mode;int ic_phymode,ic_rf_chipid,ic_opmode;u32 ic_csw_reason;void(*ic_set_channel)(struct ieee80211com*);};
struct ieee80211vap {struct ieee80211com*iv_ic;int iv_opmode;struct profile iv_5ghz_prof,iv_2_4ghz_prof;};
static unsigned step,wirecalls,modecalls,reassoc_calls,channelcalls;static u32 sent;static int expected_target;
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int id,int value,void*d,int len){assert(step==0&&id==62&&d==NULL&&len==0);step=1;sent=(u32)value;wirecalls++;}
static void ieee80211_setmode(struct ieee80211com*ic,int mode){assert(step==1&&mode==expected_target&&ic->ic_phymode==mode&&ic->ic_des_mode==(u16)mode);step=2;ic->ic_curmode=(u16)mode;modecalls++;}
static void ieee80211_wireless_reassoc(struct ieee80211vap*v,int x,int y){assert(step==2&&x==0&&y==1&&v->iv_ic->ic_csw_reason==4);step=3;reassoc_calls++;}
static void channel(struct ieee80211com*ic){assert(step==3);step=4;channelcalls++;}
static int is5g(int p){return p==1||p==7||p==10||(p>=11&&p<=14);}
static void resetcalls(void){step=wirecalls=modecalls=reassoc_calls=channelcalls=0;sent=0xa5a5a5a5;}
'''+helper+r'''
static unsigned long operations;
static void verify(struct ieee80211vap*v,int value){
 struct ieee80211com before=*v->iv_ic,*ic=v->iv_ic;struct profile p5=v->iv_5ghz_prof,p2=v->iv_2_4ghz_prof;int target=-1,rc,error=0;u32 wantwire=255;int fixed=before.om_legacy_rate_fixed,saved=before.om_legacy_rate_saved_mode;
 if(value<0){if(!fixed)error=1;else{target=saved;fixed=0;saved=0;if(target>=1&&target<=6)target=-1;}}
 else if(value>12)error=1;
 else{wantwire=0x7f000000U|(u32)value|((u32)value<<8)|((u32)value<<16);if(before.ic_curmode>=1&&before.ic_curmode<=6)target=-1;else target=is5g(before.ic_phymode)?1:3;if(!fixed){saved=before.ic_curmode;fixed=1;}}
 expected_target=target;resetcalls();rc=om_fix_legacy_rate(v,value);operations++;
 if(error){assert(rc==-22&&step==0&&!wirecalls&&!memcmp(&before,ic,sizeof(before))&&!memcmp(&p5,&v->iv_5ghz_prof,sizeof(p5))&&!memcmp(&p2,&v->iv_2_4ghz_prof,sizeof(p2)));return;}
 assert(rc==0&&sent==wantwire&&wirecalls==1&&ic->om_legacy_rate_fixed==fixed&&ic->om_legacy_rate_saved_mode==saved);
 if(target==-1){assert(step==1&&!modecalls&&!reassoc_calls&&!channelcalls&&ic->ic_phymode==before.ic_phymode&&ic->ic_des_mode==before.ic_des_mode&&ic->ic_curmode==before.ic_curmode&&ic->ic_csw_reason==before.ic_csw_reason);}
 else{assert(modecalls==1&&reassoc_calls==1&&channelcalls==(v->iv_opmode==6)&&step==(v->iv_opmode==6?4U:3U));assert(ic->ic_curmode==(u16)target&&ic->ic_des_mode==(u16)target&&ic->ic_phymode==target&&ic->ic_csw_reason==4);if(before.ic_rf_chipid==2&&before.ic_opmode==1){if(is5g(before.ic_phymode))p5.vht=target>10;else p2.vht=target>10;}}
 assert(v->iv_5ghz_prof.vht==p5.vht&&v->iv_2_4ghz_prof.vht==p2.vht);
}
static void setup(struct ieee80211com*ic,struct ieee80211vap*v,unsigned cur,int phy,int rf,int mode,int op){memset(ic,0,sizeof(*ic));memset(v,0,sizeof(*v));ic->ic_curmode=(u16)cur;ic->ic_des_mode=0x4567;ic->ic_phymode=phy;ic->ic_rf_chipid=rf;ic->ic_opmode=op;ic->ic_csw_reason=0x89;ic->ic_set_channel=channel;v->iv_ic=ic;v->iv_opmode=mode;v->iv_5ghz_prof.vht=7;v->iv_2_4ghz_prof.vht=9;}
int main(void){struct ieee80211com ic;struct ieee80211vap v;unsigned cur,rate,phy,rf,mode,op;
 for(cur=0;cur<65536;cur++)for(rate=0;rate<13;rate++){setup(&ic,&v,cur,cur%15,cur%3,(cur&1)?6:1,(cur&2)?1:6);verify(&v,(int)rate);verify(&v,(int)((rate+1)%13));verify(&v,INT_MIN);verify(&v,-1);}
 for(cur=0;cur<15;cur++)for(phy=0;phy<15;phy++)for(rate=0;rate<13;rate++)for(rf=0;rf<3;rf++)for(mode=0;mode<2;mode++)for(op=0;op<2;op++){setup(&ic,&v,cur,phy,rf,mode?6:1,op?6:1);verify(&v,(int)rate);verify(&v,12);verify(&v,-2);verify(&v,INT_MAX);}
 assert(operations==3548272UL);return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);pins={str(source):sha(source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert r.returncode==0,(r.returncode,r.stderr)
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL490_FULL_TRANSACTION_REFERENCE_HOST_FIXTURE',hardware_accessed=False,firmware_eligible=False,operations=3548272,current_modes_exhausted=65536,rates_exhausted=13,profile_mode_cases=35100,source_sha256=pins[str(source)],helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),limits='Actual helper with independent reference and fake synchronous callbacks; no acceptance of physical rate/mode transition or callback success.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
