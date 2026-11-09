"""Compiler witness for all parsed old IC/VAP/QDRV enclosing members.

SOURCE23 appends two host integers only. Prove old IC/VAP offsets and widths,
and every parsed QDRV member after embedded IC shifts by exactly eight bytes.
Conditional absent fields are explicitly reported; no hardware access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

import build_f370_qdrv_module as qb
from build_hgw5g_typed_header_closure import compile_command
from witness_hgw5g_typed_vap_abi import split_struct, members
from recover_hgw5g_driver_ops import Elf

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 definitions=[('ieee80211com','headers/net80211/ieee80211_var.h','struct ieee80211com {'),('ieee80211vap','headers/net80211/ieee80211_var.h','struct ieee80211vap {'),('qdrv_wlan','source/qdrv/qdrv_wlan.h','struct qdrv_wlan {')]
 names={typ:members(split_struct((a.parent/file).read_text(),label))for typ,file,label in definitions};rows=[];omissions={};pins={}
 for label,src in [('old',a.parent),('new',a.candidate)]:
  folder=a.output/label;folder.mkdir();qsrc=src/'source/qdrv';wsrc=src/'source/wlan';headers=src/'headers';selected={k:list(v)for k,v in names.items()}
  for _,file,_ in definitions:pins[str(src/file)]=sha(src/file)
  prefix='\n'.join(x for x in(qsrc/'qdrv_wlan.c').read_text().splitlines()if x.startswith('#include'))+'\n#include "qtn/beacon_ioctl.h"\n'
  while True:
   mapping=[(typ,m)for typ in selected for m in selected[typ]];expressions=[]
   for typ,m in mapping:expressions+=['offsetof(struct '+typ+','+m+')','sizeof(((struct '+typ+'*)0)->'+m+')']
   sizes=['ieee80211com','ieee80211vap','qdrv_wlan','qdrv_vap','host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t'];expressions+=['sizeof(struct '+t+')'for t in sizes]
   if label=='new':expressions+=['offsetof(struct ieee80211com,om_legacy_rate_saved_mode)','offsetof(struct ieee80211com,om_legacy_rate_fixed)']
   source=folder/'witness.c';source.write_text(prefix+'\nconst unsigned om_legacy23_full_layout[]={'+','.join(expressions)+'};\n');cmd,_=compile_command('qdrv','qdrv_wlan',folder,qsrc,wsrc,headers);cmd[-1]=str(source);cmd[cmd.index('-o')+1]=str(folder/'witness.o');proc=subprocess.run(cmd,cwd=qb.context.CONTEXT,capture_output=True)
   (folder/'compile.command.json').write_text(json.dumps(cmd,indent=2)+'\n');(folder/'compile.stderr').write_bytes(proc.stderr)
   if not proc.returncode:break
   errors=proc.stderr.decode(errors='replace');missing=[]
   for typ,m in re.findall(r"(?:struct )?(ieee80211\w+|qdrv_wlan)['’].*?has no member named ['‘]([A-Za-z_]\w*)",errors):
    if typ in selected and m in selected[typ]:selected[typ].remove(m);missing.append((typ,m))
   if not missing:raise RuntimeError(errors[-5000:])
   omissions.setdefault(label,[]).extend(missing)
  e=Elf(folder/'witness.o');s=next(s for s in e.syms if s['name']=='om_legacy23_full_layout');raw=e.sections[s['section']]['data'][s['value']:s['value']+s['size']];v=struct.unpack('<'+'I'*(len(raw)//4),raw);fields={}
  for i,(typ,m)in enumerate(mapping):fields.setdefault(typ,{})[m]={'offset':v[2*i],'size':v[2*i+1]}
  rows.append(dict(lane=label,fields=fields,sizes=dict(zip(sizes,v[len(mapping)*2:len(mapping)*2+len(sizes)])),extensions=list(v[-2:])if label=='new'else[],object_sha256=sha(folder/'witness.o')))
 old,new=rows
 for typ in('ieee80211com','ieee80211vap'):assert old['fields'][typ]==new['fields'][typ],typ+' prefix drift'
 assert set(old['fields']['qdrv_wlan'])==set(new['fields']['qdrv_wlan'])
 for m,x in old['fields']['qdrv_wlan'].items():
  y=new['fields']['qdrv_wlan'][m]
  if m=='ic':assert x['offset']==y['offset']and y['size']==x['size']+8
  else:assert x['size']==y['size']and y['offset']==x['offset']+(8 if x['offset']>=old['sizes']['ieee80211com']else 0),(m,x,y)
 assert new['sizes']['ieee80211com']==old['sizes']['ieee80211com']+8 and new['sizes']['qdrv_wlan']==old['sizes']['qdrv_wlan']+8
 for typ in sizes:
  if typ not in('ieee80211com','qdrv_wlan'):assert old['sizes'][typ]==new['sizes'][typ],typ+' size drift'
 assert new['extensions']==[old['sizes']['ieee80211com'],old['sizes']['ieee80211com']+4]
 for path,h in pins.items():assert sha(path)==h,'witness input drift'
 pins[str(Path(__file__))]=sha(__file__);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
 result=dict(status='PASS_ARC_LEGACY23_ALL_PARSED_IC_VAP_PREFIX_QDRV_SHIFT8_WIRE',hardware_accessed=False,firmware_eligible=False,rows=rows,old_members_checked={typ:len(old['fields'][typ])for typ in names},conditional_omissions=omissions,limits='Parsed nonbitfield host members witnessed; whole source/header control rebuild required. Old QDRV layouts must never mix; no RF or physical acceptance.')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in('status','old_members_checked','conditional_omissions')}))

if __name__=='__main__':main()
