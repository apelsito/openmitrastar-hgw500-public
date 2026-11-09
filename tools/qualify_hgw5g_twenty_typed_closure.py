"""Strict eighteen-to-twenty complete-module typedVAP delta verification.

QDRV must be byte-identical. WLAN permits only get/set/default/ADDBA actual
bodies plus exact diagnostic-immediate encodingchanges. Every residual code
byte, data byte, symbol and relocation is compared canonically. No hardware.
"""
import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf,normalized_path
from recover_hgw5g_driver_ops import Elf as OpsElf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_ancillary(oldpath,newpath):
 old,new=Elf(oldpath),Elf(newpath)
 metadata={'.modinfo','.note.gnu.build-id','.symtab','.strtab','.shstrtab'}
 assert set(old.byname)==set(new.byname),'ancillarysectionmembership'
 for name,sec in old.byname.items():
  n=new.byname[name];assert(sec['type'],sec['flags'],sec['align'],sec['entsize'])==(n['type'],n['flags'],n['align'],n['entsize'])
  if name in metadata or sec['type']==4:continue
  assert sec['size']==n['size']and sec['data']==n['data'],'ancillaryoperationalbytes '+name
 def symbol(elf,s):
  sec=elf.symsection(s);value=s['value']
  if sec=='.modinfo'and s['type']!=3:
   value=elf.cstring(sec,value)
  return(s['name'],sec,value,s['size'],s['type'],s['bind'],s['other'])
 def symbols(elf):return Counter(symbol(elf,s)for s in elf.syms if not s['name'].startswith('__UNIQUE_ID_srcversion'))
 assert symbols(old)==symbols(new),'ancillarysymbolcontext'
 def relocation(elf,r):return(r['section'],r['offset'],r['type'],symbol(elf,elf.syms[r['symbol']]),r['addend'])
 assert Counter(relocation(old,r)for r in old.relas)==Counter(relocation(new,r)for r in new.relas),'ancillaryallRELA'
 def info(elf):
  result={}
  for part in elf.byname['.modinfo']['data'].split(b'\0'):
   if b'='in part:
    k,v=part.split(b'=',1);result.setdefault(k.decode(),[]).append(v.decode())
  return result
 a,b=info(old),info(new);delta=[k for k in set(a)|set(b)if a.get(k)!=b.get(k)]
 assert delta==['srcversion']and 'srcversion'not in a and len(b['srcversion'])==1,'ancillarymetadata'+str(delta)
 return dict(status='PASS_ANCILLARY_OPERATIONAL_BYTES_ALL_SYMBOLS_RELOCS',functions=sum(s['type']==2 and s['size']>0 for s in old.syms),relocations=len(old.relas),symbols=len(old.syms),declared_metadata_delta='Onlynewgeneratedsrcversionaddition; originalcode/data/exports exact')

CHANGED={'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam','ieee80211_vap_setup','ieee80211_send_mgmt'}
DIAGNOSTICS={'ieee80211_delete_wlanunit':[(44,'d852','ea52'),(116,'d952','eb52')],
'ieee80211_ioctl_giwfreq':[(76,'d80b','180c')],
'ieee80211_param_from_qdrv':[(92,'8e0d','8f0d')],
'ieee80211com_media_change':[(204,'1d08','5d08')],
'ieee80211_chan2mode':[(44,'3d08','3e08')]}
COMPACT={'ieee80211_get_chanflags':[(0,4,bytes.fromhex('3d089403')),(28,8,b''),(40,0,bytes.fromhex('61da556a'))],
'ieee80211_get_prichan_list_by_operating_class':[(34,2,bytes.fromhex('27f4')),(54,4,b''),(66,0,bytes.fromhex('0a22800f00004f0b'))]}

