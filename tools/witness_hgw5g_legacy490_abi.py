"""ARC ICtail/privateQDRV offsets andwire size witnesses for490SOURCE23."""
import argparse
import json
from pathlib import Path
import struct

import build_f370_qdrv_module as qb
from build_hgw5g_typed_header_closure import run
from recover_hgw5g_driver_ops import Elf

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);fields=['ic_phymode','ic_curmode','ic_des_mode','ic_rf_chipid','ic_opmode','ic_csw_reason','ic_set_channel'];rows=[]
 for label,src in [('old',a.parent),('new',a.candidate)]:
  folder=a.output/label;folder.mkdir();q=src/'source/qdrv';h=src/'headers';prefix='\n'.join(x for x in(q/'qdrv_wlan.c').read_text().splitlines()if x.startswith('#include'))+'\n#include "qtn/beacon_ioctl.h"\n'
  expressions=['sizeof(struct ieee80211com)','sizeof(struct qdrv_wlan)']+['offsetof(struct ieee80211com,'+f+')'for f in fields]+['offsetof(struct qdrv_wlan,'+f+')'for f in['flags_ext','mac','tx_if','rx_if','sp','om_bbdf_war_enabled','om_duplicate_rts_value']]+['sizeof(struct host_ioctl)','sizeof(struct qtn_setparams_args)','sizeof(struct beacon_shared_ie_t)']
  if label=='new':expressions+=['offsetof(struct ieee80211com,om_legacy_rate_saved_mode)','offsetof(struct ieee80211com,om_legacy_rate_fixed)']
  path=folder/'witness.c';path.write_text(prefix+'\nconst unsigned om_legacy490_layout[]={'+','.join(expressions)+'};\n');cmd,_=qb.command('qdrv_wlan',q,folder);cmd[-1]=str(path);cmd[cmd.index('-o')+1]=str(folder/'witness.o');cmd[1:1]=['-I'+str(h),'-I'+str(q.parent),'-I'+str(q)];run(cmd,qb.context.CONTEXT,folder/'compile-witness');e=Elf(folder/'witness.o');s=next(s for s in e.syms if s['name']=='om_legacy490_layout');d=e.sections[s['section']]['data'][s['value']:s['value']+s['size']];v=struct.unpack('<'+'I'*(len(d)//4),d);rows.append(dict(label=label,values=v))
 old,new=rows[0]['values'],rows[1]['values'];assert old[2:9]==new[2:9];assert old[16:19]==new[16:19];assert new[0]-old[0]==8;assert all(new[i]-old[i]==8for i in range(9,16))
 result=dict(status='PASS_ARC_LEGACY490_IC_PREFIX_WIRE_UNCHANGED_QDRV_SHIFT8',hardware_accessed=False,firmware_eligible=False,fields=fields,rows=rows,per_radio_state_zero='existingqdrv_wlan_init memset(sizeofstruct) includesappend',limits='EveryQDRVenclosingfield shifts8; allmodules/headerusersrebuild; noABIclaimwitholdQDRV/fieldclients')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
