"""Complete R3-to-R4 typed retry source/module residual audit, no hardware.

Changed/new source bodies are bounded by fixtures; all other executable bytes,
symbols, exports and relocations are compared with declared anchor corrections.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r3-typed-batch-build-r2'
SOURCE=ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r4-typed-queue-source-r8'
FIXTURE=[ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r4-typed-queue-fixture-r10/result.json',ROOT/'outputs/rea/driver5g-ops-20261022-tqe-r4-initial-retry-fixture-r5/result.json']
CHANGED={'switch_tqe':{'omtqe_push_mcast_batch','tqe_rx_multicast'},'topaz_congest_queue':{'topaz_congest_queue_clear','omcgq_batch_finish','topaz_congest_enqueue','topaz_congest_queue_xmit'}}
NEW={'switch_tqe':{'omtqe_typed_queue_xmit'},'topaz_congest_queue':{'omcgq_batch_has_queued','omcgq_batch_queue_admit','omcgq_batch_queue_cancel_reserve','omcgq_batch_queue_reserve','omcgq_batch_retry_acquire','omcgq_batch_xmit_register','omcgq_typed_head'}}
PATCH={'switch_tqe':{'tqe_rx_napi_handler':{546:(210,83),547:(11,4),924:(82,211),925:(15,7)},'tqe_tx':{400:(22,151),401:(9,1)}},'topaz_congest_queue':{'omcgq_record_held':{82:(13,16),92:(13,16),108:(206,209),120:(13,16),130:(13,16),188:(206,209)},'topaz_congest_dequeue':{74:(138,141),82:(11,14)},'omcgq_batch_admit':{126:(14,17),134:(15,21),206:(15,21),214:(206,209),224:(15,21),290:(206,209)},'topaz_congest_queue_exit':{44:(12,15),50:(204,207)},'topaz_congest_release_queue':{40:(72,75)},'reg_congest_queue_stats':{8:(10,13),10:(43,46)}}}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def named(e):
 rows=[s for s in e.syms if s['name']];assert len(rows)==len({s['name']for s in rows});return{s['name']:s for s in rows}
def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]

def audit(op,np,c):
 o,n=Elf(op),Elf(np);os,ns=named(o),named(n);of={k:s for k,s in os.items()if s['type']==2 and s['size']};nf={k:s for k,s in ns.items()if s['type']==2 and s['size']};assert set(of)<=set(nf)and set(nf)-set(of)==NEW[c]
 for name,s in os.items():
  rename={'__UNIQUE_ID_description327':'__UNIQUE_ID_description328','__UNIQUE_ID_author328':'__UNIQUE_ID_author329','__UNIQUE_ID_license329':'__UNIQUE_ID_license330'}if c=='topaz_congest_queue'else{}
  target=rename.get(name,name);assert target in ns,'existingnamed symbol '+name;t=ns[target];assert(s['type'],s['bind'],s['other'],o.symsection(s))==(t['type'],t['bind'],t['other'],n.symsection(t)),'symbolattrs '+name
  if name in rename:assert o.byname['.modinfo']['data'][s['value']:s['value']+s['size']]==n.byname['.modinfo']['data'][t['value']:t['value']+t['size']],'generatedmetadata literal'
  if name not in CHANGED[c]:assert s['size']==t['size'],'symbolsize '+name
 assert set(o.byname)==set(n.byname)
 for name,s in o.byname.items():
  for attr in('type','flags','align','entsize'):assert s[attr]==n.byname[name][attr],(name,attr)
 for name,s in of.items():
  if name in CHANGED[c]:continue
  x,y=body(o,s),body(n,nf[name])
  if x!=y:
   assert name in PATCH[c]and len(x)==len(y);z=bytearray(y)
   for p,(a,b)in PATCH[c][name].items():assert x[p]==a and y[p]==b;z[p]=a
   assert bytes(z)==x,'remainingcode '+name
 # Everyunowned instruction is precisely NOP padding in these smallmodules.
 for sec,s in o.byname.items():
  if not s['flags']&4:continue
  def padding(e,fs):
   cover={i for s in fs.values()if e.symsection(s)==sec for i in range(s['value'],s['value']+s['size'])}
   return bytes(b for i,b in enumerate(e.byname[sec]['data'])if i not in cover)
  x,y=padding(o,of),padding(n,nf);assert len(x)%2==len(y)%2==0 and x==bytes.fromhex('e078')*(len(x)//2)and y==bytes.fromhex('e078')*(len(y)//2),'unownedNOP '+sec
 @lru_cache(maxsize=None)
 def point(e,sec,v):
  if sec in('.rodata.str1.4','__ksymtab_strings'):return('string',e.cstring(sec,v))
  arr=[s for s in e.syms if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=v<s['value']+s['size']]
  if arr:s=min(arr,key=lambda x:x['size']);return('object',sec,s['name'],v-s['value'])
  return('section',sec,v)
 def rel(e,r):
  arr=[s for s in e.syms if s['type']==2 and e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
  if arr and any(s['name']in CHANGED[c]|NEW[c]for s in arr):return None
  if c=='topaz_congest_queue'and r['section']=='__ksymtab':
   exp=[s for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+12]
   if exp and exp[0]['name'][10:]in NEW[c]:return None
  s=e.syms[r['symbol']];sec=e.symsection(s)
  if c=='topaz_congest_queue'and arr and arr[0]['name']in PATCH[c]and sec=='.bss'and s['type']==3 and r['addend']==0:target=('old_BSS_anchor',0)
  else:target=point(e,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(s['name'],sec,s['type'],s['bind'],r['addend'])
  return(point(e,r['section'],r['offset']),r['type'],target)
 a=Counter(v for r in o.relas if(v:=rel(o,r))is not None);b=Counter(v for r in n.relas if(v:=rel(n,r))is not None);assert a==b,'residualRELA '+str(list((a-b).elements())[:5])
 for name,s in o.byname.items():
  t=n.byname[name]
  if s['flags']&4 or s['type']==4 or name in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  if c=='topaz_congest_queue'and name in('__ksymtab','__ksymtab_strings'):continue
  if s['type']==8:
   if c=='switch_tqe':assert s['size']==t['size']
   else:assert s['size']==8256 and t['size']==10984
  elif name=='.rodata.str1.4':
   # Recoveredinputconfiguration blockstoresuse function source line numbers;
   # compilerstringsemantics remainexact when only declaredfunctionnamesadded.
   assert Counter(x for x in s['data'].split(b'\0')if x)==Counter(x for x in t['data'].split(b'\0')if x),'data strings '+name
  elif c=='switch_tqe'and name=='.rodata':
   x=s['data'];expected=x[:24]+x[72:96]+x[24:72]+x[96:]
   assert expected==t['data'],'exact reordered five diagnostic literal region'
  else:assert s['data']==t['data'],'data '+name
 # Exactallnewfunctionattributes and7newkernelrecordproperties.
 for name in NEW[c]:
  s=ns[name];exported=c=='topaz_congest_queue'and name!='omcgq_typed_head';assert(s['type'],s['bind'],s['other'],n.symsection(s))==(2,1 if exported else 0,0,'.text')
  if exported:
   record=ns['__ksymtab_'+name];assert(record['type'],record['bind'],record['other'],record['size'],n.symsection(record))==(1,0,0,12,'__ksymtab');rr={r['offset']-record['value']:r for r in n.relas if r['section']=='__ksymtab'and record['value']<=r['offset']<record['value']+12};assert set(rr)=={0,4,8};assert n.syms[rr[0]['symbol']]['name']==name
   for off,expected in((4,name),(8,'')):
    r=rr[off];s=n.syms[r['symbol']];assert n.cstring(n.symsection(s),s['value']+r['addend'])==expected
 rename={'__UNIQUE_ID_description327':'__UNIQUE_ID_description328','__UNIQUE_ID_author328':'__UNIQUE_ID_author329','__UNIQUE_ID_license329':'__UNIQUE_ID_license330'}if c=='topaz_congest_queue'else{}
 added=set(ns)-{rename.get(name,name)for name in os}
 exported=NEW['topaz_congest_queue']-{'omcgq_typed_head'}
 expected=NEW[c]|{'omcgq_batch_queue_admit','omcgq_batch_queue_cancel_reserve','omcgq_batch_queue_reserve','omcgq_batch_retry_acquire','omcgq_batch_xmit_register'}if c=='switch_tqe'else NEW[c]|{'omcgq_credit_queue','omcgq_queue_markers','omcgq_queue_pending','omcgq_queue_processing','omcgq_queue_reserved','omcgq_retry_marker','omcgq_typed_owner','omcgq_typed_xmit'}|{p+name for p in('__kstrtab_','__kstrtabns_','__ksymtab_')for name in exported}
 assert added==expected,'new named symbol membership '+str(added^expected)
 if c=='topaz_congest_queue':
  bss={'omcgq_quarantined':(0,1),'omcgq_retained':(1,1),'omcgq_reserved':(2,1),'omcgq_generation':(4,4),'omcgq_owner':(8,4),'omcgq_batch':(12,28),'omcgq_queue_pending':(40,4),'omcgq_queue_reserved':(44,4),'omcgq_credit_queue':(48,4),'pktlog_update_cgq_stats':(52,8),'g_congest_queue_ptr':(60,4),'omcgq_unrecorded':(64,4),'omcgq_held_count':(68,4),'omcgq_retry_marker':(72,4),'omcgq_typed_xmit':(76,4),'omcgq_typed_owner':(80,4),'omcgq_batch_generation':(84,4),'omcgq_queue_processing':(88,1),'omcgq_queue_markers':(92,2700),'omcgq_held':(2792,8192)}
  for name,(offset,size)in bss.items():
   s=ns[name];assert(n.symsection(s),s['value'],s['size'],s['type'],s['bind'],s['other'])==('.bss',offset,size,1,1 if name in('pktlog_update_cgq_stats','g_congest_queue_ptr')else 0,0),'BSS canonical '+name
 return{'status':'PASS_R4_CONFIRMED_CN_RETRY_GLOBAL_RESIDUAL_SCOPE','changed_source_functions':sorted(CHANGED[c]),'new_functions':sorted(NEW[c]),'other_exact_anchor_diagnostics':sorted(PATCH[c]),'residual_relocations':sum(a.values()),'limits':'Changed/newsourcebodies fixturebounded, hardwaretiming/foreign/recoveryacceptanceUNRUN.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);res={'status':'NO_GO_R4_TYPEDQUEUE_GLOBAL','hardware_accessed':False,'firmware_eligible':False}
 try:
  pins={str(p):sha(p)for p in [Path(__file__),ROOT/'tools/qualify_f370_qdrv_module.py',SOURCE/'result.json',*FIXTURE,a.build/'result.json',a.build/'input-pins.json',PARENT/'result.json']}
  for f in FIXTURE:
   for p in f.parent.iterdir():
    if p.is_file():pins[str(p)]=sha(p)
  for p in SOURCE.iterdir():
   if p.is_file():pins[str(p)]=sha(p)
  proof=json.loads((a.build/'result.json').read_text());assert proof['status']=='PASS_OFFLINE_COMPLETE_BOUNDED_PROVIDER_PAIR_PENDING_FIXTURE_AND_DELTA'
  buildpins=json.loads((a.build/'input-pins.json').read_text())
  for path,h in buildpins.items():
   p=Path(path);assert sha(p)==h,'actual buildpin drift '+path;pins[path]=h
  for f in FIXTURE:assert json.loads(f.read_text())['status'].startswith('PASS_')
  report={}
  for c in('switch_tqe','topaz_congest_queue'):
   p=a.build/'a'/c/(c+'.ko');assert sha(p)==sha(a.build/'b'/c/(c+'.ko'));report[c]=audit(PARENT/'a'/c/(c+'.ko'),p,c);pins[str(p)]=sha(p);pins[str(PARENT/'a'/c/(c+'.ko'))]=sha(PARENT/'a'/c/(c+'.ko'))
  for p,h in pins.items():assert sha(p)==h,'pin drift '+p
  (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'complete-audit.json').write_text(json.dumps(report,indent=2)+'\n');res.update(status='PASS_R4_TYPEDQUEUE_GLOBAL_RESIDUAL_PENDING_SEMANTIC_REVIEW',modules=proof['modules'],limits='Nohardware/foreign/HBMwholepath/recoveryacceptance; credit andheadercontextfixtures scoped.')
 except Exception as e:res['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2));return int(not res['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
