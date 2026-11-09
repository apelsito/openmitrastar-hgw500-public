"""Whole QDRV R9-to-R10 two-cleanup-call delta, no hardware."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from qualify_f370_qdrv_module import Elf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def audit(oldpath,newpath):
 a,b=Elf(oldpath),Elf(newpath);assert set(a.byname)==set(b.byname)and len(a.syms)==len(b.syms)
 for sec,x in a.byname.items():assert all(x[k]==b.byname[sec][k]for k in('type','flags','align','entsize'))
 work='qdrv_wlan_beacon_work';changed=None;diagnostics=[]
 for i,(x,y)in enumerate(zip(a.syms,b.syms)):
  assert(x['name'],x['type'],x['bind'],x['other'],a.symsection(x))==(y['name'],y['type'],y['bind'],y['other'],b.symsection(y)),'symbolidentity'
  if x['type']!=2 or not x['size']:continue
  u=a.sections[x['section']]['data'][x['value']:x['value']+x['size']];v=b.sections[y['section']]['data'][y['value']:y['value']+y['size']]
  if x['name']==work:
   assert x['value']==y['value']and x['size']==2066 and y['size']==2074
   changed={'index':i,'name':work,'start':x['value'],'oldsize':x['size'],'newsize':y['size'],'source_fixture_scope':'Two extra prepublication vnet_free_ioctl calls only'}
  elif u!=v:
   assert x['name']in('qdrv_wlan_auth_state_change','qdrv_wlan_exit');z=bytearray(v);positions=[628,794,942]if x['name']=='qdrv_wlan_auth_state_change'else[950]
   for p in positions:assert v[p]-u[p]==2;z[p]=u[p]
   assert bytes(z)==u,'nondiagnosticbyte';diagnostics.append((i,positions))
 assert changed
 for sec,x in a.byname.items():
  if not x['flags']&4:continue
  v=bytearray(b.byname[sec]['data'])
  for i,positions in diagnostics:
   old,new=a.syms[i],b.syms[i]
   if a.symsection(old)==sec:
    for p in positions:v[new['value']+p]=x['data'][old['value']+p]
  if a.symsection(a.syms[changed['index']])==sec:
   start=changed['start'];v[start:start+changed['newsize']]=x['data'][start:start+changed['oldsize']]
  assert bytes(v)==x['data'],'residualexecutables'
 @lru_cache(maxsize=None)
 def address(e,sec,value):
  if e is b and sec=='.text'and value>=changed['start']+changed['newsize']:value-=8
  if sec=='.rodata.str1.4':return('string',e.cstring(sec,value))
  return(sec,value)
 def rel(e,r):
  s=e.syms[changed['index']]
  if r['section']==e.symsection(s)and s['value']<=r['offset']<s['value']+s['size']:return None
  target=e.syms[r['symbol']];sec=e.symsection(target)
  t=address(e,sec,target['value']+r['addend'])if target['type']==3 or sec=='.rodata.str1.4'else(target['name'],sec,target['type'],target['bind'],r['addend'])
  return(address(e,r['section'],r['offset']),r['type'],t)
 ar=Counter(v for r in a.relas if(v:=rel(a,r))is not None);br=Counter(v for r in b.relas if(v:=rel(b,r))is not None);assert ar==br,'residualrelocations'
 for i,(x,y)in enumerate(zip(a.syms,b.syms)):
  if i==changed['index']or x['type']==3:continue
  assert x['size']==y['size']and address(a,a.symsection(x),x['value'])==address(b,b.symsection(y),y['value']),'symbolmetadata'
 for sec,x in a.byname.items():
  y=b.byname[sec]
  if x['flags']&4 or x['type']==4 or sec in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  assert x['data']==y['data']and x['size']==y['size'],'allocateddata'
 return{'status':'PASS_COMPLETE_R10_TWO_UNPUBLISHED_CLEANUP_CALL_DELTA','changed':changed,'diagnosticfunctions':len(diagnostics),'symbols':len(a.syms),'relocations_outside_changed_work':sum(ar.values()),'all_other_executable_data_metadata_exact':True}

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 pins={}
 def read(path):raw=Path(path).read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
 proof=read(a.build/'result.json');assert proof['status']=='PASS_R10_ONE_SOURCE_UNIT_TWICE_COMPLETE_PAIR_PENDING_DELTA';f=read(a.fixture);assert f['status']=='PASS_ACTUAL_PREPUBLICATION_HOSTLINK_CLEANUP'
 result=audit(a.parent/'qdrv/qdrv.ko',a.build/'a/qdrv/qdrv.ko')
 for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
  assert sha(a.build/'a'/c/(c+'.ko'))==sha(a.build/'b'/c/(c+'.ko'))
  if c!='qdrv':assert sha(a.parent/c/(c+'.ko'))==sha(a.build/'a'/c/(c+'.ko'))
 for row in proof['modules']:pins[row['path']]=row['sha256']
 for path,h in pins.items():assert sha(path)==h
 (a.output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps({'status':'PASS_OFFLINE_R10_COMPLETE_SEVEN_MODULE_PAIR','hardware_accessed':False,'firmware_eligible':False,'modules':proof['modules'],'scope':'Two unpublished ioctl cleanupcalls; noABI orothermodulechange. NoRF/lifecycle/persistence/release acceptance'},indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
