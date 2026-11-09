"""Strict R2-to-R3 typed batch code/data/symbol/RELA residual qualification.

Actual typed batch bodies/new helpers are fixture-bound, all other executable
bytes remain exact after declared anchor/diagnostic changes. No hardware proof.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-provider-build-r2'
SOURCE=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-typed-batch-source-r4'
FIXTURES=[ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-typed-batch-capacity-fixture-r3/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-typed-publication-fixture-r6/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-normal-writers-fixture-r3/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-fullcaller-fixture-r1/result.json']
CHANGED={'switch_tqe':{'tqe_rx_multicast'},'topaz_congest_queue':{'omcgq_bank_acquire','omcgq_bank_quarantine'}}
NEW={'switch_tqe':{'omtqe_push_mcast_batch'},'topaz_congest_queue':{'omcgq_batch_acquire','omcgq_batch_admit','omcgq_batch_complete','omcgq_batch_finish','omcgq_batch_matches','omcgq_batch_valid'}}
REMOVED={'switch_tqe':{'tqe_push_mcast'},'topaz_congest_queue':set()}
PATCHES={'switch_tqe':{'tqe_rx_napi_handler':{546:(209,210),547:(10,11),924:(81,82),925:(14,15)},'tqe_tx':{400:(21,22),401:(8,9)}},'topaz_congest_queue':{'omcgq_record_held':{82:(6,13),92:(6,13),108:(199,206),120:(6,13),130:(6,13),188:(199,206)},'topaz_congest_dequeue':{74:(131,138),82:(4,11)},'topaz_congest_queue_exit':{44:(5,12),50:(197,204)},'topaz_congest_enqueue':{62:(131,138),70:(4,11),76:(131,138),82:(4,11)},'topaz_congest_release_queue':{40:(69,72),41:(13,3)},'reg_congest_queue_stats':{8:(3,10),10:(36,43)}}}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def funcs(e):
 rows=[s for s in e.syms if s['type']==2 and s['size']];assert len(rows)==len({s['name']for s in rows});return{s['name']:s for s in rows}
def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]

def audit(op,np,c):
 o,n=Elf(op),Elf(np);of,nf=funcs(o),funcs(n);assert set(of)-set(nf)==REMOVED[c];assert set(nf)-set(of)==NEW[c]
 assert set(o.byname)==set(n.byname)
 osy={s['name']:s for s in o.syms if s['name']};nsy={s['name']:s for s in n.syms if s['name']};assert len(osy)==sum(bool(s['name'])for s in o.syms)and len(nsy)==sum(bool(s['name'])for s in n.syms),'duplicate named symbol'
 assert set(osy)-set(nsy)==REMOVED[c]
 for name,s in osy.items():
  if name in REMOVED[c]:continue
  t=nsy[name];assert(s['type'],s['bind'],s['other'],o.symsection(s))==(t['type'],t['bind'],t['other'],n.symsection(t)),'existing symbolattrs '+name
  if name not in CHANGED[c]:assert s['size']==t['size'],'existing symbolsize '+name
 for name,s in o.byname.items():
  for attr in('type','flags','align','entsize'):assert s[attr]==n.byname[name][attr],(name,attr)
 changed=[];patched=[]
 for name,s in of.items():
  if name in REMOVED[c]:continue
  t=nf[name];a,b=body(o,s),body(n,t)
  if name in CHANGED[c]:changed.append(name);continue
  if a!=b:
   assert name in PATCHES[c]and len(a)==len(b);z=bytearray(b)
   for p,(old,new)in PATCHES[c][name].items():assert a[p]==old and b[p]==new;z[p]=old
   assert bytes(z)==a;patched.append(name)
 def residue(e,fs,side):
  out={}
  for sec,s in e.byname.items():
   if not s['flags']&4:continue
   z=bytearray(s['data'])
   if side=='new':
    for name in PATCHES[c]:
     t=fs[name]
     if e.symsection(t)==sec:
      for p,(old,new)in PATCHES[c][name].items():z[t['value']+p]=old
   ranges=[(s['value'],s['size'])for name,s in fs.items()if name in(CHANGED[c]|(REMOVED[c]if side=='old'else NEW[c]))and e.symsection(s)==sec]
   padnames=({'switch_tqe':set(),'topaz_congest_queue':{'omcgq_bank_acquire'}}if side=='old'else{'switch_tqe':{'omtqe_push_mcast_batch','tqe_rx_multicast'},'topaz_congest_queue':{'omcgq_batch_matches','omcgq_bank_quarantine'}})[c]
   for name in padnames:
    s=fs[name]
    if e.symsection(s)==sec:
     end=s['value']+s['size'];assert z[end:end+2]==bytes.fromhex('e078'),'exact semantic padding '+name
     ranges=[(p,n+2)if p==s['value']else(p,n)for p,n in ranges]
   for start,size in sorted(ranges,reverse=True):del z[start:start+size]
   out[sec]=bytes(z)
  return out
 a,b=residue(o,of,'old'),residue(n,nf,'new')
 for sec in a:
  if c=='switch_tqe':
   # All old function bodies were matched by unique name and checked above;
   # compiler reorders two unchanged helpers. The only unowned bytes in these
   # exact modules are declared ARC NOP padding, checked separately in full.
   def unowned(e,fs):
    cover={i for s in fs.values()if e.symsection(s)==sec for i in range(s['value'],s['value']+s['size'])}
    return bytes(v for i,v in enumerate(e.byname[sec]['data'])if i not in cover)
   x,y=unowned(o,of),unowned(n,nf)
   expected={'.text':(52,56),'.text.unlikely':(2,2),'.init.text':(2,2),'.exit.text':(2,2)}[sec]
   assert x==bytes.fromhex('e078')*(expected[0]//2)and y==bytes.fromhex('e078')*(expected[1]//2),'exact TQE unowned padding'
  else:assert a[sec]==b[sec],'completecode residue '+sec
 @lru_cache(maxsize=None)
 def point(e,sec,value):
  if sec in('.rodata.str1.4','__ksymtab_strings'):return('string',e.cstring(sec,value))
  rows=[(s['size'],s)for s in e.syms if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']]
  if rows:_,s=min(rows,key=lambda x:x[0]);return('object',sec,s['name'],value-s['value'])
  return('section',sec,value)
 for name,s in osy.items():
  if name in REMOVED[c]or name in CHANGED[c]:continue
  t=nsy[name]
  if s['type']==1 and not name.startswith('__ksymtab_')and o.symsection(s)!='.modinfo':
   a=o.sections[s['section']]['data'][s['value']:s['value']+s['size']]
   b=n.sections[t['section']]['data'][t['value']:t['value']+t['size']]
   assert a==b,'existingobjectbytes '+name
  if s['type']not in(1,2)and o.symsection(s)=='__ksymtab_strings':
   assert o.cstring(o.symsection(s),s['value'])==n.cstring(n.symsection(t),t['value']),'existingnamespace/stringvalue '+name
  elif s['type']not in(1,2):assert s['value']==t['value'],'existingnonobjectvalue '+name
 added=set(nsy)-set(osy)
 batchexports=NEW['topaz_congest_queue']-{'omcgq_batch_matches'}
 expected=(NEW[c]|batchexports)if c=='switch_tqe'else(NEW[c]|{'omcgq_batch','omcgq_batch_generation','memset'}|{p+x for p in('__kstrtab_','__kstrtabns_','__ksymtab_')for x in batchexports})
 assert added==expected,'new namedsymbolmembership '+str(added^expected)
 def relocation(e,r):
  owners=[s for s in e.syms if s['type']==2 and e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
  ignored=CHANGED[c]|NEW[c]|REMOVED[c]
  if owners and any(s['name']in ignored for s in owners):return None
  if c=='topaz_congest_queue'and r['section']=='__ksymtab':
   rs=[s for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+12]
   if rs and rs[0]['name'][10:]in NEW[c]:return None
  s=e.syms[r['symbol']];sec=e.symsection(s)
  if e is n and c=='topaz_congest_queue'and s['type']==3 and sec=='.bss'and owners and owners[0]['name']in PATCHES[c]and r['addend']==0:
   # Checked anchor instructions shift all referencedoldfields exactly28B.
   target=('anchor_existing_BSS',0)
  elif e is o and c=='topaz_congest_queue'and s['type']==3 and sec=='.bss'and owners and owners[0]['name']in PATCHES[c]and r['addend']==0:target=('anchor_existing_BSS',0)
  else:target=point(e,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(s['name'],sec,s['type'],s['bind'],r['addend'])
  return(point(e,r['section'],r['offset']),r['type'],target)
 ra=Counter(v for r in o.relas if(v:=relocation(o,r))is not None);rb=Counter(v for r in n.relas if(v:=relocation(n,r))is not None);assert ra==rb,'allresidualRELA '+str(list((ra-rb).elements())[:5])
 for sec,s in o.byname.items():
  t=n.byname[sec]
  if s['flags']&4 or s['type']==4 or sec in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  if sec=='.modinfo':
   normalize=lambda z:Counter(part for part in z.split(b'\0')if part and not part.startswith(b'depends='));assert normalize(s['data'])==normalize(t['data'])
   a=next(x for x in s['data'].split(b'\0')if x.startswith(b'depends='));b=next(x for x in t['data'].split(b'\0')if x.startswith(b'depends='));assert set(a.split(b'=',1)[1].split(b','))==set(b.split(b'=',1)[1].split(b','))
  elif c=='topaz_congest_queue'and sec in('__ksymtab','__ksymtab_strings'):continue
  elif s['type']==8:
   assert(c=='switch_tqe'and s['size']==t['size'])or(c=='topaz_congest_queue'and s['size']==8224 and t['size']==8256)
  else:assert s['data']==t['data'],'data '+sec
 if c=='topaz_congest_queue':
  bss={'omcgq_quarantined':(0,1),'omcgq_retained':(1,1),'omcgq_reserved':(2,1),'omcgq_generation':(4,4),'omcgq_owner':(8,4),'omcgq_batch':(12,28),'pktlog_update_cgq_stats':(40,8),'g_congest_queue_ptr':(48,4),'omcgq_unrecorded':(52,4),'omcgq_held_count':(56,4),'omcgq_batch_generation':(60,4),'omcgq_held':(64,8192)}
  for name,(value,size)in bss.items():
   t=nsy[name];assert(n.symsection(t),t['value'],t['size'],t['type'],t['bind'],t['other'])==('.bss',value,size,1,1 if name in('pktlog_update_cgq_stats','g_congest_queue_ptr')else 0,0),'new BSS '+name
  exported=NEW[c]-{'omcgq_batch_matches'}
  for name in exported:
   s=nsy[name];assert(s['type'],s['bind'],s['other'],n.symsection(s))==(2,1,0,'.text')
   record=nsy['__ksymtab_'+name];assert(record['size'],record['type'],record['bind'],record['other'],n.symsection(record))==(12,1,0,0,'__ksymtab')
   records={r['offset']-record['value']:r for r in n.relas if r['section']=='__ksymtab'and record['value']<=r['offset']<record['value']+12};assert set(records)=={0,4,8}
   assert n.syms[records[0]['symbol']]['name']==name
   for offset,expected in((4,name),(8,'')):
    r=records[offset];t=n.syms[r['symbol']];assert n.cstring(n.symsection(t),t['value']+r['addend'])==expected
  s=nsy['omcgq_batch_matches'];assert(s['type'],s['bind'],s['other'],n.symsection(s))==(2,0,0,'.text')
 else:
  s=nsy['omtqe_push_mcast_batch'];assert(s['type'],s['bind'],s['other'],n.symsection(s))==(2,0,0,'.text')
 return{'status':'PASS_R3_TYPED_BATCH_RESIDUAL_SCOPE','changed_source_bodies':sorted(CHANGED[c]),'removed_source_functions':sorted(REMOVED[c]),'new_source_functions':sorted(NEW[c]),'exact_anchor_diagnostic_functions':patched,'residual_relocations_checked':sum(ra.values()),'limits':'Actualchanged/newbodies fixturebound; notuniversalfirmware/release acceptance.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);result={'status':'NO_GO_R3_TYPED_BATCH_GLOBAL','hardware_accessed':False,'firmware_eligible':False}
 try:
  pins={str(p):sha(p)for p in [Path(__file__),ROOT/'tools/qualify_f370_qdrv_module.py',SOURCE/'result.json',*FIXTURES,a.build/'result.json',a.build/'input-pins.json',PARENT/'result.json',PARENT/'input-pins.json']}
  for fixture in FIXTURES:
   for p in fixture.parent.iterdir():
    if p.is_file():pins[str(p)]=sha(p)
  for name in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h'):pins[str(SOURCE/name)]=sha(SOURCE/name)
  proof=json.loads((a.build/'result.json').read_text());assert proof['status']=='PASS_OFFLINE_COMPLETE_BOUNDED_PROVIDER_PAIR_PENDING_FIXTURE_AND_DELTA'
  # Hash the completed build closure before and after qualification. Windows
  # filesystem paths are remapped through WSL only for this exact local gate.
  buildpins=json.loads((a.build/'input-pins.json').read_text())
  for path,h in buildpins.items():
   selected=Path(path.replace('/mnt/c/','C:/').replace('/mnt/d/','D:/'))if __import__('os').name=='nt'else Path(path)
   if str(selected).startswith('/home/')or str(selected).startswith('\\home\\'):continue
   assert sha(selected)==h,'completed buildpin drift '+path;pins[str(selected)]=h
  for f in FIXTURES:assert json.loads(f.read_text())['status'].startswith('PASS_')
  report={}
  for c in('switch_tqe','topaz_congest_queue'):
   np=a.build/'a'/c/(c+'.ko');assert sha(np)==sha(a.build/'b'/c/(c+'.ko'));report[c]=audit(PARENT/'a'/c/(c+'.ko'),np,c);pins[str(np)]=sha(np);pins[str(PARENT/'a'/c/(c+'.ko'))]=sha(PARENT/'a'/c/(c+'.ko'))
  for p,h in pins.items():assert sha(p)==h,'qualificationinput drift '+p
  (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
  (a.output/'complete-audit.json').write_text(json.dumps(report,indent=2)+'\n');result.update(status='PASS_R3_TYPED_BATCH_GLOBAL_RESIDUAL_PENDING_RECOVERY_POLICY',modules=proof['modules'],limits='VLANdenialnotforwarded; multicastretrychangedtoquarantine. Capacityownerreservationfinite, butHMBwaits/foreignbank/recovery/physicalNO_GO.')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
