"""Strict30→32modulecode/data/symbol/RELA scope withscannerbodyfixturebindings.

Everyoldnamedfunctionoutsideexplicit461changes retainsbytes (exactlinepatches
only); everyanonymousnonNOPgap/body remainsbound. Newtables areexact130×80B
andallhostdata outsidedeclaredobjects/2WEXTrecords remainschecked. NoHW.
"""
from collections import Counter
from functools import lru_cache
import hashlib,json,argparse
from pathlib import Path
from qualify_f370_qdrv_module import Elf
CHANGED={'wlan':{'__ieee80211_newstate.isra.0','scan_restart_pwrsav','send_probes','scan_next','_ieee80211_cancel_scan','ieee80211_ioctl_getparam','ieee80211_ioctl_setparam','ieee80211_scan_detach','ieee80211_start_scan','ieee80211_scan_vdetach','ieee80211_scan_attach'},'wlan_scan_ap':{'ap_pick_channel','ap_end','unlock_ap_list.isra.0','ap_detach'}}
NEW={'wlan':{'change_channel.part.0','om_chanset_add_scan_type','om_chanset_cost','om_chanset_edges','om_chanset_end','om_chanset_find','om_chanset_kernel_active','om_chanset_kernel_allowed','om_chanset_kernel_cancel','om_chanset_kernel_finished','om_chanset_kernel_pick','om_chanset_kernel_policy','om_chanset_kernel_scan_type','om_chanset_kernel_start','om_chanset_normalize_sample','om_chanset_prepare','om_chanset_rank','om_chanset_rank_defaults','om_chanset_scan_advance','om_chanset_scan_request','om_chanset_scan_sample','om_chanset_select','om_chanset_template','om_chanset_update_scan_entry','om_cs_neighbor_record','om_cs_scale'},'wlan_scan_ap':set()}
EXPORTS={'om_chanset_kernel_active','om_chanset_kernel_allowed','om_chanset_kernel_cancel','om_chanset_kernel_finished','om_chanset_kernel_pick','om_chanset_kernel_policy','om_chanset_kernel_scan_type','om_chanset_kernel_start'}
REN={'CSWTCH.1121':'CSWTCH.672','CSWTCH.1119':'CSWTCH.670','CSWTCH.1175':'CSWTCH.726','CSWTCH.1158':'CSWTCH.709','CSWTCH.1173':'CSWTCH.724','CSWTCH.1108':'CSWTCH.659'}
DIAG={'ieee80211_newstate':[(350,167,171)],'ieee80211_delete_wlanunit':[(44,141,150),(116,142,151)],'ieee80211_ioctl_giwfreq':[(76,216,24),(77,13,14)],'ieee80211_param_from_qdrv':[(92,150,151)],'ieee80211_should_scan':[(144,9,10)]}
TABLES={'om_cs_band5_bw160':1280,'om_cs_band24_bw20':1120,'om_cs_band24_bw40':1440,'om_cs_band5_bw20':2400,'om_cs_band5_bw40':2240,'om_cs_band5_bw80':1920,'span.2':8,'weight.0':8}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def normpath(s):return s.replace('consolidated29-source-20261022T212500Z-r1','consolidated32-source-20261022T222600Z-r2').replace('consolidated30-source-20261022T221100Z-r2','consolidated32-source-20261022T222600Z-r2')
def table(e,c,new=False):
 counts=Counter();out={}
 for i,s in enumerate(e.syms):
  name=REN.get(s['name'],s['name'])if new and c=='wlan'else s['name'];base=(name,e.symsection(s),s['type']);k=(*base,counts[base]);counts[base]+=1;out[k]=(i,s)
 return out
