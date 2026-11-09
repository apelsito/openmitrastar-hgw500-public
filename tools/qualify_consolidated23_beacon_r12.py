"""R12 whole modules against exact SOURCE23 same-header control, offline."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib,json
from pathlib import Path
from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]
CHANGED={'qdrv':{'qdrv_wlan_beacon_work'},'wlan':{'ieee80211_beacon_alloc_ie','ieee80211_add_beacon_ie_desc','ieee80211_ioctl_getappiebuf','ieee80211_ioctl_setappiebuf','ieee80211_ioctl_getparam','ieee80211_ioctl_setparam','ieee80211_beacon_update','ieee80211_add_beacon_desc_header','ieee80211_send_mgmt','ieee80211_beacon_alloc','ieee80211_add_mandatory_field','ieee80211_get_probereq','ieee80211_add_beacon_desc_ie','ieee80211_beacon_create_param','ieee80211_add_beacon_desc_mandatory_fields','ieee80211_vap_detach'}}
NEW={'qdrv':set(),'wlan':{'om_app_ie_copy','om_beacon_allocation_ready','om_beacon_chain_valid','om_beacon_descriptor_valid','om_beacon_reserved_remove','om_beacon_reserved_update','om_beacon_slot_error.isra.0','om_bss_tm_update_ie.isra.0','om_ieee80211_beacon_build_status','om_ieee80211_beacon_frame_status'}}
REN={'qdrv':{'CSWTCH.697':'CSWTCH.696'},'wlan':{'CSWTCH.94':'CSWTCH.89','CSWTCH.990':'CSWTCH.983','CSWTCH.993':'CSWTCH.986'}}
PATCH={'qdrv':{'qdrv_wlan_auth_state_change':[(628,47,59),(794,60,72),(942,71,83)],'qdrv_wlan_exit':[(958,246,2),(959,35,36)]},'wlan':{'ieee80211_delete_wlanunit':[(44,70,120),(116,71,121)],'ieee80211_ioctl_giwfreq':[(76,152,88),(77,12,13)],'ieee80211_param_from_qdrv':[(92,145,148)],'ieee80211com_media_change':[(204,93,29),(205,8,9)],'ieee80211_ifattach':[(166,142,78),(167,2,3),(1134,14,206),(1180,78,14),(1181,4,5)],'ieee80211_get_chanflags':[(42,33,36)],'ieee80211_add_wpa':[(76,82,146),(504,82,146),(854,80,144)],'ieee80211_tdls_mgmt_output':[(72,133,197)],'ieee80211_mgmt_output':[(64,68,132)],'ieee80211_chan2mode':[(44,62,65)],'ieee80211_compile_action_measurement_11h':[(300,219,237)]}}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def normpath(s):return s.replace('consolidated23-beacon-r12-control-source-20261022T204600Z-r1','consolidated23-beacon-r12-source-20261022T203200Z-r2')
def table(e,c,new=False):
 counts=Counter();r={}
 for i,s in enumerate(e.syms):
  name=REN[c].get(s['name'],s['name'])if new else s['name'];base=(name,e.symsection(s),s['type']);k=(*base,counts[base]);counts[base]+=1;r[k]=(i,s)
 return r
def audit(op,np,c):
 o,n=Elf(op),Elf(np);os,ns=table(o,c),table(n,c,True);of={k:s for k,(_,s)in os.items()if s['type']==2 and s['size']};nf={k:s for k,(_,s)in ns.items()if s['type']==2 and s['size']};assert set(of)<=set(nf)and{k[0]for k in set(nf)-set(of)}==NEW[c]
 def body(e,s):return e.sections[s['section']]['data'][s['value']:s['value']+s['size']]
 diagnostic=[];changed=[];unchanged=0;transforms=[]
 for k,s in of.items():
  t=nf[k];x,y=body(o,s),body(n,t)
  if k[0]in CHANGED[c]:changed.append(k[0])
  elif x!=y:
   z=bytearray(y)
   if k[0]in PATCH[c]:
    for p,a,b in PATCH[c][k[0]]:assert x[p]==a and y[p]==b,(k,p);z[p]=a
   elif k[0]=='ieee80211_get_prichan_list_by_operating_class':
    assert c=='wlan'and len(x)==172 and len(y)==176 and x[34]==37 and y[34]==39;z[34]=37;assert x[54:58]==bytes.fromhex('b5da546a')and y[62:70]==bytes.fromhex('0a22800f0000530b');assert(0xb5<<4)+3==0xb53
    z[62:70]=b'';z[54:54]=x[54:58]
   elif k[0]=='ieee80211_compile_action_measurement_11k':
    assert c=='wlan'and len(x)==448 and len(y)==452;assert x[76]==128 and y[76]==130 and x[274]==159 and y[274]==163;z[76]=128;z[274]=159;assert x[300:304]==bytes.fromhex('e3da546a')and y[308:316]==bytes.fromhex('0a22800f0000420e');z[308:316]=b'';z[300:300]=x[300:304]
    for pos,old,new in [(342,208,204),(364,92,90),(428,174,172),(446,54,52)]:assert x[pos]==old and z[pos]==new;z[pos]=old
   else:raise AssertionError('unrelatedfunction '+str(k))
   assert bytes(z)==x,'exactdiagnosticencoding '+str(k);diagnostic.append(k[0])
  else:unchanged+=1
  if x!=y:transforms.append({'name':k[0],'section':o.symsection(s),'old':s['value'],'oldsize':s['size'],'new':t['value'],'newsize':t['size']})
 for k in set(nf)-set(of):
  s=nf[k];transforms.append({'name':k[0],'section':n.symsection(s),'old':0,'oldsize':0,'new':s['value'],'newsize':s['size']})
 assert set(changed)==CHANGED[c]and set(diagnostic)==set(PATCH[c])|({'ieee80211_get_prichan_list_by_operating_class','ieee80211_compile_action_measurement_11k'}if c=='wlan'else set())
 # Delete exactbody+alignment spans on bothsides; allremaininganonymousbytesmatch.
 for t in transforms:
  for side,e in [('old',o),('new',n)]:
   if not t[side+'size']:continue
   end=t[side]+t[side+'size'];nextstarts=[s['value']for s in(of if side=='old'else nf).values()if e.symsection(s)==t['section']and s['value']>=end]
   if nextstarts and min(nextstarts)==end+2 and e.byname[t['section']]['data'][end:end+2]==bytes.fromhex('e078'):t[side+'size']+=2
  if c=='wlan'and t['name']=='ieee80211_beacon_update':
   end=t['old']+t['oldsize'];assert o.byname[t['section']]['data'][end:end+2]==bytes.fromhex('e078');t['oldsize']+=2
 for sec,s in o.byname.items():
  assert sec in n.byname
  if not s['flags']&4:continue
  a,b=bytearray(s['data']),bytearray(n.byname[sec]['data'])
  for k in of:
   if k[0]in diagnostic:
    old,new=of[k],nf[k]
    if o.symsection(old)==sec:
     # diagnosticbody replacement included below inmaskedranges
     pass
  for t in sorted({(t['old'],t['oldsize'])for t in transforms if t['section']==sec and t['oldsize']},reverse=True):del a[t[0]:t[0]+t[1]]
  for t in sorted({(t['new'],t['newsize'])for t in transforms if t['section']==sec and t['newsize']},reverse=True):del b[t[0]:t[0]+t[1]]
  first=next((i for i in range(min(len(a),len(b)))if a[i]!=b[i]),None)
  assert bytes(a)==bytes(b),'allresidualanonymous '+sec+' '+str((len(a),len(b)))+' first '+str(first)+' fragments '+a[max(0,(first or 0)-12):(first or 0)+16].hex()+'/'+b[max(0,(first or 0)-12):(first or 0)+16].hex()
 @lru_cache(maxsize=None)
 def point(e,sec,value):
  if sec in ['.rodata.str1.4','__ksymtab_strings']:return('string',normpath(e.cstring(sec,value)))
  choices=[(s['size'],k,s)for k,(_,s)in(os if e is o else ns).items()if s['type']in(1,2)and s['size']and e.symsection(s)==sec and s['value']<=value<s['value']+s['size']]
  if choices:
   _,k,s=min(choices,key=lambda x:x[0]);rel=value-s['value']
   if sec=='.rodata'and k[0].startswith('__func__.'):return('function_literal',body(e,s),rel)
   if e is n and k[0]=='ieee80211_get_prichan_list_by_operating_class':rel=62 if rel==58 else(rel-4 if rel>=70 else rel)
   if e is n and k[0]=='ieee80211_compile_action_measurement_11k':rel=308 if rel==304 else(rel-4 if rel>=316 else rel)
   return('object',k,rel)
  if e is n and sec=='.rodata'and c=='wlan':
   if value>=4536+14232:value-=68
   elif value>=108:value+=28
  if e is n and n.byname.get(sec,{}).get('flags',0)&4:
   original=value;value-=sum(t['newsize']-t['oldsize']for t in transforms if t['section']==sec and original>=t['new']+t['newsize'])
  return('section',sec,value)
 def reloc(e,r):
  owners=[k for k,s in(of if e is o else nf).items()if e.symsection(s)==r['section']and s['value']<=r['offset']<s['value']+s['size']]
  if owners and owners[0][0]in CHANGED[c]|NEW[c]:return None
  if c=='wlan'and r['section']=='__ksymtab':
   exp=[s for s in e.syms if s['name'].startswith('__ksymtab_')and s['value']<=r['offset']<s['value']+12]
   if exp and exp[0]['name'][10:]in NEW[c]:return None
  s=e.syms[r['symbol']];sec=e.symsection(s);name=REN[c].get(s['name'],s['name'])if e is n else s['name'];target=point(e,sec,s['value']+r['addend'])if s['type']==3 or sec in ['.rodata.str1.4','__ksymtab_strings']or(sec=='.rodata'and s['name'].startswith('__func__.'))else(name,sec,s['type'],s['bind'],r['addend']);return(point(e,r['section'],r['offset']),r['type'],target)
 a=Counter(x for r in o.relas if(x:=reloc(o,r))is not None);b=Counter(x for r in n.relas if(x:=reloc(n,r))is not None);assert a==b,'residualRELA '+str(list((a-b).elements())[:4])+str(list((b-a).elements())[:4])
 for sec,s in o.byname.items():
  t=n.byname[sec];assert all(s[k]==t[k]for k in ['type','flags','align','entsize']),('sectionmeta',sec)
  if s['flags']&4 or s['type']==4 or sec in ['.symtab','.strtab','.shstrtab','.note.gnu.build-id']:continue
  if sec=='.rodata.str1.4':
   norm=lambda z:Counter(normpath(x.decode('latin1'))for x in z.split(b'\0')if x);removed=norm(s['data'])-norm(t['data']);added=norm(t['data'])-norm(s['data']);assert not added and (not removed if c=='qdrv'else list(removed.elements())==['%s: allocated space %d is not enough for adding more ie descriptors\n'])
  elif c=='wlan'and sec in ['__ksymtab','__ksymtab_strings']:continue
  elif c=='wlan'and sec=='.rodata':
   x,y=s['data'],t['data'];assert x[108:136]==b'ieee80211_beacon_alloc_ie\0\0\0';oldtab=next(s for s in o.syms if s['name']=='ieee80211_priv_args');newtab=next(s for s in n.syms if s['name']=='ieee80211_priv_args');assert oldtab['size']==589*24 and newtab['size']==593*24
   cut=newtab['value']+oldtab['size'];assert x[:108]+x[136:]==y[:cut]+y[cut+96:],'complete rodataoutside4privrecords'
  elif c=='wlan'and sec=='.data':
   x,y=s['data'],t['data'];assert x[1356:1360]==bytes.fromhex('4d020000')and y[1356:1360]==bytes.fromhex('51020000');assert x[:1356]+x[1360:]==y[:1356]+y[1360:],'dataoutside593privcount'
  elif s['type']==8:assert s['size']==t['size']
  else:assert s['data']==t['data'],'all data '+sec
 return{'status':'PASS_CONSOLIDATED23_BEACON_R12_MATCHED_HEADER_RESIDUAL','component':c,'unchanged_functions':unchanged,'changed_source_functions':sorted(CHANGED[c]),'new_source_functions':sorted(NEW[c]),'exact_diagnostic_functions':sorted(diagnostic),'residual_RELA':sum(a.values()),'all_anonymous_executable_bytes_checked':True,'private_records':593 if c=='wlan'else None,'limits':'Changed/newsourcebodies fixturebound; full27sourceentryclaimnotphysicalops.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);r={'status':'NO_GO_CONSOLIDATED23_BEACON_R12_GLOBAL'}
 try:report={c:audit(a.control/c/(c+'.ko'),a.candidate/c/(c+'.ko'),c)for c in ['qdrv','wlan']};r={'status':'PASS_CONSOLIDATED23_BEACON_R12_QDRV_WLAN_MATCHED_HEADER_RESIDUAL','hardware_accessed':False,'firmware_eligible':False,'audits':report}
 except Exception as ex:r['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
