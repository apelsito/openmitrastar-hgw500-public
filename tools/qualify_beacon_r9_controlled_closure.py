"""Qualify R9 lifetime delta against a full same-header parent19 source control.

This gate proves lifetime-only residual scope, ABI and two independent builds.
Inherited nineteen OEM entries are not promoted to feature/client acceptance.
All duplicate local symbols are matched by section/name/occurrence, not dict.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from functools import lru_cache

from qualify_f370_qdrv_module import Elf

CHANGED={'qdrv':{'qdrv_wlan_beacon_work'},'wlan':{'ieee80211_beacon_alloc_ie','ieee80211_add_beacon_ie_desc','ieee80211_beacon_update','ieee80211_add_beacon_desc_header','ieee80211_beacon_flush_param','ieee80211_beacon_alloc','ieee80211_add_beacon_desc_ie','ieee80211_beacon_create_param','ieee80211_add_beacon_desc_mandatory_fields'}}
NEW={'qdrv':set(),'wlan':{'om_beacon_allocation_ready','om_beacon_chain_valid','om_beacon_descriptor_valid','om_beacon_reserved_remove','om_beacon_reserved_update','om_beacon_slot_error.isra.0','om_ieee80211_beacon_build_status','om_ieee80211_beacon_frame_status'}}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def pathnorm(s):
 return s.replace('beacon-r9-parent19-control-source-20261022T183100Z-r1','beacon-global-descriptor-lifetime-20261022T174000Z-r9')
@lru_cache(maxsize=None)
def symbols(e):
 counts=Counter();rows={}
 for i,s in enumerate(e.syms):
  key=(s['name'],e.symsection(s),s['type'],counts[(s['name'],e.symsection(s),s['type'])]);counts[key[:3]]+=1;rows[key]=(i,s)
 return rows
@lru_cache(maxsize=None)
def functions(e):return{k:(i,s)for k,(i,s)in symbols(e).items()if s['type']==2 and s['size']}
def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]
def ancillary(oldpath,newpath):
 old,new=Elf(oldpath),Elf(newpath);assert set(old.byname)==set(new.byname)
 for name,s in old.byname.items():
  t=new.byname[name];assert(s['type'],s['flags'],s['align'],s['entsize'],s['size'])==(t['type'],t['flags'],t['align'],t['entsize'],t['size']),name
  if s['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  if name=='.rodata.str1.4':assert pathnorm(s['data'].decode('latin1'))==t['data'].decode('latin1'),'exact ancillary strings path map'
  else:assert s['data']==t['data'],'ancillary bytes '+name
 def symbol(e,s):
  sec=e.symsection(s);value=s['value']
  if sec=='.rodata.str1.4'and s['type']!=3:value=pathnorm(e.cstring(sec,value))
  return(s['name'],sec,value,s['size'],s['type'],s['bind'],s['other'])
 assert Counter(symbol(old,s)for s in old.syms)==Counter(symbol(new,s)for s in new.syms),'ancillary symbol metadata'
 def reloc(e,r):
  s=e.syms[r['symbol']];sec=e.symsection(s)
  target=('string',pathnorm(e.cstring(sec,s['value']+r['addend'])))if sec=='.rodata.str1.4'else(symbol(e,s),r['addend'])
  return(r['section'],r['offset'],r['type'],target)
 assert Counter(reloc(old,r)for r in old.relas)==Counter(reloc(new,r)for r in new.relas),'ancillary allRELA'
 return{'status':'PASS_EXACT_ANCILLARY_CODE_DATA_ALL_SYMBOLS_RELA_AFTER_DECLARED_PATH_MAP','symbols':len(old.syms),'relocations':len(old.relas)}

def audit(oldpath,newpath,component):
 old,new=Elf(oldpath),Elf(newpath);of,nf=functions(old),functions(new);assert set(of)<=set(nf)
 assert{k[0]for k in set(nf)-set(of)}==NEW[component]
 for k in set(nf)-set(of):
  _,s=nf[k];global_export=k[0]in{'om_beacon_reserved_remove','om_beacon_reserved_update','om_ieee80211_beacon_build_status','om_ieee80211_beacon_frame_status'}
  assert(s['type'],s['bind'],s['other'],new.symsection(s))==(2,1 if global_export else 0,0,'.text'),'exact new helper symbol '+k[0]
 assert set(old.byname)==set(new.byname)
 for name,s in old.byname.items():
  for attr in('type','flags','align','entsize'):assert s[attr]==new.byname[name][attr],(component,name,attr)
 changes=[];diagnostics=[];unchanged=[]
 for k,(i,s)in of.items():
  j,t=nf[k];x,y=body(old,s),body(new,t)
  if k[0]in CHANGED[component]:changes.append({'key':k,'old_value':s['value'],'new_value':t['value'],'old_size':s['size'],'new_size':t['size'],'old_sha256':digest(x),'new_sha256':digest(y)})
  elif x!=y:
   assert component=='qdrv'and k[0]in('qdrv_wlan_auth_state_change','qdrv_wlan_exit'),('unrelated function',k)
   positions=[628,794,942]if k[0]=='qdrv_wlan_auth_state_change'else[950];z=bytearray(y);assert len(x)==len(y)
   for p in positions:assert y[p]-x[p]==10;z[p]=x[p]
   assert bytes(z)==x;diagnostics.append({'key':k,'byte_positions':positions,'line_delta':10})
  else:unchanged.append(k)
 # Every byte outside changed function ranges includes exact NOP alignment.
 padding=[]
 for sec,s in old.byname.items():
  if not s['flags']&4:continue
  # Delete only actual changed/new body ranges; all unidentified/unowned code
  # and every unchanged function remains in the exact residual byte comparison.
  # Diagnostics retain their width and are rewritten with checked literals.
  a=bytearray(s['data']);b=bytearray(new.byname[sec]['data'])
  for d in diagnostics:
   k=d['key'];_,oldf=of[k];_,newf=nf[k]
   if old.symsection(oldf)==sec:
    for p in d['byte_positions']:b[newf['value']+p]=a[oldf['value']+p]
  old_ranges=sorted({(x['value'],x['size'])for k,(_,x)in of.items()if k[0]in CHANGED[component]and old.symsection(x)==sec},reverse=True)
  new_ranges=sorted({(x['value'],x['size'])for k,(_,x)in nf.items()if k[0]in(CHANGED[component]|NEW[component])and new.symsection(x)==sec},reverse=True)
  if component=='qdrv'and sec=='.text':
   k=next(k for k in nf if k[0]=='qdrv_wlan_beacon_work');_,t=nf[k];end=t['value']+t['size'];assert b[end:end+2]==bytes.fromhex('e078'),'exact new beaconwork alignment NOP'
   new_ranges=[(p,n+2)if p==t['value']else(p,n)for p,n in new_ranges]
  if component=='wlan'and sec=='.text':
   old_pad={'ieee80211_beacon_alloc','ieee80211_beacon_update','ieee80211_beacon_alloc_ie','ieee80211_add_beacon_ie_desc'}
   new_pad={'ieee80211_add_beacon_desc_ie','om_beacon_descriptor_valid','om_ieee80211_beacon_build_status','om_beacon_reserved_remove','om_ieee80211_beacon_frame_status','om_beacon_reserved_update'}
   for k,(_,t)in of.items():
    if k[0]in old_pad:
     end=t['value']+t['size'];assert a[end:end+2]==bytes.fromhex('e078');old_ranges=[(p,n+2)if p==t['value']else(p,n)for p,n in old_ranges]
   for k,(_,t)in nf.items():
    if k[0]in new_pad:
     end=t['value']+t['size'];assert b[end:end+2]==bytes.fromhex('e078');new_ranges=[(p,n+2)if p==t['value']else(p,n)for p,n in new_ranges]
  for p,n in old_ranges:del a[p:p+n]
  for p,n in new_ranges:del b[p:p+n]
  assert bytes(a)==bytes(b),'all residual executable bytes '+sec
  padding.append({'section':sec,'bytes':len(a),'sha256':digest(a),'includes_unowned_executable_bytes':True})
 osy,nsy=symbols(old),symbols(new)
 @lru_cache(maxsize=None)
 def point(e,sec,value):
  if sec in('.rodata.str1.4','__ksymtab_strings'):
   return('string',pathnorm(e.cstring(sec,value)))
  choices=[(s['size'],k,i,s)for k,(i,s)in symbols(e).items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']]
  if choices:
   _,k,i,s=min(choices,key=lambda x:(x[0],x[2]))
   if sec=='.rodata'and s['name'].startswith('__func__.'):
    literal=e.byname[sec]['data'][s['value']:s['value']+s['size']]
    return('function_literal',literal.hex(),value-s['value'])
   if component=='qdrv'and k[0]=='CSWTCH.697':k=('CSWTCH.696',*k[1:])
   return('object',k,value-s['value'])
  if e is new and sec=='.text'and component=='qdrv':
   row=next(r for r in changes if r['key'][0]=='qdrv_wlan_beacon_work')
   if value>=row['new_value']+row['new_size']:value-=row['new_size']-row['old_size']+2
  if e is new and sec=='.rodata'and component=='wlan'and value>=108:
   value+=28
  return('section',sec,value)
 def ownerkey(e,r):
  choices=[(s['size'],k)for k,(_,s)in functions(e).items()if e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
  return min(choices)[1]if choices else None
 def reloc(e,r):
  owned=ownerkey(e,r)
  if owned and owned[0]in(CHANGED[component]|NEW[component]):return None
  s=e.syms[r['symbol']];sec=e.symsection(s)
  if component=='wlan'and r['section']=='__ksymtab':
   choices=[s for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+12]
   if choices and choices[0]['name'][10:]in NEW['wlan']:return None
  target=point(e,sec,s['value']+r['addend'])if s['type']==3 or sec in('.rodata.str1.4','__ksymtab_strings')or(sec=='.rodata'and s['name'].startswith('__func__.'))else(s['name'],sec,s['type'],s['bind'],r['addend'])
  return(point(e,r['section'],r['offset']),r['type'],target)
 a=Counter(v for r in old.relas if(v:=reloc(old,r))is not None);b=Counter(v for r in new.relas if(v:=reloc(new,r))is not None);delta=list((a-b).elements())+list((b-a).elements());assert not delta,'residualRELA '+str(delta[:8])
 data=[]
 for name,s in old.byname.items():
  t=new.byname[name]
  if s['flags']&4 or s['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  x,y=s['data'],t['data']
  if name=='.rodata.str1.4':
   norm=lambda z:Counter(pathnorm(x.decode('latin1'))for x in z.split(b'\0')if x);removed=norm(x)-norm(y);added=norm(y)-norm(x)
   assert not added
   if component=='qdrv':assert not removed
   else:assert set(removed)=={'%s: allocated space %d is not enough for adding more ie descriptors\n'}
  elif component=='wlan'and name in('__ksymtab','__ksymtab_strings'):
   oldexp={s['name'][10:]for s in old.syms if s['name'].startswith('__ksymtab_')};newexp={s['name'][10:]for s in new.syms if s['name'].startswith('__ksymtab_')};assert oldexp<=newexp and newexp-oldexp=={x for x in NEW['wlan']if x in('om_beacon_reserved_remove','om_beacon_reserved_update','om_ieee80211_beacon_build_status','om_ieee80211_beacon_frame_status')}
  elif component=='wlan'and name=='.rodata':
   # Only the allocator's now-unused __func__ literal is removed; compare all
   # named object payloads individually, including duplicate local names.
   assert x[108:136]==b'ieee80211_beacon_alloc_ie\x00\x00\x00';assert x[:108]+x[136:]==y,'whole rodata after allocator literal removal'
  elif s['type']==8:assert s['size']==t['size']and s['align']==t['align']
  else:assert x==y,'data '+name
  data.append(name)
 # Function diagnostic literals can change occurrence numbers after the exact
 # allocator string removal. Match their actual bytes and complete attributes.
 def literal_symbols(e):
  return Counter((e.byname['.rodata']['data'][s['value']:s['value']+s['size']],s['size'],s['type'],s['bind'],s['other'])
   for s in e.syms if e.symsection(s)=='.rodata'and s['name'].startswith('__func__.'))
 before_literals,after_literals=literal_symbols(old),literal_symbols(new)
 if component=='wlan':
  removed=before_literals-after_literals;added=after_literals-before_literals
  assert not added and sum(removed.values())==1 and next(iter(removed))[0]==b'ieee80211_beacon_alloc_ie\0','exact removed diagnostic symbol'
 else:assert before_literals==after_literals,'unchanged diagnostic symbols'
 # Every old named metadata symbol must resolve, with the one exact switch
 # renumbering and removed allocator literal declared above.
 checked=0
 for k,(i,s)in osy.items():
  if not s['name']or s['type']==3:continue
  if old.symsection(s)=='.rodata'and s['name'].startswith('__func__.'):
   checked+=1;continue
  nk=('CSWTCH.697',*k[1:])if component=='qdrv'and k[0]=='CSWTCH.696'else k
  assert nk in nsy,('missing old symbol',k)
  j,t=nsy[nk];assert(s['type'],s['bind'],s['other'])==(t['type'],t['bind'],t['other']),('symbolattrs',k)
  if s['name']not in CHANGED[component]:assert s['size']==t['size'],('symbolsize',k)
  if s['type']==1 and not s['name'].startswith('__ksymtab_'):
   x=old.sections[s['section']]['data'][s['value']:s['value']+s['size']]
   y=new.sections[t['section']]['data'][t['value']:t['value']+t['size']]
   assert x==y,('old object payload',k)
  checked+=1
 if component=='wlan':
  exported={'om_beacon_reserved_remove','om_beacon_reserved_update','om_ieee80211_beacon_build_status','om_ieee80211_beacon_frame_status'}
  for name in exported:
   records=[s for s in new.syms if s['name']=='__ksymtab_'+name];assert len(records)==1
   record=records[0];assert(new.symsection(record),record['type'],record['bind'],record['other'],record['size'])==('__ksymtab',1,0,0,12),'exact new export record'
   rels={r['offset']-record['value']:r for r in new.relas if r['section']=='__ksymtab'and record['value']<=r['offset']<record['value']+12}
   assert set(rels)=={0,4,8},'export relocation positions'
   assert new.syms[rels[0]['symbol']]['name']==name,'export function target'
   for offset,prefix in((4,'__kstrtab_'),(8,'__kstrtabns_')):
    rel=rels[offset];symbol=new.syms[rel['symbol']]
    if symbol['type']==3:literal=new.cstring(new.symsection(symbol),symbol['value']+rel['addend'])
    else:
     assert symbol['name']==prefix+name;literal=new.cstring(new.symsection(symbol),symbol['value']+rel['addend'])
    assert literal==(name if offset==4 else ''),'export name or namespace literal'
 return{'status':'PASS_R9_LIFETIME_SCOPE_AGAINST_FULL_PARENT19_CONTROL','changed_source_bodies':changes,'diagnostics':diagnostics,'unchanged_functions_checked':len(unchanged),'new_functions':sorted(NEW[component]),'all_residual_relocations':sum(a.values()),'all_existing_symbol_attributes_checked':checked,'all_data_sections':data,'unowned_padding':padding,'limits':'Changed/new source bodies fixture-bound; inherited19operation behavior notacceptedbythiscontrolcomparison.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 result={'status':'NO_GO_BEACON_R9_CONTROLLED_GLOBAL','hardware_accessed':False,'firmware_eligible':False}
 try:
  pins={}
  def readjson(path):
   path=Path(path);raw=path.read_bytes();pins[str(path)]=digest(raw);return json.loads(raw)
  receipt=readjson(a.candidate/'result.json');control=readjson(a.control/'result.json');second=readjson(a.second/'result.json');assert receipt['status']==control['status']==second['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
  abi=readjson(a.abi);assert abi['status']=='PASS_ARC_FULL_IC_BO_PARAM_PREFIX_AND_PHYSICAL_WIRE_WITNESS'
  fixture=readjson(a.fixture);assert fixture['status']=='PASS_SOURCE_FULL_CHAIN_LIFETIME_AND_VALIDATION_FIXTURE'
  # Compose receipts bind their source/header closure before and after this
  # static audit. No later tool/source edit is substituted for those pins.
  for directory in(a.control,a.candidate,a.second):
   for path,h in readjson(directory/'input-pins.json').items():
    pins[path]=h;assert sha(path)==h,'composition input drift '+path
   for row in readjson(directory/'result.json')['modules']:
    pins[row['path']]=row['sha256'];assert sha(row['path'])==row['sha256'],'module receipt drift'
  root=Path(__file__).resolve().parents[1]
  source=root/'outputs/rea/beacon-global-descriptor-lifetime-20261022T174000Z-r9'
  source_proof=readjson(source/'result.json')
  for path,h in source_proof['changed_sources'].items():
   file=source/path.replace('\\','/');pins[str(file)]=h;assert sha(file)==h,'source candidate drift'
  for path in(Path(__file__),root/'tools/qualify_f370_qdrv_module.py',root/'tools/recover_hgw5g_driver_ops.py'):
   pins[str(path)]=sha(path)
  report={}
  for row in receipt['modules']:
   c=row['component'];path=a.candidate/c/(c+'.ko');s=a.second/c/(c+'.ko');assert sha(path)==sha(s)==row['sha256']
   if c in('qdrv','wlan'):report[c]=audit(a.control/c/(c+'.ko'),path,c)
   else:
    # Equivalent sources/header context: ancillary differences are only literal
    # mapped paths/build source identity. Full compiler/static gate handles maps.
    report[c]=ancillary(a.control/c/(c+'.ko'),path)
  (a.output/'complete-controlled-audit.json').write_text(json.dumps(report,indent=2)+'\n')
  for path,h in pins.items():assert sha(path)==h,'qualification input drift '+path
  (a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
  (a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
  result.update(status='PASS_OFFLINE_R9_LIFETIME_CONTROLLED_SEVEN_MODULE_SCOPE',reproducible=True,source_units_per_wave=58,wire_unchanged=True,modules=receipt['modules'],pins_verified=len(pins),read_once_inputs_rechecked=True,limits='Inherited19ops remainpartial/sourceproven; BSS/RRMcapabilitiesnotactionhandler/clientacceptance. Nohardware/RF/traffic/persistence/release.')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
