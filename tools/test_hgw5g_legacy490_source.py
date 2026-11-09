"""Actualstateful490Cfunction fixture with wire/callback ordering anderrors."""
import argparse
import json
from pathlib import Path
import subprocess

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=(a.candidate/'source/wlan/ieee80211_wireless.c').read_text();start=text.index('static int om_fix_legacy_rate(');end=text.index('\nstatic int\nieee80211_ioctl_setparam(',start);helper=text[start:end]
 fixture='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint32_t u32;typedef uint16_t u16;
#define EINVAL 22
#define CHIPID_DUAL 2
#define IEEE80211_M_STA 1
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_PARAM_FIXED_TX_RATE 62
#define IEEE80211_CSW_REASON_CONFIG 4
struct profile{int vht;};struct ieee80211com{int om_legacy_rate_fixed,om_legacy_rate_saved_mode;u16 ic_curmode,ic_des_mode;int ic_phymode,ic_rf_chipid,ic_opmode;u32 ic_csw_reason;void(*ic_set_channel)(struct ieee80211com*);};
struct ieee80211vap{struct ieee80211com*iv_ic;int iv_opmode;struct profile iv_5ghz_prof,iv_2_4ghz_prof;};
static unsigned step;static u32 sent;static int sendid;
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int id,int value,void*d,int len){assert(step==0&&d==NULL&&len==0);step=1;sent=value;sendid=id;}
static void ieee80211_setmode(struct ieee80211com*ic,int mode){assert(step==1&&ic->ic_phymode==mode&&ic->ic_des_mode==mode);step=2;ic->ic_curmode=mode;}
static void ieee80211_wireless_reassoc(struct ieee80211vap*v,int x,int y){assert(step==2&&x==0&&y==1&&v->iv_ic->ic_csw_reason==4);step=3;}
static void channel(struct ieee80211com*ic){assert(step==3);step=4;}
'''+helper+'''int main(void){struct ieee80211com ic,before;struct ieee80211vap v;unsigned current,phy,value,rf,mode;int rc;
for(current=0;current<15;current++)for(phy=0;phy<15;phy++)for(value=0;value<13;value++)for(rf=0;rf<3;rf++)for(mode=0;mode<2;mode++){
memset(&ic,0,sizeof(ic));ic.ic_curmode=current;ic.ic_phymode=phy;ic.ic_rf_chipid=rf;ic.ic_opmode=1;ic.ic_set_channel=channel;v.iv_ic=&ic;v.iv_opmode=mode?6:1;v.iv_5ghz_prof.vht=7;v.iv_2_4ghz_prof.vht=9;step=0;rc=om_fix_legacy_rate(&v,value);assert(rc==0&&sendid==62&&sent==(0x7f000000U|value|(value<<8)|(value<<16)));assert(ic.om_legacy_rate_fixed==1&&ic.om_legacy_rate_saved_mode==(int)current);assert(step==((current>=1&&current<=6)?1:(mode?4:3)));
step=0;rc=om_fix_legacy_rate(&v,-1);assert(rc==0&&sent==255&&ic.om_legacy_rate_fixed==0&&ic.om_legacy_rate_saved_mode==0);assert(step==((current>=1&&current<=6)?1:(mode?4:3)));}
memset(&ic,0,sizeof(ic));ic.ic_set_channel=channel;v.iv_ic=&ic;before=ic;step=0;assert(om_fix_legacy_rate(&v,13)==-22&&!memcmp(&ic,&before,sizeof(ic))&&step==0);assert(om_fix_legacy_rate(&v,-1)==-22&&!memcmp(&ic,&before,sizeof(ic))&&step==0);
ic.om_legacy_rate_fixed=1;ic.om_legacy_rate_saved_mode=11;v.iv_opmode=6;step=0;assert(om_fix_legacy_rate(&v,INT32_MIN)==0&&sent==255&&step==4);return0;}
'''.replace('return0;','return 0;')
 a.output.mkdir(parents=True,exist_ok=False);f=a.output/'fixture.c';f.write_text(fixture);r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert r.returncode==0,r.stderr
 result=dict(status='PASS_ACTUAL490_STATE_WIRE_MODE_CALLBACK_HOST_FIXTURE',hardware_accessed=False,firmware_eligible=False,set_restore_sequences=17550,error_cases=3,original_wire_value_preserved=True,order='wire62 thenmode/setmode thenCSA4/reassoc thenHOSTAPchannel',limits='Hostfakecallbacks; fullARCABI/allmoduleclosure andOEMcallbackfunctionsemantics stillpending')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
