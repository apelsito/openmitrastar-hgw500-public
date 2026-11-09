"""Bound actual portinit fragments + exactOEMzero-init/AP/WEXT byte evidence."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from test_hgw5g_dfs467_refreshed_pick import extract
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pseudos(p):
 out=[]
 def visit(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k=='pseudocode'and isinstance(v,str):out.append(v)
    else:visit(v)
  elif isinstance(x,list):
   for v in x:visit(v)
 visit(json.loads(p.read_text()));assert out;return max(out,key=len)
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};paths={'oem_init':ROOT/'outputs/rea/weather478-oem-default-init-20261022T234600Z-r1/rea.json','oem_ap':ROOT/'outputs/rea/windows-oem-dfs467-scanap-pick-20261022T223500Z-r1/rea.json','oem_set':ROOT/'outputs/rea/oem-wlan-missingops-20261022T131900Z-setparam-r2/rea.json','oem_get':ROOT/'outputs/rea/oem-wlan-missingops-20261022T131900Z-getparam-r2/rea.json'};tx={k:pseudos(v)for k,v in paths.items()}
 init=tx['oem_init'];zero='(*(code *)&memset)(iVar4,0,0x8004);';assert zero in init and init.index(zero)<init.index('(*(code *)&ieee80211_ifattach)(iVar4);');assert '0xbf4'not in init
 assert "*(char *)(param_1 + 0xbf4) == '\\0'"in tx['oem_ap'];assert '*(bool *)(iVar23 + 0xbf4) = uVar20 != 0;'in tx['oem_set'];assert '*param_4 = (uint)*(byte *)(iVar8 + 0xbf4);'in tx['oem_get']
 source=a.candidate/'source/qdrv/qdrv_wlan.c';s=source.read_text();outer=extract(s,s.index('int qdrv_wlan_init('));inner=extract(s,s.index('static int qdrv_wlan_80211_init('));portzero='memset(qw, 0, sizeof(struct qdrv_wlan));';assignment='ic->om_weather_cac_enabled = 0;';assert portzero in outer and outer.index(portzero)<outer.index('qdrv_wlan_80211_init(&qw->ic');assert inner.count(assignment)==1 and inner.index(assignment)>inner.index('ieee80211_ifattach(ic);');assert s.count('om_weather_cac_enabled')==1
 abi=ROOT/'outputs/rea/weather478-all-abi-20261022T234000Z-r1/result.json';v=json.loads(abi.read_text());assert v['status']=='PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605';size=v['rows'][1]['sizes']['ieee80211com'];qsize=v['rows'][1]['sizes']['qdrv_wlan'];ic_offset=v['rows'][1]['fields']['qdrv_wlan']['ic']['offset'];assert ic_offset==0
 c='''#include <assert.h>
#include <string.h>
struct ieee80211com {unsigned char prefix[22605];unsigned char om_weather_cac_enabled;unsigned char suffix[ICSIZE-22606];};
struct qdrv_wlan {struct ieee80211com ic;unsigned char suffix[QSIZE-ICSIZE];};
static void actual_outer_zero(struct qdrv_wlan*qw){ZERO}
static void actual_inner_default(struct ieee80211com*ic){ASSIGN}
int main(void){struct qdrv_wlan q;for(unsigned x=0;x<256;x++){memset(&q,x,sizeof(q));actual_outer_zero(&q);assert(q.ic.om_weather_cac_enabled==0);for(unsigned n=0;n<sizeof(q);n++)assert(((unsigned char*)&q)[n]==0);q.ic.om_weather_cac_enabled=(unsigned char)x;actual_inner_default(&q.ic);assert(q.ic.om_weather_cac_enabled==0);}return 0;}
'''.replace('ICSIZE',str(size)).replace('QSIZE',str(qsize)).replace('ZERO',portzero).replace('ASSIGN',assignment);f=a.output/'actual-init-fragments.c';f.write_text(c);r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr
 for path in [*paths.values(),source,abi,a.compiler,Path(__file__),f,a.output/'fixture.exe']:pins[str(path)]=sha(path)
 for name in('weather478-oem-default-init-20261022T234600Z-r1','windows-oem-dfs467-scanap-pick-20261022T223500Z-r1','oem-wlan-missingops-20261022T131900Z-setparam-r2','oem-wlan-missingops-20261022T131900Z-getparam-r2'):
  path=ROOT/'outputs/rea'/name/'result.json';r=json.loads(path.read_text());assert r['exit_code']==0 and r['target_unchanged'];pins[str(path)]=sha(path);target=Path(r['command'][3]if r['command'][2]=='function'else r['command'][2]);st=str(target).replace('\\','/');st=st.replace('/mnt/c/','C:/').replace('/mnt/d/','D:/');path=Path(st);assert sha(path)==r['target_sha256'];pins[str(path)]=r['target_sha256']
 assert all(sha(path)==h for path,h in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_WEATHER478_OEM_ZERO_INIT_BOOLEAN_AP_SOURCE_DEFAULT_FRAGMENTS',hardware_accessed=False,firmware_eligible=False,constructor_cases=256,oem_ic_byte_offset=3060,oem_zero_allocation_bytes=32772,port_ic_byte_offset=22605,port_ic_size=size,port_qdrv_size=qsize,oem_matching_targets=True,port_zero_before_attach=True,explicit_default_after_ifattach=True,limits=['OEMcompleteallocationzero proven and noexplicitbf4 write in qdrvinit; externalcallees/async consumers not universally replayed','Hostfixture executesactualzero/defaultfragments using ARCwitnessedsizes, notwholeqdrvinitwithrealhardwarecallbacks','Initializedconstructiondefault0 only; noOEMcalibration/regulatory/CAC/RFacceptance']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
