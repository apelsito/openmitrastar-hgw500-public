"""Strict SOURCE23 op490 scope against a fully compiled same-header NAC22.

No broad QDRV function mask. All 34 QDRV units plus five provider objects and
modules must exactly match the same-header source control. WLAN permits only
the actual fixture-bound op490 helper/dispatch, exact diagnostic encodings,
one 24-byte private record and its count. All residual bytes/RELA/symbols check.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()

SWITCH_MAP={'CSWTCH.663':'CSWTCH.669','CSWTCH.652':'CSWTCH.658','CSWTCH.719':'CSWTCH.725','CSWTCH.702':'CSWTCH.708','CSWTCH.665':'CSWTCH.671','CSWTCH.717':'CSWTCH.723'}
CHANGED={'ieee80211_ioctl_setparam'}
NEW={'om_fix_legacy_rate'}
DIAG={'ieee80211_delete_wlanunit','ieee80211_ioctl_giwfreq','ieee80211_param_from_qdrv'}

def keys(e,new=False):
 counts=Counter();result={}
 reverse={v:k for k,v in SWITCH_MAP.items()}
 for i,s in enumerate(e.syms):
  name=reverse.get(s['name'],s['name'])if new else s['name'];base=(name,e.symsection(s),s['type']);k=(*base,counts[base]);counts[base]+=1;result[k]=(i,s)
 return result

def audit(old,new):
 os,ns=keys(old),keys(new,True);assert set(os)<=set(ns),'old symbol membership'
 assert {k[0]for k in set(ns)-set(os)}==NEW,'new symbol membership'
 assert len(ns)-len(os)==1
 def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]
 transforms=[];changed=[];diag=[];unchanged=0
 for k,(i,s)in os.items():
  j,t=ns[k];assert(s['type'],s['bind'],s['other'])==(t['type'],t['bind'],t['other']),('symbol attrs',k)
  if s['type']!=2 or not s['size']:continue
  x,y=body(old,s),body(new,t)
  if k[0]in CHANGED:changed.append(dict(key=k,old_sha256=digest(x),new_sha256=digest(y),old_bytes=len(x),new_bytes=len(y)))
  elif x!=y:
   z=bytearray(y);name=k[0]
   if name=='ieee80211_delete_wlanunit':
    for pos,a,b in[(44,'1253','4653'),(116,'1353','4753')]:assert x[pos:pos+2]==bytes.fromhex(a)and y[pos:pos+2]==bytes.fromhex(b);z[pos:pos+2]=x[pos:pos+2]
   elif name=='ieee80211_ioctl_giwfreq':assert x[76:78]==bytes.fromhex('580c')and y[76:78]==bytes.fromhex('980c');z[76:78]=x[76:78]
   elif name=='ieee80211_param_from_qdrv':
    assert x[46:48]==bytes.fromhex('a1ed')and y[46:48]==bytes.fromhex('a3ed');assert x[58:60]==bytes.fromhex('9bed')and y[58:60]==bytes.fromhex('9ded');assert x[78:82]==bytes.fromhex('d9da546a');assert y[78:86]==bytes.fromhex('0a23800f00000000')and y[86:94]==bytes.fromhex('0a22800f0000910d');z[86:94]=b'';z[78:78]=x[78:82];z[46:48]=x[46:48];z[58:60]=x[58:60]
   else:raise AssertionError('unrelated function '+name)
   assert bytes(z)==x,'non diagnostic body bytes '+name;diag.append(name)
  else:unchanged+=1
  if x!=y:
   row=dict(section=old.symsection(s),old_value=s['value'],old_size=s['size'],new_value=t['value'],new_size=t['size'])
   if k[0]=='ieee80211_ioctl_setparam':
    assert new.byname['.text']['data'][t['value']+t['size']:t['value']+t['size']+2]==bytes.fromhex('e078'),'exact new setparam alignment NOP';row['new_size']+=2
   transforms.append(row)
 assert {r['key'][0]for r in changed}==CHANGED and set(diag)==DIAG
 for k in set(ns)-set(os):
  _,s=ns[k];assert(s['type'],s['bind'],s['other'],new.symsection(s),s['size'])==(2,0,0,'.text',328),'op490 helper exact compiled extent';transforms.append(dict(section='.text',old_value=0,old_size=0,new_value=s['value'],new_size=s['size']))
 ot=next(s for s in old.syms if s['name']=='ieee80211_priv_args');nt=next(s for s in new.syms if s['name']=='ieee80211_priv_args');assert ot['size']==588*24 and nt['size']==589*24 and ot['value']==nt['value'];cut=ot['value']+ot['size']
 for sec,s in old.byname.items():
  assert sec in new.byname
  if not s['flags']&4:continue
  b=bytearray(new.byname[sec]['data'])
  for row in sorted([r for r in transforms if r['section']==sec],key=lambda r:r['new_value'],reverse=True):b[row['new_value']:row['new_value']+row['new_size']]=s['data'][row['old_value']:row['old_value']+row['old_size']]
  assert bytes(b)==s['data'],'all residual executable '+sec
 def owner(e,sec,value):
  table=os if e is old else ns;choices=[(s['size'],i,k,s)for k,(i,s)in table.items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']];return min(choices,key=lambda x:(x[0],x[1]))if choices else None
 @lru_cache(maxsize=None)
 def addr(e,sec,value):
  if sec=='.rodata.str1.4':return('string',e.cstring(sec,value))
  choice=owner(e,sec,value)
  if choice:
   _,_,k,s=choice;rel=value-s['value']
   if e is new and k[0]=='ieee80211_param_from_qdrv':rel=rel-4 if rel>=94 else(86 if rel==82 else rel)
   return('object',k,rel)
  if e is new:
   original=value;value-=sum(r['new_size']-r['old_size']for r in transforms if r['section']==sec and original>=r['new_value']+r['new_size'])
   if sec=='.rodata'and original>=nt['value']+nt['size']:value-=24
  return('section',sec,value)
 def reloc(e,r):
  choice=owner(e,r['section'],r['offset'])
  if choice and choice[2][0]in(CHANGED|NEW):return None
  s=e.syms[r['symbol']];sec=e.symsection(s);name={v:k for k,v in SWITCH_MAP.items()}.get(s['name'],s['name'])if e is new else s['name'];target=addr(e,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(name,sec,s['type'],s['bind'],r['addend']);return(addr(e,r['section'],r['offset']),r['type'],target)
 ar=Counter(v for r in old.relas if(v:=reloc(old,r))is not None);br=Counter(v for r in new.relas if(v:=reloc(new,r))is not None);delta=list((ar-br).elements())+list((br-ar).elements());assert not delta,'residual RELA '+str(delta[:8])
 for k,(i,s)in os.items():
  _,t=ns[k]
  if s['type']==3 or k[0]in CHANGED or k[0]=='ieee80211_param_from_qdrv':continue
  assert s['size']==t['size']or k[0]=='ieee80211_priv_args','symbol size '+str(k)
  assert addr(old,old.symsection(s),s['value'])==addr(new,new.symsection(t),t['value']),'symbol address '+str(k)
 assert set(old.byname)==set(new.byname)
 for sec,s in old.byname.items():
  t=new.byname[sec];assert(s['type'],s['flags'],s['align'],s['entsize'])==(t['type'],t['flags'],t['align'],t['entsize'])
  if s['flags']&4 or s['type']==4 or sec in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  x,y=s['data'],t['data']
  if sec=='.rodata':assert x==y[:cut]+y[cut+24:],'data outside private record'
  elif sec=='.data':
   offset=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')['value']+8;z=bytearray(y);assert struct.unpack_from('<H',x,offset)[0]==588 and struct.unpack_from('<H',y,offset)[0]==589;struct.pack_into('<H',z,offset,588);assert x==bytes(z),'data outside private count'
  elif s['type']==8:assert s['size']==t['size'],'BSS extent'
  else:assert x==y,'allocated data '+sec
 return dict(status='PASS_EXACT_SOURCE23_OP490_RESIDUAL_AGAINST_HEADER_CONTROL',fixture_bound_bodies=changed,new_helper='om_fix_legacy_rate',diagnostics=diag,unchanged_functions=unchanged,residual_relocations=sum(ar.values()),symbols_old=len(old.syms),symbols_new=len(new.syms),sections=len(old.byname))

def layout_delta_inventory(parent,control):
 old,new=Elf(parent),Elf(control);of=keys(old);nf=keys(new);rows=[]
 for k,(_,s)in of.items():
  if s['type']!=2 or not s['size']or k not in nf:continue
  _,t=nf[k];x=old.byname[old.symsection(s)]['data'][s['value']:s['value']+s['size']];y=new.byname[new.symsection(t)]['data'][t['value']:t['value']+t['size']]
  if x!=y:rows.append(dict(key=k,old_bytes=len(x),new_bytes=len(y),old_sha256=digest(x),new_sha256=digest(y)))
 return dict(status='SOURCE_IDENTICAL_HEADER_ONLY_COMPILER_DELTA_INVENTORY_NOT_INSTRUCTION_EQUIVALENCE',changed_functions=rows,old_relocations=len(old.relas),new_relocations=len(new.relas),old_sha256=sha(parent),control_sha256=sha(control),limits='All parsed old IC offsets and QDRV +8 field layout witnessed; source identity and closure pinned. No broad executable mask used in selected candidate audit.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--control',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--parent-qdrv',type=Path,required=True);p.add_argument('--parent-qualification',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--abi-supplement',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--negative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);result=dict(status='NO_GO_SOURCE23_CONTROLLED_CLOSURE',hardware_accessed=False,firmware_eligible=False);pins={}
 try:
  def readjson(p):raw=Path(p).read_bytes();pins[str(p)]=digest(raw);return json.loads(raw)
  build=readjson(a.build/'result.json');control=readjson(a.control/'result.json');assert build['status']==control['status']=='PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA'and build['reproducible']and build['no_baseline_objects_reused']and control['no_baseline_objects_reused'];assert len(build['units'])==116 and len(control['units'])==58
  for directory in(a.build,a.control):
   for path,h in readjson(directory/'input-pins.json').items():pins[path]=h;assert sha(path)==h,'build input drift '+path
   for r in readjson(directory/'result.json')['modules']:pins[r['path']]=r['sha256'];assert sha(r['path'])==r['sha256']
  candidate=Path(build['candidate']);cs=Path(control['candidate']);cp=readjson(candidate/'result.json');sp=readjson(cs/'result.json');readjson(a.parent_source/'result.json')
  pp=readjson(a.parent_qualification);assert pp['status']=='PASS_OFFLINE_NAC22_RECORD_SEMANTICS_AND_PARENT_CLOSURE'and pp['original_records_recovered']==22
  for rel,h in sp['source_pins'].items():
   rel=rel.replace('\\','/');assert sha(cs/rel)==sha(a.parent_source/rel)==h,'source control identity '+rel;pins[str(cs/rel)]=pins[str(a.parent_source/rel)]=h
   if rel!='source/wlan/ieee80211_wireless.c':assert sha(candidate/rel)==h,'unrelated candidate source drift '+rel;pins[str(candidate/rel)]=h
  for rel,h in sp['header_pins'].items():rel=rel.replace('\\','/');assert sha(cs/rel)==sha(candidate/rel)==h,'candidate control header identity '+rel;pins[str(cs/rel)]=pins[str(candidate/rel)]=h
  assert sha(candidate/'source/wlan/ieee80211_wireless.c')==cp['wireless_sha256'];pins[str(candidate/'source/wlan/ieee80211_wireless.c')]=cp['wireless_sha256']
  abi=readjson(a.abi);assert abi['status']=='PASS_ARC_LEGACY23_ALL_PARSED_IC_VAP_PREFIX_QDRV_SHIFT8_WIRE';fixture=readjson(a.fixture);assert fixture['status']=='PASS_ACTUAL490_FULL_TRANSACTION_REFERENCE_HOST_FIXTURE'and fixture['source_sha256']==cp['wireless_sha256'];negative=readjson(a.negative);assert negative['status']=='PASS_SEVEN_SOURCE23_NEGATIVE_AUDIT_CASES'and negative['cases']==7
  src=(candidate/'source/wlan/ieee80211_wireless.c').read_text();start=src.index('static int om_fix_legacy_rate(');end=src.index('\nstatic int\nieee80211_ioctl_setparam(',start);assert digest(src[start:end].encode())==fixture['helper_sha256'],'actual fixture helper differs'
  dispatch=src[src.index('switch (param)',end):src.index('switch (param)',end)+200];assert 'case OM_OEM_PARAM_FIX_LEGACY_RATE:'in dispatch and 'return om_fix_legacy_rate(vap,value);'in dispatch,'op490 dispatch'
  for path,h in readjson(a.fixture.parent/'input-pins.json').items():
   normalized=path.replace('\\','/')
   if len(normalized)>2 and normalized[1]==':':normalized='/mnt/'+normalized[0].lower()+normalized[2:]
   file=Path(normalized);file=file if file.is_absolute()else Path(__file__).resolve().parents[1]/file;assert sha(file)==h,'fixture input drift';pins[str(file)]=h
  for file in(a.fixture.parent/'fixture.c',a.fixture.parent/'fixture.exe',a.negative.parent/'test_hgw5g_legacy23_delta_negative.py'):
   if file.exists():pins[str(file)]=sha(file)
  for path,h in readjson(a.abi.parent/'input-pins.json').items():pins[path]=h;assert sha(path)==h
  supplemental=readjson(a.abi_supplement/'result.json')
  for path,h in readjson(a.abi_supplement/'input-pins.json').items():pins[path]=h;assert sha(path)==h,'ABI supplemental drift '+path
  reports={};inventory={};exact_units=0
  for component in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   cpath=a.control/'a'/component/(component+'.ko');bpath=a.build/'a'/component/(component+'.ko');assert sha(bpath)==sha(a.build/'b'/component/(component+'.ko'))
   if component=='wlan':reports[component]=audit(Elf(cpath),Elf(bpath));inventory[component]=layout_delta_inventory(a.parent/'a/wlan/wlan.ko',cpath)
   else:
    assert sha(cpath)==sha(bpath),'whole same-header module '+component;reports[component]=dict(status='BYTE_IDENTICAL_WHOLE_SAME_HEADER_MODULE',bytes=bpath.stat().st_size,sha256=sha(bpath))
    if component=='qdrv':inventory[component]=layout_delta_inventory(a.parent_qdrv,cpath);pins[str(a.parent_qdrv)]=sha(a.parent_qdrv)
   for row in[r for r in control['units']if r['component']==component]:
    n=row['name'];old=a.control/'a'/component/(n+'.o');new=a.build/'a'/component/(n+'.o')
    if n!='ieee80211_wireless':assert sha(old)==sha(new),'same-header whole object '+n;exact_units+=1
  oldops=OpsElf(a.control/'a/wlan/wlan.ko').ioctl_records();newops=OpsElf(a.build/'a/wlan/wlan.ko').ioctl_records();assert newops[:588]==oldops and[(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in newops[588:]]==[(490,18433,0,'fix_legacy_rate')]
  e=Elf(a.build/'a/wlan/wlan.ko');helper=next(s for s in e.syms if s['name']=='om_fix_legacy_rate');setter=next(s for s in e.syms if s['name']=='ieee80211_ioctl_setparam');hrela=[r for r in e.relas if r['section']=='.text'and helper['value']<=r['offset']<helper['value']+helper['size']];assert len(hrela)==3 and[r['offset']-helper['value']for r in hrela]==[72,152,178],'helper exact call sites'
  assert e.syms[hrela[0]['symbol']]['name']=='ieee80211_param_to_qdrv'and e.syms[hrela[1]['symbol']]['name']=='ieee80211_setmode';assert e.syms[hrela[2]['symbol']]['type']==3 and hrela[2]['addend']==next(s['value']for s in e.syms if s['name']=='ieee80211_wireless_reassoc'),'helper reassoc target'
  assert any(r['section']=='.text'and setter['value']<=r['offset']<setter['value']+setter['size']and e.syms[r['symbol']]['type']==3 and r['addend']==helper['value']for r in e.relas),'actual setter links recovered helper'
  root=Path(__file__).resolve().parents[1]
  for path in(Path(__file__),Path(__file__).parent/'qualify_f370_qdrv_module.py',Path(__file__).parent/'recover_hgw5g_driver_ops.py',Path(__file__).parent/'test_hgw5g_legacy23_delta_negative.py',a.parent/'a/wlan/wlan.ko',root/'outputs/rea/oem-wlan-case-map-20261022T132100Z-r1/490-fix_legacy_rate-set.objdump.txt',root/'outputs/rea/oem-wlan-missingops-20261022T131900Z-setparam-r2/rea.json'):
   pins[str(path)]=sha(path)
  for path,h in pins.items():assert sha(path)==h,'qualification input drift '+path
  (a.output/'audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'header-control-layout-delta.json').write_text(json.dumps(inventory,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
  result.update(status='PASS_OFFLINE_SOURCE23_OP490_SAME_HEADER_SEVEN_MODULE_CLOSURE',reproducible=True,source_units_per_lane=58,same_header_unchanged_whole_units=exact_units,private_records=589,original_records_recovered=23,remaining_original_records=21,fixture_transactions=fixture['operations'],negative_cases=7,pins_verified=len(pins),modules=build['modules'],old_members_checked=abi['old_members_checked'],abi_dependency_supplement_status=supplemental['status'],limits='Host controlflow recovery only; two inherited unsupported ops and NAC scalar snapshot limitations preserved. ABI supplement hashes postcompile; source/header originals checked during witness. No fixed-rate PHY, RF, traffic, boot, persistence or release acceptance. Header-only parent control is not firmware.')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
