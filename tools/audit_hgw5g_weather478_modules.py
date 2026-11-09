"""Complete SOURCE25 residual module scope against full same-header SOURCE23.

Admit only pinned/fixture-bound CoC PM/CSA helpers, dispatcher/count/table and
quiesce integration. No broad QDRV offset mask: same-header source control
retains all layout effects. Duplicate local symbols are occurrence-matched.
"""
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf

CHANGED={'qdrv':{'qdrv_wlan_init'},'wlan':{'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam'},'wlan_scan_ap':{'ap_pick_channel'}}
NEW={'qdrv':set(),'wlan':set(),'wlan_scan_ap':set()}
EXPORTS=set()
RENAME={'CSWTCH.1119':'CSWTCH.1120','CSWTCH.1108':'CSWTCH.1109','CSWTCH.1175':'CSWTCH.1176','CSWTCH.1158':'CSWTCH.1159','CSWTCH.1121':'CSWTCH.1122','CSWTCH.1173':'CSWTCH.1174','__UNIQUE_ID_license328':'__UNIQUE_ID_license329','__UNIQUE_ID_description327':'__UNIQUE_ID_description328','__UNIQUE_ID_author326':'__UNIQUE_ID_author327'}
DIAG={'ieee80211_delete_wlanunit':[(44,'9653','a153'),(116,'9753','a253')],'ieee80211_ioctl_giwfreq':[(76,'180e','580e')],'ieee80211_param_from_qdrv':[(92,'970d','980d')],'qdrv_wlan_exit':[(962,'0424','0524')],'ap_end':[(104,'ce0a','0e0b')]}
COMPACT=set()

def digest(b):return hashlib.sha256(b).hexdigest()

def symbols(e,new=False,renames=None):
 counts=Counter();out={};reverse={v:k for k,v in (renames or {}).items()}
 for i,s in enumerate(e.syms):
  n=reverse.get(s['name'],s['name'])if new else s['name'];base=(n,e.symsection(s),s['type']);k=(*base,counts[base]);counts[base]+=1;out[k]=(i,s)
 return out

def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]

def repair(name,x,y):
 z=bytearray(y)
 if name in DIAG:
  for pos,a,b in DIAG[name]:assert x[pos:pos+2]==bytes.fromhex(a)and y[pos:pos+2]==bytes.fromhex(b),(name,pos);z[pos:pos+2]=x[pos:pos+2]
 elif name=='ieee80211_get_prichan_list_by_operating_class':
  assert x[34:36]==bytes.fromhex('25f4')and y[34:36]==bytes.fromhex('27f4');assert x[54:58]==bytes.fromhex('b5da546a');assert y[54:62]==bytes.fromhex('0a23800f00000000')and y[62:70]==bytes.fromhex('0a22800f0000ed0b');z[62:70]=b'';z[54:54]=x[54:58];z[34:36]=x[34:36]
 else:raise AssertionError('unrelated function '+name)
 assert bytes(z)==x,'non diagnostic bytes '+name