def body(elf,s):return elf.byname[elf.symsection(s)]['data'][s['value']:s['value']+s['size']]
def repair_diagnostic(name,x,y):
 z=bytearray(y);patches=[]
 if name in DIAGNOSTICS:
  for offset,old,new in DIAGNOSTICS[name]:
   assert x[offset:offset+len(bytes.fromhex(old))]==bytes.fromhex(old)and y[offset:offset+len(bytes.fromhex(new))]==bytes.fromhex(new),(name,offset)
   z[offset:offset+len(bytes.fromhex(new))]=bytes.fromhex(old);patches.append(dict(offset=offset,old=old,new=new))
 elif name=='ieee80211_get_chanflags':
  assert x[:4]==bytes.fromhex('3d089403')and y[:4]==bytes.fromhex('41089403')
  assert x[28:32]==bytes.fromhex('61da556a')and y[28:36]==bytes.fromhex('0a23800f00000000')and y[36:44]==bytes.fromhex('0a22800f0000210c')
  z[36:44]=b'';z[28:28]=bytes.fromhex('61da556a');z[:4]=x[:4];patches=[dict(kind='diagnostic3120to3121 expandedmovandbranchtarget',old='61<<5',new='3121')]
 elif name=='ieee80211_get_prichan_list_by_operating_class':
  assert x[34:36]==bytes.fromhex('27f4')and y[34:36]==bytes.fromhex('25f4')
  assert x[54:62]==bytes.fromhex('0a23800f00000000')and x[62:70]==bytes.fromhex('0a22800f00004f0b')
  assert y[54:58]==bytes.fromhex('b5da546a')and y[58:66]==bytes.fromhex('0a23800f00000000')
  z[54:58]=b'';z[62:62]=x[62:70];z[34:36]=x[34:36];patches=[dict(kind='diagnostic2895to2896 compactmovandbranchtarget',old='2895',new='181<<4')]
 else:raise AssertionError('unrelatedfunctionchanged '+name)
 assert bytes(z)==x,'otherbyteschanged '+name
 return patches

