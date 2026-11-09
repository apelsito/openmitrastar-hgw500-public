"""Whole R10-to-R11c WLAN residual with exact compiler diagnostic rewrites.

Only six source-changed emitted bodies and one APP copy helper are excluded
from instruction equality; fixtures bind those source helpers separately.
All remaining executable bytes including anonymous padding, data, symbol
membership/attributes/addresses and RELA are checked. No hardware acceptance.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib,json
from pathlib import Path
from qualify_f370_qdrv_module import Elf

CHANGED={'ieee80211_ioctl_setappiebuf','ieee80211_ioctl_getappiebuf','ieee80211_send_mgmt','ieee80211_get_probereq','ieee80211_vap_detach','ieee80211_beacon_update'}
NEW={'om_app_ie_copy'}
RENAME={'CSWTCH.94':'CSWTCH.89','CSWTCH.990':'CSWTCH.989','CSWTCH.993':'CSWTCH.992'}
PATCHES={'ieee80211_delete_wlanunit':[(44,226,243),(116,227,244)],'ieee80211com_media_change':[(204,29,221)],'ieee80211_ifattach':[(166,142,78),(167,2,3),(1134,14,206),(1180,78,14),(1181,4,5)],'ieee80211_get_prichan_list_by_operating_class':[(68,79,82)],'ieee80211_compile_action_measurement_11k':[(314,49,66)],'ieee80211_compile_action_measurement_11h':[(300,220,237)]}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def table(e,new=False):
 counts=Counter();r={}
 for s in e.syms:
  name=RENAME.get(s['name'],s['name'])if new else s['name'];base=(name,e.symsection(s),s['type']);k=(*base,counts[base]);counts[base]+=1;r[k]=s
 return r
def audit(op,np):
 o,n=Elf(op),Elf(np);os,ns=table(o),table(n,True);assert set(os)<=set(ns) and {k[0]for k in set(ns)-set(os)}==NEW and len(ns)-len(os)==1
 def body(e,s):return e.sections[s['section']]['data'][s['value']:s['value']+s['size']]
 def norm(name,x,y):
  z=bytearray(y)
  if name in PATCHES:
   for p,a,b in PATCHES[name]:assert x[p]==a and y[p]==b,(name,p);z[p]=a
  elif name=='ieee80211_chan2mode':
   assert len(x)==256 and len(y)==252
   assert x[10]==29 and y[10]==27;z[10]=x[10]
   assert x[38:46]==bytes.fromhex('0a22800f00003d08')and y[30:34]==bytes.fromhex('21da566a')
   assert(0x21<<6)==(0x83d+3)
   z[30:34]=b'';z[38:38]=x[38:46]
  elif name=='ieee80211_get_chanflags':
   assert len(x)==72 and len(y)==76 and x[0]==61 and y[0]==65;z[0]=61
   assert x[28:32]==bytes.fromhex('61da556a')and y[36:44]==bytes.fromhex('0a22800f0000230c')
   assert(0x61<<5)+3==0xc23
   z[36:44]=b'';z[28:28]=x[28:32]
  else:raise AssertionError('unrelated changed function '+name)
  assert bytes(z)==x,'non-diagnostic function bytes '+name
  return bytes(z)
 transforms=[];diagnostic=[];unchanged=0
 for k,s in os.items():
  t=ns[k];assert(s['type'],s['bind'],s['other'])==(t['type'],t['bind'],t['other']),('old symbol attributes',k)
  if s['type']!=2 or not s['size']:continue
  x,y=body(o,s),body(n,t)
  if k[0]in CHANGED:pass
  elif x!=y:norm(k[0],x,y);diagnostic.append(k[0])
  else:unchanged+=1
  if x!=y:transforms.append({'name':k[0],'section':o.symsection(s),'old':s['value'],'oldsize':s['size'],'new':t['value'],'newsize':t['size']})
 for k in set(ns)-set(os):
  s=ns[k];assert(s['type'],s['bind'],s['other'],n.symsection(s))==(2,0,0,'.text');transforms.append({'name':k[0],'section':'.text','old':0,'oldsize':0,'new':s['value'],'newsize':s['size']})
 assert set(diagnostic)==set(PATCHES)|{'ieee80211_chan2mode','ieee80211_get_chanflags'}
 assert {t['name']for t in transforms if t['name']in CHANGED}==CHANGED
 # Exact alignment spans inferred only when anonymous bytes contain ARC NOP.
 for t in transforms:
  if t['name'] in ['ieee80211_ioctl_getappiebuf','ieee80211_vap_detach','ieee80211_send_mgmt']:
   assert t['oldsize']%4==0 and t['newsize']%4==2
   end=t['new']+t['newsize'];assert n.byname[t['section']]['data'][end:end+2]==bytes.fromhex('e078'),('exact new padding',t['name']);t['newsize']+=2
 for sec,s in o.byname.items():
  assert sec in n.byname
  if not s['flags']&4:continue
  z=bytearray(n.byname[sec]['data'])
  for t in sorted([t for t in transforms if t['section']==sec],key=lambda x:x['new'],reverse=True):z[t['new']:t['new']+t['newsize']]=s['data'][t['old']:t['old']+t['oldsize']]
  mismatch=next((i for i in range(min(len(z),len(s['data'])))if z[i]!=s['data'][i]),None)
  assert bytes(z)==s['data'],'all residual executable/anonymous '+sec+' lengths '+str((len(z),len(s['data'])))+' first '+str(mismatch)
 def canonical(e,sec,value):
  if e is n:
   for t in sorted([t for t in transforms if t['section']==sec],key=lambda x:x['new'],reverse=True):
    if value>=t['new']+t['newsize']:value-=t['newsize']-t['oldsize']
  return(sec,value)
 def within_rewrite(e,name,relative):
  if e is o:return relative
  if name=='ieee80211_chan2mode':return 34 if relative==38 else(relative+4 if relative>=34 else relative)
  if name=='ieee80211_get_chanflags':return 36 if relative==32 else(relative-4 if relative>=44 else relative)
  return relative
 @lru_cache(maxsize=None)
 def point(e,sec,value):
  if sec=='.rodata.str1.4':return('string',e.cstring(sec,value))
  rows=[(s['size'],k,s)for k,s in(os if e is o else ns).items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']]
  if rows:
   _,k,s=min(rows,key=lambda r:r[0]);return('object',k,within_rewrite(e,k[0],value-s['value']))
  return canonical(e,sec,value)
 def reloc(e,r):
  owners=[(k,s)for k,s in(os if e is o else ns).items()if s['type']==2 and e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
  if owners and owners[0][0][0]in CHANGED|NEW:return None
  s=e.syms[r['symbol']];sec=e.symsection(s);name=RENAME.get(s['name'],s['name'])if e is n else s['name'];target=point(e,sec,s['value']+r['addend'])if s['type']==3 or sec=='.rodata.str1.4'else(name,sec,s['type'],s['bind'],r['addend']);return(point(e,r['section'],r['offset']),r['type'],target)
 a=Counter(x for r in o.relas if(x:=reloc(o,r))is not None);b=Counter(x for r in n.relas if(x:=reloc(n,r))is not None);assert a==b,'residual RELA '+str(list((a-b).elements())[:6])+str(list((b-a).elements())[:6])
 for k,s in os.items():
  t=ns[k]
  if k[0]in CHANGED or k[0]in {'ieee80211_chan2mode','ieee80211_get_chanflags'}or s['type']==3:continue
  assert s['size']==t['size'],'symbol size '+str(k)
  assert canonical(o,o.symsection(s),s['value'])==canonical(n,n.symsection(t),t['value']),'symbol value '+str(k)
 assert set(o.byname)==set(n.byname)
 for sec,s in o.byname.items():
  t=n.byname[sec];assert all(s[k]==t[k]for k in['type','flags','align','entsize']),('section metadata',sec)
  if s['flags']&4 or s['type']==4 or sec in['.symtab','.strtab','.shstrtab','.note.gnu.build-id']:continue
  assert s['size']==t['size']and s['data']==t['data'],'all allocated data '+sec
 return{'status':'PASS_R11C_COMPLETE_WLAN_RESIDUAL','changed_source_functions':sorted(CHANGED),'new_source_helper':'om_app_ie_copy','unchanged_functions':unchanged,'exact_diagnostic_functions':sorted(diagnostic),'all_residual_RELA':sum(a.values()),'old_symbols':len(os),'new_symbols':len(ns),'anonymous_executable_bytes_checked':True,'data_sections_exact':True}
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);r={'status':'NO_GO_R11C_COMPLETE_DELTA','hardware_accessed':False,'firmware_eligible':False}
 try:r=audit(a.parent,a.build);r.update(hardware_accessed=False,firmware_eligible=False)
 except Exception as ex:r['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return int(not r['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