def audit(old,new,component):
 renames={k:v for k,v in RENAME.items()if (component=='wlan'and k.startswith('CSWTCH.'))or(component=='wlan_scan_ap'and k.startswith('__UNIQUE_ID_'))}
 os,ns=symbols(old),symbols(new,True,renames);of={k:(i,s)for k,(i,s)in os.items()if s['type']==2 and s['size']};nf={k:(i,s)for k,(i,s)in ns.items()if s['type']==2 and s['size']};assert set(of)<=set(nf);assert{k[0]for k in set(nf)-set(of)}==NEW[component],'new functions'
 changed=[];diagnostics=[];transforms=[];same=0
 for k,(i,s)in of.items():
  j,t=nf[k];x,y=body(old,s),body(new,t)
  if k[0]in CHANGED[component]:changed.append(dict(key=k,old_bytes=s['size'],new_bytes=t['size'],old_sha256=digest(x),new_sha256=digest(y)))
  elif x!=y:
   assert k[0]in DIAG,('unrelated function',k);repair(k[0],x,y);diagnostics.append(k[0])
  else:same+=1
  if x!=y:transforms.append(dict(key=k,section=old.symsection(s),old_value=s['value'],new_value=t['value'],old_size=s['size'],new_size=t['size']))
 assert{r['key'][0]for r in changed}==CHANGED[component]
 assert set(diagnostics)==({'ieee80211_delete_wlanunit','ieee80211_ioctl_giwfreq','ieee80211_param_from_qdrv'}if component=='wlan'else({'ap_end'}if component=='wlan_scan_ap'else{'qdrv_wlan_exit'}))
 for k in set(nf)-set(of):
  _,s=nf[k];assert(s['type'],s['bind'],s['other'],new.symsection(s))==(2,1 if k[0]in EXPORTS else 0,0,'.text');transforms.append(dict(key=k,section='.text',old_value=0,old_size=0,new_value=s['value'],new_size=s['size']))
 # Diagnostic code changes are replaced with exact old byte ranges. Allowed
 # changed/new semantic ranges are deleted; anonymous executable residue stays.
 padding=[]
 for sec,s in old.byname.items():
  assert sec in new.byname
  if not s['flags']&4:continue
  a=bytearray(s['data']);b=bytearray(new.byname[sec]['data']);oldranges=[];newranges=[]
  for r in transforms:
   if r['section']!=sec:continue
   name=r['key'][0]
   if name in CHANGED[component]|NEW[component]:
    oldn=r['old_size'];newn=r['new_size']
    if oldn:oldranges.append((r['old_value'],oldn))
    newranges.append((r['new_value'],newn))
   else:
    b[r['new_value']:r['new_value']+r['new_size']]=a[r['old_value']:r['old_value']+r['old_size']]
  # Diagnostic width changes adjust later positions; remove semantic ranges
  # in mapped coordinates after those diagnostic replacements.
  for pos,n in sorted(oldranges,reverse=True):del a[pos:pos+n]
  for pos,n in sorted(newranges,reverse=True):
   mapped=pos-sum(r['new_size']-r['old_size']for r in transforms if r['section']==sec and r['key'][0]not in(CHANGED[component]|NEW[component])and pos>=r['new_value']+r['new_size']);del b[mapped:mapped+n]
  # All named function bodies have already been individually checked. The
  # linker reorders this unit's functions; verify each unnamed executable gap
  # anchored to its following function, rather than assuming global order.
  def gaps(e,fs):
   rows={};p=0;data=e.byname[sec]['data']
   for k,(_,s)in sorted(fs.items(),key=lambda row:row[1][1]['value']):
    if e.symsection(s)!=sec:continue
    if s['value']>p:
     raw=data[p:s['value']];prefix=0
     while raw.startswith(bytes.fromhex('e078')):raw=raw[2:];prefix+=2
     rows[k]=(raw,prefix)
    p=max(p,s['value']+s['size'])
   if p<len(data):rows[('__section_tail__',sec,2,0)]=(data[p:],0)
   return rows
  ag,bg=gaps(old,of),gaps(new,nf);ac=Counter(raw for raw,n in ag.values()if raw);bc=Counter(raw for raw,n in bg.values()if raw);assert ac==bc,'every anonymous executable body '+sec
  for k,(raw,n)in ag.items():
   if raw:assert k in bg and bg[k][0]==raw,'anonymous gap owner '+str(k)
  ap=sum(n for _,n in ag.values());bp=sum(n for _,n in bg.values());expected=2 if sec=='.text'and component=='wlan_scan_ap'else 0;assert bp-ap==expected,('exact anonymous NOP delta',sec,ap,bp)
  padding.append(dict(section=sec,anonymous_body_bytes=sum(len(x)for x in ac.elements()),anonymous_body_count=sum(ac.values()),old_nop_bytes=ap,new_nop_bytes=bp,every_non_nop_body_and_following_owner_exact=True))
 table_old=next((s for s in old.syms if s['name']=='ieee80211_priv_args'),None);table_new=next((s for s in new.syms if s['name']=='ieee80211_priv_args'),None)
 if component=='wlan':assert table_old['value']==table_new['value']and table_old['size']==598*24 and table_new['size']==600*24
 @lru_cache(maxsize=None)
 def owner(e,sec,value):
  sy=os if e is old else ns;rows=[(s['size'],i,k,s)for k,(i,s)in sy.items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']];return min(rows,key=lambda r:(r[0],r[1]))if rows else None
 @lru_cache(maxsize=None)
 def addr(e,sec,value):
  if sec in('.rodata.str1.4','__ksymtab_strings'):return('string',e.cstring(sec,value))
  row=owner(e,sec,value)
  if row:
   _,i,k,s=row;rel=value-s['value']
   return('object',k,rel)
  if sec in e.byname and e.byname[sec]['flags']&4:
   p=0;fs=of if e is old else nf
   for k,(_,s)in sorted(fs.items(),key=lambda row:row[1][1]['value']):
    if e.symsection(s)!=sec:continue
    if p<=value<s['value']:
     raw=e.byname[sec]['data'][p:s['value']];prefix=0
     while raw.startswith(bytes.fromhex('e078')):raw=raw[2:];prefix+=2
     return('anonymous_gap',k,value-p-prefix)
    p=max(p,s['value']+s['size'])
  if e is new:
   original=value;value-=sum(r['new_size']-r['old_size']for r in transforms if r['section']==sec and original>=r['new_value']+r['new_size'])
   if component=='wlan'and sec=='.rodata'and original>=table_new['value']+table_new['size']:value-=48
  return('section',sec,value)
 def export_owner(e,r):
  if r['section']!='__ksymtab':return None
  return next((s['name'][10:]for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+s['size']),None)
 def reloc(e,r):
  row=owner(e,r['section'],r['offset'])
  if row and row[2][0]in(CHANGED[component]|NEW[component]):return None
  if component=='wlan'and export_owner(e,r)in EXPORTS:return None
  s=e.syms[r['symbol']];sec=e.symsection(s);name={v:k for k,v in renames.items()}.get(s['name'],s['name'])if e is new else s['name'];target=addr(e,sec,s['value']+r['addend'])if s['type']==3 or sec in('.rodata.str1.4','__ksymtab_strings')else(name,sec,s['type'],s['bind'],r['addend'])
  return(addr(e,r['section'],r['offset']),r['type'],target)
 ar=Counter(v for r in old.relas if(v:=reloc(old,r))is not None);br=Counter(v for r in new.relas if(v:=reloc(new,r))is not None);delta=list((ar-br).elements())+list((br-ar).elements());assert not delta,'all residual RELA '+str(delta[:10])
 assert set(old.byname)==set(new.byname)
 for sec,s in old.byname.items():
  t=new.byname[sec];assert(s['type'],s['flags'],s['align'],s['entsize'])==(t['type'],t['flags'],t['align'],t['entsize'])
  if s['flags']&4 or s['type']==4 or sec in('.symtab','.strtab','.shstrtab','.note.gnu.build-id'):continue
  x,y=s['data'],t['data']
  if sec=='.modinfo':
   def info(z):return Counter(v for v in z.split(b'\0')if v and not v.startswith(b'srcversion='))
   assert info(x)==info(y),'module metadata';continue
  if component=='wlan'and sec=='.rodata':cut=table_old['value']+table_old['size'];assert x==y[:cut]+y[cut+48:],'data outside48Btable'
  elif component=='wlan'and sec=='.data':
   p=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')['value']+8;z=bytearray(y);assert struct.unpack_from('<H',x,p)[0]==598 and struct.unpack_from('<H',y,p)[0]==600;struct.pack_into('<H',z,p,598);assert x==bytes(z),'data outside private count'
  elif component=='wlan'and sec=='.rodata.str1.4':
   strings=lambda z:Counter(v for v in z.split(b'\0')if v);assert strings(x)==strings(y),'all existing strings'
  elif component=='wlan'and sec in('__ksymtab','__ksymtab_strings'):
   oldexp={s['name'][10:]for s in old.syms if s['name'].startswith('__ksymtab_')};newexp={s['name'][10:]for s in new.syms if s['name'].startswith('__ksymtab_')};assert oldexp<=newexp and newexp-oldexp==EXPORTS
   if sec=='__ksymtab':
    b=bytearray(y)
    for s in sorted([s for s in new.syms if s['name'].startswith('__ksymtab_')and s['name'][10:]in EXPORTS],key=lambda s:s['value'],reverse=True):assert s['size']==12;del b[s['value']:s['value']+12]
    assert bytes(b)==x,'export record residue'
   else:assert Counter(v for v in y.split(b'\0')if v)-Counter(v for v in x.split(b'\0')if v)==Counter(n.encode()for n in EXPORTS),'export name strings'
  elif s['type']==8:assert s['size']==t['size'],'BSS size'
  else:assert x==y,'allocated data '+sec
 # Exact attributes of every old named symbol, including duplicate locals.
 # Positions canonicalize function/object/string ownership; section symbols
 # remain checked by complete section membership and all RELA targets.
 for k,(i,s)in os.items():
  if not s['name']or s['type']==3:continue
  assert k in ns,'missing old named symbol '+str(k);j,t=ns[k]
  assert(s['type'],s['bind'],s['other'])==(t['type'],t['bind'],t['other']),('old symbol attrs',k)
  if k[0]not in CHANGED[component]|COMPACT and k[0]!='ieee80211_priv_args':assert s['size']==t['size'],('old symbol size',k)
  if old.symsection(s)=='.modinfo':
   if not s['name'].startswith('__UNIQUE_ID_srcversion'):assert body(old,s)==body(new,t),('metadata symbol payload',k)
  elif k[0]not in COMPACT:assert addr(old,old.symsection(s),s['value'])==addr(new,new.symsection(t),t['value']),('old symbol position',k)
 expected_new=set()
 if component in('wlan_scan_ap','qdrv'):pass
 else:
  expected_new|=NEW['wlan'];expected_new|={prefix+name for name in EXPORTS for prefix in('__ksymtab_','__kstrtab_','__kstrtabns_')}
 added={k[0]for k in set(ns)-set(os)if k[0]};assert added==expected_new,('new named symbols',added,expected_new)
 return dict(status='PASS_COMPLETE_WEATHER478_SOURCE34_RESIDUAL_MODULE_SCOPE',component=component,fixture_bound_functions=changed,new_functions=sorted(NEW[component]),diagnostics=diagnostics,unchanged_functions=same,residual_relocations=sum(ar.values()),old_symbols=len(old.syms),new_symbols=len(new.syms),executable_residue=padding,limits='Semanticrangesfixturebound; noinstructionequivalence/PM/CSA/RF/physicalacceptance')

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--component',choices=['qdrv','wlan_scan_ap','wlan'],required=True);a=p.parse_args();print(json.dumps(audit(Elf(a.old),Elf(a.new),a.component)))