def body(e,s):return e.sections[s['section']]['data'][s['value']:s['value']+s['size']]
def audit(old,new,c):
 os,ns=table(old,c),table(new,c,True);of={k:s for k,(_,s)in os.items()if s['type']==2 and s['size']};nf={k:s for k,(_,s)in ns.items()if s['type']==2 and s['size']};assert set(of)<=set(nf)and{k[0]for k in set(nf)-set(of)}==NEW[c];changed=[];diag=[];same=0
 for k,s in of.items():
  t=nf[k];x,y=body(old,s),body(new,t)
  if k[0]in CHANGED[c]:changed.append(k[0])
  elif x!=y:
   assert c=='wlan'and k[0]in DIAG and len(x)==len(y),('unrelatedfunction',k);z=bytearray(y)
   for p,a,b in DIAG[k[0]]:assert x[p]==a and y[p]==b,(k,p);z[p]=a
   assert bytes(z)==x,'nondiagnosticbyte '+str(k);diag.append(k[0])
  else:same+=1
 assert set(changed)==CHANGED[c]and set(diag)==(set(DIAG)if c=='wlan'else set())
 # Preserveanonymousblocks, allunownedfunctiontails; exactNOPdelta frozen.
 gaps=[]
 for sec,s in old.byname.items():
  if not s['flags']&4:continue
  def unowned(e,fs):
   rows={};p=0;data=e.byname[sec]['data']
   for k,s in sorted(fs.items(),key=lambda kv:kv[1]['value']):
    if e.symsection(s)!=sec:continue
    if s['value']>p:
     raw=data[p:s['value']];n=0
     while raw.startswith(bytes.fromhex('e078')):raw=raw[2:];n+=2
     rows[k]=(raw,n)
    p=max(p,s['value']+s['size'])
   if p<len(data):rows[('__tail__',sec,2,0)]=(data[p:],0)
   return rows
  ag,bg=unowned(old,of),unowned(new,nf);a=Counter(x for x,n in ag.values()if x);b=Counter(x for x,n in bg.values()if x);assert a==b,'anonymousbytes '+sec
  for k,(raw,n)in ag.items():
   if raw:assert k in bg and raw==bg[k][0],'anonymousowner '+str(k)
  an,bn=sum(n for _,n in ag.values()),sum(n for _,n in bg.values());assert bn-an==(28 if c=='wlan'and sec=='.text'else 0),('exactNOPdelta',c,sec,an,bn);gaps.append({'section':sec,'old_nop_bytes':an,'new_nop_bytes':bn,'old_anonymous_bytes':sum(len(x)for x in a.elements()),'anonymous_owner_exact':True})
 @lru_cache(maxsize=None)
 def owner(e,sec,v):
  rows=[(s['size'],k,s)for k,(_,s)in(os if e is old else ns).items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=v<s['value']+s['size']];return min(rows,key=lambda x:x[0])if rows else None
 @lru_cache(maxsize=None)
 def addr(e,sec,v):
  if sec in['.rodata.str1.4','__ksymtab_strings']:return('string',normpath(e.cstring(sec,v)))
  if c=='wlan'and sec=='.rodata'and ((e is old and v==2236)or(e is new and v==12652)):
   assert old.byname['.rodata']['data'][2236:2240]==b'an\0\0'and new.byname['.rodata']['data'][12652:12656]==b'\0\0\0\0';return('diagnostic_preceding_string_region',-4)
  row=owner(e,sec,v)
  if row:
   _,k,s=row
   if sec=='.rodata'and k[0].startswith('__func__.'):return('function_literal',body(e,s),v-s['value'])
   return('object',k,v-s['value'])
  if sec in e.byname and e.byname[sec]['flags']&4:
   p=0;fs=of if e is old else nf
   for k,s in sorted(fs.items(),key=lambda kv:kv[1]['value']):
    if e.symsection(s)!=sec:continue
    if p<=v<s['value']:
     raw=e.byname[sec]['data'][p:s['value']];n=0
     while raw.startswith(bytes.fromhex('e078')):raw=raw[2:];n+=2
     return('anonymous',k,v-p-n)
    p=max(p,s['value']+s['size'])
  if e is new and c=='wlan'and sec=='.rodata':
   if v>=14952+14352:v-=10464
   elif v>=12656:v-=10416
  return('section',sec,v)
 def export(e,r):return next((s['name'][10:]for s in e.syms if r['section']=='__ksymtab'and s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+12),None)
 def rel(e,r):
  owned=owner(e,r['section'],r['offset'])
  if owned and owned[1][0]in CHANGED[c]|NEW[c]:return None
  if c=='wlan'and export(e,r)in EXPORTS:return None
  s=e.syms[r['symbol']];sec=e.symsection(s);name=REN.get(s['name'],s['name'])if e is new and c=='wlan'else s['name'];target=addr(e,sec,s['value']+r['addend'])if s['type']==3 or sec in['.rodata.str1.4','__ksymtab_strings']else(name,sec,s['type'],s['bind'],r['addend']);return(addr(e,r['section'],r['offset']),r['type'],target)
 ar=Counter(v for r in old.relas if(v:=rel(old,r))is not None);br=Counter(v for r in new.relas if(v:=rel(new,r))is not None);assert ar==br,'allresidualRELA '+str(list((ar-br).elements())[:5])+str(list((br-ar).elements())[:5])
 assert set(old.byname)==set(new.byname)
 for sec,s in old.byname.items():
  t=new.byname[sec];assert all(s[x]==t[x]for x in['type','flags','align','entsize']),('sectionmeta',sec)
  if s['flags']&4 or s['type']==4 or sec in['.symtab','.strtab','.shstrtab','.note.gnu.build-id']:continue
  x,y=s['data'],t['data']
  if sec=='.modinfo':
   info=lambda z:Counter(v for v in z.split(b'\0')if v and not v.startswith(b'srcversion='));assert info(x)==info(y),'allmodinfooutsidegeneratedsrcversion'
  elif sec=='.rodata.str1.4':strs=lambda z:Counter(normpath(v.decode('latin1'))for v in z.split(b'\0')if v);assert strs(x)==strs(y),'allstrings'
  elif c=='wlan'and sec=='.rodata':
   additions=[]
   for name,size in TABLES.items():
    s=next(s for s in new.syms if s['name']==name);assert s['size']==size;additions.append((s['value'],size))
   oldtab=next(s for s in old.syms if s['name']=='ieee80211_priv_args');newtab=next(s for s in new.syms if s['name']=='ieee80211_priv_args');assert oldtab['size']==596*24 and newtab['size']==598*24;additions.append((newtab['value']+oldtab['size'],48));z=bytearray(y)
   for p,n in sorted(additions,reverse=True):del z[p:p+n]
   assert bytes(z)==x,'allrodataoutside130tables/2privrecords'
  elif c=='wlan'and sec=='.data':
   p=next(s for s in old.syms if s['name']=='ieee80211_iw_handler_def')['value']+8;z=bytearray(y);assert int.from_bytes(x[p:p+2],'little')==596 and int.from_bytes(y[p:p+2],'little')==598;z[p:p+2]=x[p:p+2];assert x==bytes(z),'all dataoutsideprivatecount'
  elif c=='wlan'and sec in['__ksymtab','__ksymtab_strings']:
   oldexp={s['name'][10:]for s in old.syms if s['name'].startswith('__ksymtab_')};newexp={s['name'][10:]for s in new.syms if s['name'].startswith('__ksymtab_')};assert newexp-oldexp==EXPORTS and oldexp<=newexp
   if sec=='__ksymtab':
    z=bytearray(y)
    for s in sorted([s for s in new.syms if s['name'].startswith('__ksymtab_')and s['name'][10:]in EXPORTS],key=lambda s:s['value'],reverse=True):del z[s['value']:s['value']+12]
    assert bytes(z)==x
  elif s['type']==8:assert s['size']==t['size']
  else:assert x==y,'allocateddata '+sec
 for k,(i,s)in os.items():
  if not s['name']or s['type']==3:continue
  if old.symsection(s)=='.rodata'and k[0].startswith('__func__.'):
   literal=body(old,s);candidates=[t for t in new.syms if new.symsection(t)=='.rodata'and t['name'].startswith('__func__.')and body(new,t)==literal];assert candidates,('oldliteral',k);t=candidates[0]
  else:assert k in ns,('missingoldsym',k);_,t=ns[k]
  assert(s['type'],s['bind'],s['other'],old.symsection(s))==(t['type'],t['bind'],t['other'],new.symsection(t)),('oldsymattrs',k)
  if k[0]not in CHANGED[c]and k[0]!='ieee80211_priv_args':assert s['size']==t['size'],('oldsymwidth',k)
  assert addr(old,old.symsection(s),s['value'])==addr(new,new.symsection(t),t['value']),('oldsymaddr',k)
 if c=='wlan':
  for name in EXPORTS:
   s=next(s for s in new.syms if s['name']==name);assert(s['type'],s['bind'],s['other'],new.symsection(s))==(2,1,0,'.text');record=next(s for s in new.syms if s['name']=='__ksymtab_'+name);assert(record['size'],record['type'],record['bind'],record['other'],new.symsection(record))==(12,1,0,0,'__ksymtab');rr={r['offset']-record['value']:r for r in new.relas if r['section']=='__ksymtab'and record['value']<=r['offset']<record['value']+12};assert set(rr)=={0,4,8};assert new.syms[rr[0]['symbol']]['name']==name
   for p,v in[(4,name),(8,'')]:r=rr[p];s=new.syms[r['symbol']];assert new.cstring(new.symsection(s),s['value']+r['addend'])==v
  for name in TABLES:
   s=next(s for s in new.syms if s['name']==name);assert(s['type'],s['bind'],s['other'],new.symsection(s))==(1,0,0,'.rodata')
  expected=NEW[c]|set(TABLES)|{p+name for p in['__ksymtab_','__kstrtab_','__kstrtabns_']for name in EXPORTS}
 else:expected={'om_chanset_kernel_active','om_chanset_kernel_allowed','om_chanset_kernel_finished','om_chanset_kernel_pick'}
 additions={s['name']for s in new.syms if s['name']}-{s['name']for s in old.syms if s['name']}
 removed={s['name']for s in old.syms if s['name']}-{s['name']for s in new.syms if s['name']}
 if c=='wlan':assert removed==set(REN.values());additions-=set(REN)
 else:assert not removed
 assert additions==expected,('exactnewnamedmembership',additions^expected)
 return{'status':'PASS_CONSOLIDATED32_COMPLETE_CODE_DATA_SYMBOL_RELA_SCOPE','component':c,'same_functions':same,'source_changed_functions':sorted(CHANGED[c]),'source_new_functions':sorted(NEW[c]),'diagnostic_functions':diag,'residual_relocations':sum(ar.values()),'anonymous_gaps':gaps,'old_symbols':len(old.syms),'new_symbols':len(new.syms),'limits':'Changed/newsourcefunctionsfixturebound; nooriginaluniversalmetric/lifetime/RFproof.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--component',choices=['wlan','wlan_scan_ap'],required=True);a=p.parse_args();print(json.dumps(audit(Elf(a.parent),Elf(a.candidate),a.component),indent=2))
