"""Allpublichostprefix +private scanner append witness for SOURCE32 ARC.

Originalpublicscanstate andallpreviousprivatefieldoffsets/sizesunchanged. New
transaction lock/owner/queues/observation state append requiresownsizeofalloc.
No module/hardware/scheduler/foreigncaller lifetime acceptance.
"""
import argparse,hashlib,json,re,struct,subprocess
from pathlib import Path
import build_hgw5g_typed_header_closure as b
from witness_hgw5g_typed_vap_abi import split_struct,members
from recover_hgw5g_driver_ops import Elf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);oldscan=a.parent/'source/wlan/ieee80211_scan.c';newscan=a.candidate/'source/wlan/ieee80211_scan.c';original=b.qb.ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211'
 oldpub=a.parent/'headers/net80211/ieee80211_scan.h';oldpub=oldpub if oldpub.exists()else original/'ieee80211_scan.h';newpub=a.candidate/'headers/net80211/ieee80211_scan.h';definitions={'ieee80211_scan_state':members(split_struct(oldpub.read_text(),'struct ieee80211_scan_state {')),'scan_state':members(split_struct(oldscan.read_text(),'struct scan_state {'))};extensions=['om_chanset_lock','om_chanset_stopping','om_chanset_policy','om_chanset_owner','om_chanset','om_observations','om_channels','om_scan_detaching','om_chanset_last_error'];rows=[];omissions={};pins={str(Path(__file__)):sha(__file__),str(oldscan):sha(oldscan),str(newscan):sha(newscan),str(oldpub):sha(oldpub),str(newpub):sha(newpub)}
 for lane,src,scan,pub in [('old',a.parent,oldscan,oldpub),('new',a.candidate,newscan,newpub)]:
  folder=a.output/lane;folder.mkdir();q,w,h=src/'source/qdrv',src/'source/wlan',src/'headers';text=scan.read_text();prefix=text[:text.index('/*\n * Amount of time to go off-channel')];selected={t:list(ns)for t,ns in definitions.items()}
  while True:
   mapping=[(t,n)for t in selected for n in selected[t]];expr=[]
   for t,n in mapping:expr+=['offsetof(struct '+t+','+n+')','sizeof(((struct '+t+'*)0)->'+n+')']
   sizes=['ieee80211_scan_state','scan_state','ieee80211com','ieee80211vap','qdrv_wlan','qdrv_vap','ieee80211_beacon_offsets','ieee80211_beacon_param_t','host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t'];expr+=['sizeof(struct '+t+')'for t in sizes]
   if lane=='new':
    for n in extensions:expr+=['offsetof(struct scan_state,'+n+')','sizeof(((struct scan_state*)0)->'+n+')']
   # qdrvtypes pulledbyactualqdrvunitprefix, private scanner copiedexactly.
   qprefix='\n'.join(x for x in(q/'qdrv_wlan.c').read_text().splitlines()if x.startswith('#include'))+'\n#include <qtn/beacon_ioctl.h>\n';prefix2=prefix[prefix.index('#include <linux/version.h>'):];source=folder/'witness.c';source.write_text(qprefix+prefix2+'\nconst unsigned om_scanner32_layout[]={'+','.join(expr)+'};\n');cmd,_=b.compile_command('wlan','ieee80211_scan',folder,q,w,h);cmd[-1]=str(source);cmd[cmd.index('-o')+1]=str(folder/'witness.o');r=subprocess.run(cmd,cwd=b.qb.context.CONTEXT,capture_output=True);(folder/'compile.command.json').write_text(json.dumps(cmd,indent=2)+'\n');(folder/'compile.stderr').write_bytes(r.stderr)
   if not r.returncode:break
   text=r.stderr.decode(errors='replace');missing=[]
   for t,n in re.findall(r"(?:struct )?(ieee80211\w+|scan_state)['’].*?has no member named ['‘]([A-Za-z_]\w*)",text):
    if t in selected and n in selected[t]:selected[t].remove(n);missing.append((t,n))
   if not missing:raise RuntimeError(text[-5000:])
   omissions.setdefault(lane,[]).extend(missing)
  e=Elf(folder/'witness.o');s=next(s for s in e.syms if s['name']=='om_scanner32_layout');raw=e.sections[s['section']]['data'][s['value']:s['value']+s['size']];v=struct.unpack('<'+'I'*(len(raw)//4),raw);fields={}
  for i,(t,n)in enumerate(mapping):fields.setdefault(t,{})[n]={'offset':v[2*i],'size':v[2*i+1]}
  start=len(mapping)*2;ext={}
  if lane=='new':
   ev=v[start+len(sizes):]
   for i,n in enumerate(extensions):ext[n]={'offset':ev[2*i],'size':ev[2*i+1]}
  rows.append({'lane':lane,'fields':fields,'sizes':dict(zip(sizes,v[start:start+len(sizes)])),'extensions':ext,'object_sha256':sha(folder/'witness.o')})
  for d in b.readdeps(folder/'ieee80211_scan.d'):p=Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d;pins[str(p)]=sha(p)
 old,new=rows;assert old['fields']==new['fields'],'alloldscanner/publicfields';assert new['sizes']['scan_state']>old['sizes']['scan_state']
 for t in old['sizes']:
  if t!='scan_state':assert old['sizes'][t]==new['sizes'][t],t
 assert min(x['offset']for x in new['extensions'].values())>=old['sizes']['scan_state']
 assert new['extensions']['om_observations']['size']%255==0 and new['extensions']['om_channels']['size']%98==0
 for path,h in pins.items():assert sha(path)==h
 result={'status':'PASS_ARC_CONSOLIDATED32_PUBLIC_HOST_PREFIX_AND_PRIVATE_SCANNER_APPEND','hardware_accessed':False,'firmware_eligible':False,'rows':rows,'old_scanner_members':{t:len(old['fields'][t])for t in definitions},'new_private_extensions':new['extensions'],'dependency_pins':len(pins),'conditional_omissions':omissions,'limits':['Actualprivateallocator sizeof(scan_state) mustusecoherentnewscanunit; otheroriginalprivatefields preserved.','Usedcompilerdepshashedpostcompile thenrechecked; actualsource/headerinitialpins verified.','No module/RTNL/BHlifetime/hardwareacceptance.']};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['status','old_scanner_members','new_private_extensions','dependency_pins']},indent=2))
if __name__=='__main__':main()
