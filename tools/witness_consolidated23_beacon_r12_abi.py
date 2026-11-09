"""All parsed SOURCE23 IC/VAP/QDRV/BO/param prefixes under combined R12 ARC.

IC extends8B, BO4B, beaconparam12B. Enclosing offsets shift only by declared
embedded extents. No firmware/headermix/runtime proof. Dependency hashes are
captured after each actual compile and verified before/after final inspection.
"""
import argparse,hashlib,json,re,struct,subprocess
from pathlib import Path
import build_hgw5g_typed_header_closure as b
from witness_hgw5g_typed_vap_abi import split_struct,members
from recover_hgw5g_driver_ops import Elf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 original=b.qb.ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211'
 defs=[('ieee80211com','headers/net80211/ieee80211_var.h','struct ieee80211com {'),('ieee80211vap','headers/net80211/ieee80211_var.h','struct ieee80211vap {'),('qdrv_wlan','source/qdrv/qdrv_wlan.h','struct qdrv_wlan {'),('qdrv_vap','source/qdrv/qdrv_vap.h','struct qdrv_vap\n{'),('ieee80211_beacon_offsets','headers/net80211/ieee80211_proto.h','struct ieee80211_beacon_offsets {'),('ieee80211_beacon_param_t','headers/net80211/ieee80211_beacon_desc.h','struct ieee80211_beacon_param_t {')]
 def header(src,file):
  p=src/file;return p if p.exists()else original/Path(file).name
 names={t:members(split_struct(header(a.parent,f).read_text(),label))for t,f,label in defs};pins={str(Path(__file__)):sha(__file__)};rows=[];omissions={};extensions=[('ieee80211com','om_bss_tm_flags'),('ieee80211com','om_neighbor_report_flags'),('ieee80211_beacon_offsets','bo_om_rrm'),('ieee80211_beacon_param_t','om_cca_ie'),('ieee80211_beacon_param_t','om_app_ie'),('ieee80211_beacon_param_t','om_build_error')]
 sizes=['ieee80211com','ieee80211vap','qdrv_wlan','qdrv_vap','ieee80211_beacon_offsets','ieee80211_beacon_param_t','host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t']
 for lane,src in [('old',a.parent),('new',a.candidate)]:
  folder=a.output/lane;folder.mkdir();qsrc=src/'source/qdrv';wsrc=src/'source/wlan';headers=src/'headers';selected={t:list(ns)for t,ns in names.items()};prefix='\n'.join(s for s in(qsrc/'qdrv_wlan.c').read_text().splitlines()if s.startswith('#include'))+'\n#include <qtn/beacon_ioctl.h>\n'
  for _,f,_ in defs:pins[str(header(src,f))]=sha(header(src,f))
  while True:
   mapping=[(t,m)for t in selected for m in selected[t]];expr=[]
   for t,m in mapping:expr+=['offsetof(struct '+t+','+m+')','sizeof(((struct '+t+'*)0)->'+m+')']
   expr+=['sizeof(struct '+t+')'for t in sizes]
   if lane=='new':expr+=['offsetof(struct '+t+','+m+')'for t,m in extensions]
   witness=folder/'witness.c';witness.write_text(prefix+'const unsigned om_r12_layout[]={'+','.join(expr)+'};\n');cmd,_=b.compile_command('qdrv','qdrv_wlan',folder,qsrc,wsrc,headers);cmd[-1]=str(witness);cmd[cmd.index('-o')+1]=str(folder/'witness.o');r=subprocess.run(cmd,cwd=b.qb.context.CONTEXT,capture_output=True);(folder/'compile.command.json').write_text(json.dumps(cmd,indent=2)+'\n');(folder/'compile.stderr').write_bytes(r.stderr)
   if not r.returncode:break
   text=r.stderr.decode(errors='replace');missing=[]
   for t,m in re.findall(r"(?:struct )?(ieee80211\w+|qdrv_\w+)['’].*?has no member named ['‘]([A-Za-z_]\w*)",text):
    if t in selected and m in selected[t]:selected[t].remove(m);missing.append((t,m))
   if not missing:raise RuntimeError(text[-5000:])
   omissions.setdefault(lane,[]).extend(missing)
  e=Elf(folder/'witness.o');s=next(s for s in e.syms if s['name']=='om_r12_layout');raw=e.sections[s['section']]['data'][s['value']:s['value']+s['size']];v=struct.unpack('<'+'I'*(len(raw)//4),raw);fields={}
  for i,(t,m)in enumerate(mapping):fields.setdefault(t,{})[m]={'offset':v[2*i],'size':v[2*i+1]}
  row={'lane':lane,'fields':fields,'sizes':dict(zip(sizes,v[2*len(mapping):2*len(mapping)+len(sizes)])),'extensions':{t+'.'+m:v[-len(extensions)+i]for i,(t,m)in enumerate(extensions)}if lane=='new'else{},'object_sha256':sha(folder/'witness.o')};rows.append(row)
  for dep in b.readdeps(folder/'qdrv_wlan.d'):
   p=Path(dep)if dep.startswith('/')else b.qb.context.CONTEXT/dep;pins[str(p)]=sha(p)
 old,new=rows
 for t in ['ieee80211com','ieee80211vap','ieee80211_beacon_offsets','ieee80211_beacon_param_t']:assert old['fields'][t]==new['fields'][t],'old prefix '+t
 for m,x in old['fields']['qdrv_wlan'].items():
  y=new['fields']['qdrv_wlan'][m]
  if m=='ic':assert x['offset']==y['offset']and y['size']==x['size']+8
  else:assert x['size']==y['size']and y['offset']==x['offset']+(8 if x['offset']>=old['fields']['qdrv_wlan']['ic']['offset']+old['sizes']['ieee80211com']else 0),(m,x,y)
 bo=old['fields']['qdrv_vap']['qv_boff']
 for m,x in old['fields']['qdrv_vap'].items():
  y=new['fields']['qdrv_vap'][m]
  if m=='qv_boff':assert x['offset']==y['offset']and y['size']==x['size']+4
  else:assert x['size']==y['size']and y['offset']==x['offset']+(4 if x['offset']>=bo['offset']+bo['size']else 0),(m,x,y)
 for t,delta in [('ieee80211com',8),('qdrv_wlan',8),('ieee80211_beacon_offsets',4),('qdrv_vap',4),('ieee80211_beacon_param_t',12)]:assert new['sizes'][t]==old['sizes'][t]+delta
 for t in ['ieee80211vap','host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t']:assert old['sizes'][t]==new['sizes'][t]
 assert list(new['extensions'].values())==[old['sizes']['ieee80211com'],old['sizes']['ieee80211com']+4,old['sizes']['ieee80211_beacon_offsets'],old['sizes']['ieee80211_beacon_param_t'],old['sizes']['ieee80211_beacon_param_t']+4,old['sizes']['ieee80211_beacon_param_t']+8]
 for path,h in pins.items():assert sha(path)==h,'witness dependency drift '+path
 result={'status':'PASS_ARC_CONSOLIDATED23_FULL_PARSED_PREFIX_AND_DECLARED_EMBEDDING_EXTENTS','hardware_accessed':False,'firmware_eligible':False,'rows':rows,'old_members_checked':{t:len(old['fields'][t])for t in names},'conditional_omissions':omissions,'dependency_pins':len(pins),'dependency_hash_scope':'Actual-used compilerdependencieshashedpostcompile thenverified; sourceheaderscheckedbeforecompile.','limits':['Fullmodule/headercontrolrebuildrequired; oldQdrv/VAPembeddingsmustnotmix.','Parsednonbitfieldprefixwitnessonly; noRFclienttrafficruntimepersistence/releaseacceptance.']};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['status','old_members_checked','dependency_pins','conditional_omissions']},indent=2))
if __name__=='__main__':main()