def audit_wlan(old,new):
 assert set(old.byname)==set(new.byname)
 assert len(old.syms)==len(new.syms)
 changed=[];diag=[];transform=[]
 for i,(a,b)in enumerate(zip(old.syms,new.syms)):
  assert(a['name'],a['type'],a['bind'],a['other'],old.symsection(a))==(b['name'],b['type'],b['bind'],b['other'],new.symsection(b)),'symbolidentity'+str(i)
  if a['type']!=2 or not a['size']:continue
  x,y=body(old,a),body(new,b)
  if a['name']in CHANGED:changed.append(dict(index=i,name=a['name'],section=old.symsection(a),old_value=a['value'],new_value=b['value'],old_size=a['size'],new_size=b['size'],old_sha256=hashlib.sha256(x).hexdigest(),new_sha256=hashlib.sha256(y).hexdigest(),scope='BOUND_SOURCE_DELTA_VERIFIED_BY_ACTUAL_FIXTURE'))
  elif x!=y:diag.append(dict(index=i,name=a['name'],changes=repair_diagnostic(a['name'],x,y)))
  if x!=y:transform.append(dict(index=i,section=old.symsection(a),old_value=a['value'],new_value=b['value'],old_size=a['size'],new_size=b['size']))
 assert{r['name']for r in changed}==CHANGED
 # The foursemanticbodies are independentactualfunctionfixtures; diagnostics
 # onlyexactbytepairs. Allsectionresidue includingunownedpadding mustmatch.
 for name,sec in old.byname.items():
  if not sec['flags']&4:continue
  result=bytearray(new.byname[name]['data'])
  for t in sorted([t for t in transform if t['section']==name],key=lambda t:t['new_value'],reverse=True):
   result[t['new_value']:t['new_value']+t['new_size']]=sec['data'][t['old_value']:t['old_value']+t['old_size']]
  assert bytes(result)==sec['data'],'unownedexecutableresidue '+name
 def owner(elf,sec,value):
  arr=[(i,s)for i,s in enumerate(elf.syms)if s['type']in(1,2)and s['size']and elf.symsection(s)==sec and s['value']<=value<s['value']+s['size']]
  return min(arr,key=lambda a:(a[1]['size'],a[0]))if arr else None
 def address(elf,sec,value):
  if sec=='.rodata.str1.4':return('string',normalized_path(elf.cstring(sec,value)))
  o=owner(elf,sec,value)
  if o:
   i,s=o
   # Diagnostics withencodingchanges needexplicitrelocsiteoffsetmapping below.
   rel=value-s['value']
   if elf is new and s['name']=='ieee80211_get_chanflags':rel=rel-4 if rel>=44 else (36 if rel==32 else rel)
   if elf is new and s['name']=='ieee80211_get_prichan_list_by_operating_class':rel=rel+4 if rel>=70 else (58 if rel==62 else rel)
   return('object',i,s['name'],sec,rel)
  if elf is new:
   original_value=value
   value-=sum(t['new_size']-t['old_size']for t in transform if t['section']==sec and original_value>=t['new_value']+t['new_size'])
   if sec=='.rodata':
    table=next(s for s in elf.syms if s['name']=='ieee80211_priv_args')
    if value>=table['value']+table['size']:value-=48
  return('section',sec,value)
 def relocation(elf,r):
  o=owner(elf,r['section'],r['offset'])
  if o and o[1]['name']in CHANGED:return None
  symbol=elf.syms[r['symbol']];sec=elf.symsection(symbol)
  target=address(elf,sec,symbol['value']+r['addend'])if symbol['type']==3 or sec=='.rodata.str1.4'else(symbol['name'],sec,symbol['type'],symbol['bind'],r['addend'])
  return(address(elf,r['section'],r['offset']),r['type'],target)
 before=Counter(v for r in old.relas if(v:=relocation(old,r))is not None);after=Counter(v for r in new.relas if(v:=relocation(new,r))is not None)
 delta=list((before-after).elements())+list((after-before).elements());assert not delta,'relocationsoutsideactualbodies '+str(delta[:8])
 for a,b in zip(old.syms,new.syms):
  if a['type']==3 or a['name']in CHANGED or a['name']in COMPACT:continue
  assert a['size']==b['size']or a['name']=='ieee80211_priv_args','symbolsize'+a['name']
  assert address(old,old.symsection(a),a['value'])==address(new,new.symsection(b),b['value']),'symboladdress'+a['name']
 table=next(s for s in old.syms if s['name']=='ieee80211_priv_args');nt=next(s for s in new.syms if s['name']=='ieee80211_priv_args');assert table['size']==584*24 and nt['size']==586*24 and table['value']==nt['value']
 for name,sec in old.byname.items():
  n=new.byname[name]
  assert(sec['type'],sec['flags'],sec['align'],sec['entsize'])==(n['type'],n['flags'],n['align'],n['entsize'])
  if sec['flags']&4 or sec['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  x,y=sec['data'],n['data']
  if name=='.rodata':
   end=table['value']+table['size'];assert x==y[:end]+y[end+48:],'allocatedrodataoutside48Btable'
  elif name=='.data':
   d=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')['value']+8;z=bytearray(y);assert struct.unpack_from('<H',x,d)[0]==584 and struct.unpack_from('<H',y,d)[0]==586;struct.pack_into('<H',z,d,584);assert x==bytes(z),'allocateddataoutsidecount'
  elif sec['type']==8:assert sec['size']==n['size'],'BSSsize'
  else:assert x==y,'allocateddata '+name
 return dict(status='PASS_ALL_WLAN_RESIDUAL_BYTES_SYMBOLS_RELOCS_DATA',actual_changed=changed,exact_diagnostic_changes=diag,function_count=sum(s['type']==2 and s['size']>0 for s in old.syms),relocations_outside_actual_bodies=sum(before.values()),all_symbols=len(old.syms),all_sections=len(old.byname))

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--ancillary-parent',type=Path,required=True);p.add_argument('--ancillary-manifest',type=Path,required=True);p.add_argument('--negative-proof',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 result=dict(status='NO_GO_TWENTY_TYPED_DELTA',hardware_accessed=False,firmware_eligible=False)
 try:
  pins={}
  def readjson(path):
   path=Path(path);raw=path.read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
  proof=readjson(a.build/'result.json');assert proof['status']=='PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA'and proof['reproducible']
  buildpins=readjson(a.build/'input-pins.json')
  # Rechecktheexactbuildsourceclosure before andafter qualification. Never
  # reinterpret module build as validation of a later editedsource/toolhead.
  for path,h in buildpins.items():assert sha(path)==h,'buildpindrift '+path;pins[path]=h
  abi=readjson(a.abi);fixture=readjson(a.fixture)
  assert abi['status']=='PASS_ARC_ALL_EXISTING_VAP_FIELDS_PREFIX_WIRE_UNCHANGED'and abi['prior_members_checked']==209 and abi['qdrv_vap_delta']==0
  assert fixture['status']=='PASS_ACTUAL_HOST_TYPED_AMSDU11N_CASES_AND_ADDBA_PREDICATE'
  source=Path(proof['candidate']);candidate_proof=readjson(source/'result.json')
  for n,h in candidate_proof['changed_wlan_sources'].items():
   path=source/'source/wlan'/n;assert sha(path)==h,'candidatechangedsource '+n;pins[str(path)]=h
  header=source/'headers/net80211/ieee80211_var.h';assert sha(header)==candidate_proof['header_sha256'];pins[str(header)]=candidate_proof['header_sha256']
  for path in [Path(__file__),Path(__file__).parent/'qualify_f370_qdrv_module.py',Path(__file__).parent/'recover_hgw5g_driver_ops.py',a.parent/'result.json',a.parent/'input-pins.json',a.parent/'a/qdrv/qdrv.ko',a.parent/'a/wlan/wlan.ko']:
   pins[str(path)]=sha(path)
  for c in ['wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']:
   path=a.ancillary_parent/(c+'.ko');pins[str(path)]=sha(path)
  manifest_raw=a.ancillary_manifest.read_bytes();pins[str(a.ancillary_manifest)]=hashlib.sha256(manifest_raw).hexdigest()
  manifest_rows=list(csv.DictReader(manifest_raw.decode().splitlines(),delimiter='\t'))
  for c in ['wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']:
   rows=[r for r in manifest_rows if r['module']=='wlan/'+c+'.ko'];assert len(rows)==1
   path=a.ancillary_parent/(c+'.ko');assert sha(path)==rows[0]['sha256']and path.stat().st_size==int(rows[0]['size']),'ancillaryF152manifest '+c
  assert sha(a.parent/'a/qdrv/qdrv.ko')==sha(a.build/'a/qdrv/qdrv.ko'),'QDRVnotbyteidentical18'
  report=audit_wlan(Elf(a.parent/'a/wlan/wlan.ko'),Elf(a.build/'a/wlan/wlan.ko'))
  oldops=OpsElf(a.parent/'a/wlan/wlan.ko').ioctl_records();newops=OpsElf(a.build/'a/wlan/wlan.ko').ioctl_records();assert newops[:584]==oldops and[(x['cmd'],x['set_args'],x['get_args'],x['name'])for x in newops[584:]]==[(484,18433,0,'txamsdu_11n'),(484,0,18433,'get_txamsdu_11n')]
  for row in proof['modules']:assert sha(row['path'])==row['sha256'];assert sha(a.build/'a'/row['component']/(row['component']+'.ko'))==sha(a.build/'b'/row['component']/(row['component']+'.ko'))
  ancillary={c:verify_ancillary(a.ancillary_parent/(c+'.ko'),a.build/'a'/c/(c+'.ko'))for c in ['wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']}
  negative=readjson(a.negative_proof);assert negative['status']=='PASS_SEVEN_NEGATIVE_TYPED_DELTA_CASES'and negative['cases']==7
  for row in proof['modules']:pins[row['path']]=row['sha256']
  for path,h in pins.items():assert sha(path)==h,'qualificationpindrift '+path
  (a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
  (a.output/'wlan-complete-audit.json').write_text(json.dumps(report,indent=2)+'\n')
  (a.output/'ancillary-complete-audit.json').write_text(json.dumps(ancillary,indent=2)+'\n')
  result.update(status='PASS_OFFLINE_COMPLETE_TWENTY_TYPED_HEADER_CLOSURE',main_pair_pass=True,ancillary_count_built=5,ancillary_original_manifest_sha256=pins[str(a.ancillary_manifest)],private_table_records=586,remaining_original_table_gaps=24,modules=proof['modules'],abi_sha256=pins[str(a.abi)],fixture_sha256=pins[str(a.fixture)],negative_proof_sha256=pins[str(a.negative_proof)],negative_cases=7,pins_verified=len(pins),limits='Exact20source/7moduletypedclosurequalified offline; noaggregation/throughput/RF/client/persistence/rollbackrelease acceptance')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
