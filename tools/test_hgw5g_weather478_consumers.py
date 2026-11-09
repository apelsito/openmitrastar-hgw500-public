"""Versioned actual AP start/pick weather478 policy fixture and WEXT cases.

AP source bodies are compiled whole with explicit fake channel/radio callbacks.
Shim is a harness entry, never presented as a real driver getter or kernel path.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
from prepare_tqe_bounded_admission_prototype import function


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    original=Path(__file__).with_name('test_hgw5g_dfs467_refreshed_pick.py');text=original.read_text()
    old="query=extract(s,s.index('int om_ieee80211_dfs_channel_available('))"
    assert old in text
    # Harness only: actual ap_start -> wrapper -> ap_pick, with policy from IC.
    query='''int om_ieee80211_dfs_channel_available(struct ieee80211com *ic)
{struct ieee80211_scan_state *ss=ic->ic_scan;
ss->ss_ops->scan_start(ss,ss->ss_vap);
if(!ss->ss_last)return -95;
return ieee80211_scan_pickchannel(ic,0x130000)?1:-95;}
'''
    text=text.replace(old,'query='+repr(query))
    kernel=(a.candidate/'source/wlan/openmitrastar_chanset_kernel.inc').read_text()
    allowed=function(kernel,'int om_chanset_kernel_allowed(')
    predicates='''
#define IEEE80211_MODE_11B 2
#define IEEE80211_MODE_11NG 8
#define IEEE80211_MODE_11NG_HT40PM 9
'''+allowed+'''
static int om_chanset_kernel_active(struct ieee80211com *ic){(void)ic;return 0;}
static struct ieee80211_channel *om_chanset_kernel_pick(struct ieee80211com *ic){(void)ic;assert(0);return NULL;}
'''
    # Actual allowed predicate plus trap: admitted5GHz fixture modes never
    # enter the separate HT24 typed picker. Active is irrelevant after false.
    needle="'''+metric+'\\n'+startfn+'\\n'+pickfn"
    assert needle in text
    text=text.replace(needle,"'''+"+repr(predicates)+"+metric+'\\n'+startfn+'\\n'+pickfn",1)
    text=text.replace('int ic_phymode,ic_des_mode,ic_nchans,','int om_weather_cac_enabled,ic_phymode,ic_des_mode,ic_nchans,',1)
    text=text.replace('for(unsigned mode=0;mode<7;mode++)for(unsigned states=0;states<4096;states++){',
                      'for(unsigned enabled=0;enabled<2;enabled++)for(unsigned mode=0;mode<7;mode++)for(unsigned states=0;states<4096;states++){',1)
    text=text.replace('ic.ic_phymode=modes[mode];','ic.om_weather_cac_enabled=enabled;ic.ic_phymode=modes[mode];',1)
    text=text.replace('if((bits&1)&&!(bits&4)&&!(bits&8))expect=true;',
                      'if(!(bits&4)&&(enabled||!(bits&8)))expect=true;',1)
    # Missing-mode refusal belongs to DFS467; this harness tests only actual AP policy.
    begin=text.index('for(unsigned mode=0;mode<16;mode++)for(unsigned missing=0;missing<6;missing++)')
    end=text.index('assert(cases==28672UL)',begin)
    text=text[:begin]+text[end:]
    text=text.replace('assert(cases==28672UL)','assert(cases==57344UL)')
    text=text.replace('cases=28672,missing_mode_cases=96','cases=57344,missing_mode_cases=0')
    text=text.replace('PASS_ACTUAL_DFS467_QUERY_REFRESH_WHOLE_APSTART_AP_PICK_5GHZ_FIXTURE',
                      'PASS_ACTUAL_WEATHER478_WHOLE_APSTART_AP_PICK_POLICY_FIXTURE')
    script=a.output/'adapted-weather-fixture-generator.py';script.write_text(text,encoding='utf-8',newline='\n')
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parent)
    r=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--compiler',str(a.compiler),'--output',str(a.output/'ap-policy')],env=env,capture_output=True)
    (a.output/'run.stdout').write_bytes(r.stdout);(a.output/'run.stderr').write_bytes(r.stderr)
    assert r.returncode==0,r.stderr.decode(errors='replace')
    # Compile the actual478 set/get fragments independently for scalar/return contract.
    wire=(a.candidate/'source/wlan/ieee80211_wireless.c').read_text()
    setstart=wire.index('\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:');setend=wire.index('\n\tcase ',setstart+1)
    getstart=wire.index('\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:',setend);getend=wire.index('\n\tcase ',getstart+1)
    setcase=wire[setstart:setend];getcase=wire[getstart:getend]
    c='''#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define OM_OEM_PARAM_WEATHER_CAC_ENABLE 478
#define WRITE_ONCE(x,v) ((x)=(v))
#define READ_ONCE(x) (x)
struct ieee80211com {uint32_t prefix;unsigned char om_weather_cac_enabled;uint32_t suffix;};
static int setter(struct ieee80211com *ic,int param,int value){switch(param){'''+setcase+'''
default:return -1;}}
static int getter(struct ieee80211com *ic,int *param){switch(param[0]&65535){'''+getcase+'''
default:return -1;}}
int main(void){struct ieee80211com ic={123,0,456};unsigned cases=0;
uint32_t values[]={0,1,2,255,256,65535,65536,0x7fffffff,0x80000000,0xffffffff};
for(unsigned i=0;i<10;i++)for(unsigned tag=0;tag<65536;tag++){
assert(!setter(&ic,478,(int)values[i]));assert(ic.om_weather_cac_enabled==!!values[i]);
int value=(int)(tag<<16|478);assert(!getter(&ic,&value));assert(value==!!values[i]);
assert(ic.prefix==123&&ic.suffix==456);cases++;}
printf("%u\\n",cases);return 0;}
'''
    fixture=a.output/'actual-wext478.c';fixture.write_text(c,encoding='utf-8',newline='\n')
    r=subprocess.run([str(a.compiler),'-O2','-std=c11',str(fixture),'-o',str(a.output/'wext-fixture.exe')],capture_output=True)
    (a.output/'wext.compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr
    r=subprocess.run([str(a.output/'wext-fixture.exe')],capture_output=True);assert not r.returncode,r.stderr
    scalar_cases=int(r.stdout)
    ap=json.loads((a.output/'ap-policy/result.json').read_text())
    proof={'status':'PASS_WEATHER478_ACTUAL_AP_POLICY_AND_WEXT_SOURCE_CONSUMERS',
           'hardware_accessed':False,'firmware_eligible':False,'ap_policy_cases':ap['cases'],
           'wext_cases':scalar_cases,'source_fixture_sha256':sha(fixture),
           'pins':{str(path):sha(path)for path in[Path(__file__),original,script,a.candidate/'source/wlan/ieee80211_wireless.c',a.candidate/'source/wlan/ieee80211_scan_ap.c']},
           'limits':'Whole actual AP policy bodies at20MHz with fake channel/radio helpers; WEXT actual cases; no regulatory/CAC/RF/hardware/physical qualification.'}
    (a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
