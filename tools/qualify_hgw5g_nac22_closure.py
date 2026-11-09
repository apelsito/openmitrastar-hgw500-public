"""StrictNAC457 two-record moduledelta from qualifiedtwentyclosure.

Exactget/setchangedbodies backedactualfixture. Allresidualcode/data/symbols/
relocations match except declareddiagnosticencoding+48Btable+count. Sampletuple
andmissing/zero-EAGAIN are notcoherentmonitor orphysicalNAC acceptance.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf,normalized_path
from recover_hgw5g_driver_ops import Elf as OpsElf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def audit(old,new):
 changed_names={'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam'};transforms=[];details=[];diag=[]
 assert set(old.byname)==set(new.byname)and len(old.syms)==len(new.syms)
 for i,(a,b)in enumerate(zip(old.syms,new.syms)):
  if a['name']!=b['name']:
   renamed={'CSWTCH.718':'CSWTCH.719','CSWTCH.701':'CSWTCH.702','CSWTCH.716':'CSWTCH.717'}
   assert renamed.get(a['name'])==b['name']and a['type']==b['type']==1 and a['size']==b['size'],'unexpectedgeneratedsymbolrename'
   b['name']=a['name']
  assert(a['name'],a['type'],a['bind'],a['other'],old.symsection(a))==(b['name'],b['type'],b['bind'],b['other'],new.symsection(b))
  if a['type']!=2 or not a['size']:continue
  sec=old.symsection(a);x=old.byname[sec]['data'][a['value']:a['value']+a['size']];y=new.byname[sec]['data'][b['value']:b['value']+b['size']]
  if a['name']in changed_names:details.append(dict(index=i,name=a['name'],old_bytes=a['size'],new_bytes=b['size'],scope='SOURCEFIXTUREEXACTNACSETANDGUARDEDGET'))
  elif x!=y:
   z=bytearray(y)
   if a['name']=='ieee80211_delete_wlanunit':
    for pos,oldpair,newpair in [(44,'ea52','1253'),(116,'eb52','1353')]:assert x[pos:pos+2]==bytes.fromhex(oldpair)and y[pos:pos+2]==bytes.fromhex(newpair);z[pos:pos+2]=x[pos:pos+2]
   elif a['name']=='ieee80211_ioctl_giwfreq':assert x[76:78]==bytes.fromhex('180c')and y[76:78]==bytes.fromhex('580c');z[76:78]=x[76:78]
   elif a['name']=='ieee80211_param_from_qdrv':
    assert x[46:48]==bytes.fromhex('a3ed')and y[46:48]==bytes.fromhex('a1ed');assert x[58:60]==bytes.fromhex('9ded')and y[58:60]==bytes.fromhex('9bed');assert x[78:86]==bytes.fromhex('0a23800f00000000')and x[86:94]==bytes.fromhex('0a22800f00008f0d');assert y[78:82]==bytes.fromhex('d9da546a')and y[82:90]==bytes.fromhex('0a23800f00000000');z[78:82]=b'';z[86:86]=x[86:94];z[46:48]=x[46:48];z[58:60]=x[58:60]
   else:raise AssertionError('unrelatedfunction '+a['name'])
   assert bytes(z)==x,'otherdiagnosticbytes '+a['name'];diag.append(a['name'])
  if x!=y:transforms.append(dict(index=i,name=a['name'],section=sec,old_value=a['value'],new_value=b['value'],old_size=a['size'],new_size=b['size']))
 assert{r['name']for r in details}==changed_names
 for sec,x in old.byname.items():
  if not x['flags']&4:continue
  z=bytearray(new.byname[sec]['data'])
  for t in sorted([t for t in transforms if t['section']==sec],key=lambda t:t['new_value'],reverse=True):z[t['new_value']:t['new_value']+t['new_size']]=x['data'][t['old_value']:t['old_value']+t['old_size']]
  assert bytes(z)==x['data'],'allresidualexecutable '+sec
 def owner(elf,sec,value):
  xs=[(i,s)for i,s in enumerate(elf.syms)if s['type']in(1,2)and s['size']and elf.symsection(s)==sec and s['value']<=value<s['value']+s['size']];return min(xs,key=lambda x:(x[1]['size'],x[0]))if xs else None
 def addr(elf,sec,value):
  if sec=='.rodata.str1.4':return('string',normalized_path(elf.cstring(sec,value)))
  o=owner(elf,sec,value)
  if o:
   i,s=o;rel=value-s['value']
   if elf is new and s['name']=='ieee80211_param_from_qdrv':rel=rel+4 if rel>=94 else(82 if rel==86 else rel)
   return('object',i,s['name'],sec,rel)
  if elf is new:
   original=value;value-=sum(t['new_size']-t['old_size']for t in transforms if t['section']==sec and original>=t['new_value']+t['new_size'])
   if sec=='.rodata':
    table=next(s for s in elf.syms if s['name']=='ieee80211_priv_args')
    if original>=table['value']+table['size']:value-=48
  return('section',sec,value)
 def reloc(elf,r):
  o=owner(elf,r['section'],r['offset'])
  if o and o[1]['name']in changed_names:return None
  s=elf.syms[r['symbol']];sec=elf.symsection(s);target=addr(elf,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(s['name'],sec,s['type'],s['bind'],r['addend'])
  return(addr(elf,r['section'],r['offset']),r['type'],target)
 ar=Counter(v for r in old.relas if(v:=reloc(old,r))is not None);br=Counter(v for r in new.relas if(v:=reloc(new,r))is not None);delta=list((ar-br).elements())+list((br-ar).elements());assert not delta,'RELAresidual '+str(delta[:6])
 for a,b in zip(old.syms,new.syms):
  if a['type']==3 or a['name']in changed_names or a['name']=='ieee80211_param_from_qdrv':continue
  assert a['size']==b['size']or a['name']=='ieee80211_priv_args';assert addr(old,old.symsection(a),a['value'])==addr(new,new.symsection(b),b['value'])
 ot=next(s for s in old.syms if s['name']=='ieee80211_priv_args');nt=next(s for s in new.syms if s['name']=='ieee80211_priv_args');assert ot['size']==586*24 and nt['size']==588*24 and ot['value']==nt['value']
 for name,x in old.byname.items():
  y=new.byname[name];assert(x['type'],x['flags'],x['align'],x['entsize'])==(y['type'],y['flags'],y['align'],y['entsize'])
  if x['flags']&4 or x['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  a,b=x['data'],y['data']
  if name=='.rodata':cut=ot['value']+ot['size'];assert a==b[:cut]+b[cut+48:]
  elif name=='.data':offset=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')['value']+8;z=bytearray(b);assert struct.unpack_from('<H',a,offset)[0]==586 and struct.unpack_from('<H',b,offset)[0]==588;struct.pack_into('<H',z,offset,586);assert a==bytes(z)
  elif x['type']==8:assert x['size']==y['size']
  else:assert a==b,'allocateddata '+name
 return dict(status='PASS_EXACT_RESIDUAL_NAC22_MODULE_DELTA',changed=details,diagnostics=diag,residual_relocations=sum(ar.values()),symbols=len(old.syms),functions=sum(s['type']==2 and s['size']>0 for s in old.syms))

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--negative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);result=dict(status='NO_GO_NAC22_DELTA',hardware_accessed=False,firmware_eligible=False)
 try:
  qp={}
  def readjson(p):
   p=Path(p);raw=p.read_bytes();qp[str(p)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
  proof=readjson(a.build/'result.json');assert proof['status']=='PASS_SOURCE_WLAN_INCREMENTAL_PARENT_CLOSURE_PENDING_DELTA'and proof['reproducible'];pins=readjson(a.build/'input-pins.json')
  for path,h in pins.items():assert sha(path)==h,'inputdrift'+path
  fp=readjson(a.fixture);assert fp['status']=='PASS_ACTUAL_HOST_NAC22_SET_PREFIX_GET_FIXTURE'
  np=readjson(a.negative);assert np['status']=='PASS_SEVEN_NAC22_NEGATIVE_AUDIT_CASES'and np['cases']==7
  parent=readjson(a.parent/'result.json');candidate=Path(proof['candidate']);cp=readjson(candidate/'result.json')
  for p in [candidate/'source/wlan/ieee80211_wireless.c',Path(__file__),Path(__file__).parent/'qualify_f370_qdrv_module.py',Path(__file__).parent/'recover_hgw5g_driver_ops.py',a.parent/'a/wlan/wlan.ko',a.parent/'b/wlan/wlan.ko',a.build/'a/wlan/wlan.ko',a.build/'b/wlan/wlan.ko']:qp[str(p)]=sha(p)
  assert qp[str(candidate/'source/wlan/ieee80211_wireless.c')]==cp['wireless_sha256']
  oldpath=a.parent/'a/wlan/wlan.ko';newpath=a.build/'a/wlan/wlan.ko';report=audit(Elf(oldpath),Elf(newpath));oldops=OpsElf(oldpath).ioctl_records();newops=OpsElf(newpath).ioctl_records();assert newops[:586]==oldops;assert[(x['cmd'],x['set_args'],x['get_args'],x['name'])for x in newops[586:]]==[(457,18433,0,'nac_mode'),(457,0,18433,'get_nac_mode')]
  assert sha(newpath)==sha(a.build/'b/wlan/wlan.ko');assert all(sha(a.build/lane/'wlan'/(n+'.o'))==sha(a.parent/lane/'wlan'/(n+'.o'))for lane in('a','b')for n in [row['name']for row in parent['units']if row['lane']=='a'and row['component']=='wlan']if n!='ieee80211_wireless')
  for path,h in pins.items():assert sha(path)==h,'postdrift'+path
  for path,h in qp.items():assert sha(path)==h,'qualificationdrift'+path
  (a.output/'qualification-input-pins.json').write_text(json.dumps({**pins,**qp},indent=2)+'\n')
  (a.output/'audit.json').write_text(json.dumps(report,indent=2)+'\n');result.update(status='PASS_OFFLINE_NAC22_RECORD_SEMANTICS_AND_PARENT_CLOSURE',private_records=588,original_records_recovered=22,remaining_original_records=22,modules=proof['modules'],parent_unchanged_units_verified=36,fixture_prefix_samples=fp['prefix_samples'],fixture_setter_cases=fp['setter_cases'],negative_cases=7,pins_verified=len({**pins,**qp}),getter_semantics='Sampledscalarpacking; notcoherenttuple; missing/zero EAGAIN safetydeviation',lifecycle='F355/VAPstartlifetime retained baseline, newmonitorphysicalacceptance UNRUN',limits='TwolegacyEOPNOTSUPP plusNACsnapshotlimitations; no22feature/radio/traffic/releaseacceptanceclaim')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
