"""Compile ARC existingVAP prefix and enclosingQDRV offset witnesses.

Enumerates everydirect non-bitfield ieee80211vap C member before typedappend;
compiles offsetof/sizeof with original/currentheaders and matches allpriorfields.
qdrv_vap followingoffset changes are declared/recorded, never treatedcompatible
with old modules. Wirehost_ioctl/setparams/beacondesc remain unchanged witnesses.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import build_f370_qdrv_module as qb
from build_hgw5g_typed_header_closure import run
from recover_hgw5g_driver_ops import Elf

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def split_struct(text,startlabel):
 start=text.index(startlabel);brace=text.index('{',start);depth=1;i=brace+1
 while depth:
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[brace+1:i-1]
def members(body):
 body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S);body=re.sub(r'^\s*#.*$','',body,flags=re.M)
 # Declarations may include nestedmacrostructheads: use onlytailidentifier.
 result=[]
 for declaration in body.split(';'):
  declaration=declaration.strip()
  if not declaration:continue
  match=re.search(r'\(\s*\*\s*([A-Za-z_]\w*)\s*\)',declaration)
  if match:result.append(match[1]);continue
  declaration=re.sub(r'\[[^]]*\]','',declaration)
  match=re.search(r'\b([A-Za-z_]\w*)\s*$',declaration)
  if match and ':'not in declaration:result.append(match[1])
 return list(dict.fromkeys(result))

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 qsrc=a.candidate/'source/qdrv';headers=a.candidate/'headers';root=Path('/workspace/user-home/Desktop/MitraStar');origheader=root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h';newheader=headers/'net80211/ieee80211_var.h'
 oldtext=origheader.read_text();newtext=newheader.read_text();append='\t/* OEM484distinctVAP11n A-MSDUpolicy; noexistingmemberoffset changes. */\n\tu8 iv_tx_amsdu_11n;\n';assert newtext.replace(append,'',1)==oldtext
 names=members(split_struct(oldtext,'struct ieee80211vap {'))
 # MacrofakeheadTAILQ? validateoncompilerandreportomissions only genuineundefined.
 a.output.mkdir(parents=True,exist_ok=False);result=dict(status='NO_GO_ABI_WITNESS',hardware_accessed=False,firmware_eligible=False,field_names=names)
 try:
  rows=[]
  for label,overlay in [('old',None),('new',headers)]:
   folder=a.output/label;folder.mkdir();prefix=(qsrc/'qdrv_vap.c').read_text().split('static int',1)[0]
   prefix=prefix[:prefix.rfind('\n')]
   # Includesonly avoidsforeignstatic declarations; collectactualsourceinclude.
   prefix='\n'.join(line for line in(qsrc/'qdrv_vap.c').read_text().splitlines()if line.startswith('#include'))+'\n#include "qtn/beacon_ioctl.h"\n'
   expressions=['offsetof(struct ieee80211vap,'+n+')'for n in names]
   expressions+=['sizeof(((struct ieee80211vap*)0)->'+n+')'for n in names]
   anchor_fields=['ndev','muc_queued','parent','bc_lock','bc_skb','devid','qv_boff']
   qmembers=set(members(split_struct((qsrc/'qdrv_vap.h').read_text(),'struct qdrv_vap\n')))
   anchor_fields=[x for x in anchor_fields if x in qmembers]
   expressions+=['sizeof(struct ieee80211vap)','sizeof(struct qdrv_vap)']+['offsetof(struct qdrv_vap,'+x+')'for x in anchor_fields]
   expressions+=['sizeof(struct host_ioctl)','sizeof(struct qtn_setparams_args)','sizeof(struct beacon_shared_ie_t)']
   if overlay:expressions+=['offsetof(struct ieee80211vap,iv_tx_amsdu_11n)','sizeof(((struct ieee80211vap*)0)->iv_tx_amsdu_11n)']
   source=folder/'witness.c';source.write_text(prefix+'\nconst unsigned om_typed_vap_layout[]={'+','.join(expressions)+'};\n')
   cmd,_=qb.command('qdrv_vap',qsrc,folder)
   cmd[-1]=str(source);cmd[cmd.index('-o')+1]=str(folder/'witness.o');cmd[1:1]=(['-I'+str(overlay)]if overlay else [])+['-I'+str(qsrc.parent),'-I'+str(qsrc)]
   run(cmd,qb.context.CONTEXT,folder/'compile-witness');elf=Elf(folder/'witness.o');symbol=next(s for s in elf.syms if s['name']=='om_typed_vap_layout');data=elf.sections[symbol['section']]['data'][symbol['value']:symbol['value']+symbol['size']];values=struct.unpack('<'+'I'*(len(data)//4),data)
   n=len(names);row=dict(label=label,offsets=dict(zip(names,values[:n])),widths=dict(zip(names,values[n:2*n])),vap_size=values[2*n],qdrv_vap_size=values[2*n+1],qdrv_offsets=dict(zip(anchor_fields,values[2*n+2:2*n+2+len(anchor_fields)])),wire_sizes=values[2*n+2+len(anchor_fields):2*n+5+len(anchor_fields)],witness_sha256=sha(folder/'witness.o'))
   if overlay:row.update(extension_offset=values[-2],extension_width=values[-1])
   rows.append(row)
  assert rows[0]['offsets']==rows[1]['offsets']and rows[0]['widths']==rows[1]['widths'];assert rows[0]['wire_sizes']==rows[1]['wire_sizes']
  old_end=max(rows[0]['offsets'][n]+rows[0]['widths'][n]for n in names)
  assert rows[1]['extension_offset']>=old_end and rows[1]['extension_width']==1
  result.update(status='PASS_ARC_ALL_EXISTING_VAP_FIELDS_PREFIX_WIRE_UNCHANGED',rows=rows,prior_members_checked=len(names),last_existing_member_end=old_end,extension_uses_prior_tail_padding=rows[1]['extension_offset']<rows[0]['vap_size'],qdrv_vap_delta=rows[1]['qdrv_vap_size']-rows[0]['qdrv_vap_size'],limits='Actualfollowingoffsetdelta recorded; allheaderusersmuststillrebuild typedcode. NoABIsemanticcompatibilitywitholdmodulesorwireperformanceclaim.')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
