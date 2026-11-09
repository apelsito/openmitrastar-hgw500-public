"""ARC whole-prefix witness for R9 host ic/bo/param and enclosing QDRV layouts.

Selected source/header compile context only. No modules or hardware operations.
Every directly parsed old non-bitfield member is compiler-tested for offset and
size; absent conditional members are explicitly omitted, never inferred.
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
from witness_hgw5g_typed_vap_abi import split_struct,members
from recover_hgw5g_driver_ops import Elf

ROOT=qb.ROOT

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists();a.output.mkdir(parents=True)
 qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';original=ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211'
 definitions=[('ieee80211com','ieee80211_var.h','struct ieee80211com {'),('ieee80211_beacon_offsets','ieee80211_proto.h','struct ieee80211_beacon_offsets {'),('ieee80211_beacon_param_t','ieee80211_beacon_desc.h','struct ieee80211_beacon_param_t {')]
 # Retain exact includes/order and conditional declarations from the real unit.
 prefix=(qsrc/'qdrv_wlan.c').read_text().split('/* Delay prior to enabling hang detection */',1)[0]+'\n#include <qtn/beacon_ioctl.h>\n'
 rows=[];names={name:members(split_struct((original/file).read_text(),label))for name,file,label in definitions}
 omissions={}
 for label,overlay in [('old',original),('new',headers)]:
  folder=a.output/label;folder.mkdir();selected={k:list(v)for k,v in names.items()}
  while True:
   expressions=[];mapping=[]
   for typ in selected:
    for member in selected[typ]:
     expressions.extend(['offsetof(struct '+typ+','+member+')','sizeof(((struct '+typ+'*)0)->'+member+')']);mapping.append((typ,member))
   sizes=['ieee80211com','ieee80211_beacon_offsets','ieee80211_beacon_param_t','qdrv_wlan','qdrv_vap','host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t']
   expressions.extend('sizeof(struct '+s+')'for s in sizes)
   anchors=[('qdrv_wlan',x)for x in('ic','unit','flags_ext','mac','tx_if','rx_if','sp')]+[('qdrv_vap',x)for x in('iv','ndev','muc_queued','parent','qv_boff','napi','ni_lncb_lst')]
   expressions.extend('offsetof(struct '+t+','+m+')'for t,m in anchors)
   extensions=[('ieee80211com','om_bss_tm_flags'),('ieee80211com','om_neighbor_report_flags'),('ieee80211_beacon_offsets','bo_om_rrm'),('ieee80211_beacon_param_t','om_cca_ie'),('ieee80211_beacon_param_t','om_app_ie'),('ieee80211_beacon_param_t','om_build_error')]if label=='new'else[]
   expressions.extend('offsetof(struct '+t+','+m+')'for t,m in extensions)
   source=folder/'witness.c';source.write_text(prefix+'const unsigned om_beacon_full_layout[]={'+','.join(expressions)+'};\n')
   cmd,_=compile_command('qdrv','qdrv_wlan',folder,qsrc,wsrc,overlay)
   cmd[-1]=str(source);cmd[cmd.index('-o')+1]=str(folder/'witness.o')
   proc=subprocess.run(cmd,cwd=qb.context.CONTEXT,capture_output=True)
   (folder/'compile.command.json').write_text(json.dumps(cmd,indent=2)+'\n');(folder/'compile.stderr').write_bytes(proc.stderr)
   if not proc.returncode:break
   errors=proc.stderr.decode(errors='replace')
   missing=[]
   for typ,member in re.findall(r"(?:struct )?(ieee80211\w+)['’].*?has no member named ['‘]([A-Za-z_]\w*)",errors):
    if typ in selected and member in selected[typ]:selected[typ].remove(member);missing.append((typ,member))
   if not missing:
    (a.output/'result.json').write_text(json.dumps({'status':'NO_GO_FULL_ABI_WITNESS','hardware_accessed':False,'error':errors[-5000:]},indent=2)+'\n');raise RuntimeError(errors[-5000:])
   omissions.setdefault(label,[]).extend(missing)
  e=Elf(folder/'witness.o');s=next(s for s in e.syms if s['name']=='om_beacon_full_layout');raw=e.sections[s['section']]['data'][s['value']:s['value']+s['size']];values=struct.unpack('<'+'I'*(len(raw)//4),raw)
  count=len(mapping)*2;fields={}
  for i,(t,m)in enumerate(mapping):fields.setdefault(t,{})[m]={'offset':values[2*i],'size':values[2*i+1]}
  row={'lane':label,'fields':fields,'sizes':dict(zip(sizes,values[count:count+len(sizes)])),'enclosing_offsets':{t+'.'+m:values[count+len(sizes)+i]for i,(t,m)in enumerate(anchors)},'extensions':{t+'.'+m:values[-len(extensions)+i]for i,(t,m)in enumerate(extensions)}if extensions else{},'object_sha256':sha(folder/'witness.o')};rows.append(row)
 for typ in names:assert rows[0]['fields'][typ]==rows[1]['fields'][typ],'old prefixoffset/width '+typ
 for typ in('host_ioctl','qtn_setparams_args','qtn_beacon_args','beacon_shared_ie_t'):assert rows[0]['sizes'][typ]==rows[1]['sizes'][typ],'wirechanged '+typ
 assert rows[1]['sizes']['beacon_shared_ie_t']==20 and rows[1]['sizes']['qtn_beacon_args']==64
 result={'status':'PASS_ARC_FULL_IC_BO_PARAM_PREFIX_AND_PHYSICAL_WIRE_WITNESS','hardware_accessed':False,'firmware_eligible':False,'rows':rows,'old_members_checked':{k:len(rows[0]['fields'][k])for k in names},'conditional_omissions':omissions,'physical_wire_unchanged':True,'host_enclosing_offsets_changed':rows[0]['enclosing_offsets']!=rows[1]['enclosing_offsets'],'limits':'Hostprefix preserved; enclosingQDRV layouts change and oldmodules mustnotmix. No hardware or firmwareacceptance.'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in('status','old_members_checked','conditional_omissions','physical_wire_unchanged','host_enclosing_offsets_changed')},indent=2))

if __name__=='__main__':main()
