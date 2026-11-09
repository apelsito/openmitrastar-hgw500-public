"""Actual BBDF setter/getter fake fixture and complete ARC units/ABI witness."""
import argparse
import json
from pathlib import Path
import struct

import build_f370_qdrv_module as build
from build_wlan_txmaxmpdu_alias_module import command as wcommand,run
from compile_hgw5g_cca_abi_fixture import sha
from recover_hgw5g_driver_ops import Elf


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 proof=json.loads((a.candidate/'result.json').read_text());qroot=a.candidate/'source/qdrv';assert sha(qroot/'qdrv_wlan.c')==proof['qdrv_source_sha256']
 a.output.mkdir(parents=True,exist_ok=False);result=dict(status='NO_GO',hardware_accessed=False,firmware_eligible=False)
 try:
  old_header=(build.BASE/'qdrv_wlan.h').read_text();new_header=(qroot/'qdrv_wlan.h').read_text();field='\t/* Recovered OEM483 local state; private append preserves earlier offsets. */\n\tbool om_bbdf_war_enabled;\n';assert new_header.replace(field,'',1)==old_header
  prefixes=[]
  for lane,src in [('old',build.BASE),('new',qroot)]:
   folder=a.output/lane;folder.mkdir();text=(src/'qdrv_wlan.c').read_text();prefix=text.split('/* Delay prior to enabling hang detection */',1)[0]
   extra='offsetof(struct qdrv_wlan,om_bbdf_war_enabled)'if lane=='new'else'sizeof(struct qdrv_wlan)'
   prefix+='\nconst unsigned om_bbdf_layout[]={sizeof(struct qdrv_wlan),offsetof(struct qdrv_wlan,ic),offsetof(struct qdrv_wlan,flags_ext),offsetof(struct qdrv_wlan,mac),offsetof(struct qdrv_wlan,tx_if),offsetof(struct qdrv_wlan,rx_if),offsetof(struct qdrv_wlan,sp),'+extra+'};\n'
   witness=folder/'witness.c';witness.write_text(prefix);cmd,_=build.command('qdrv_wlan',src,folder);cmd[-1]=str(witness);cmd[cmd.index('-o')+1]=str(folder/'witness.o');cmd.insert(cmd.index('-c'),'-I'+str(src));run(cmd,build.context.CONTEXT,folder/'compile-witness')
   elf=Elf(folder/'witness.o');symbol=next(s for s in elf.syms if s['name']=='om_bbdf_layout');data=elf.sections[symbol['section']]['data'][symbol['value']:symbol['value']+symbol['size']];nums=struct.unpack('<8I',data);prefixes.append(dict(zip(['size','ic','flags_ext','mac','tx_if','rx_if','sp','extension'],nums)))
  assert all(prefixes[0][k]==prefixes[1][k]for k in['ic','flags_ext','mac','tx_if','rx_if','sp']);assert prefixes[1]['extension']>=prefixes[0]['size'] and prefixes[1]['size']>prefixes[0]['size']
  folder=a.output/'new';cmd,_=build.command('qdrv_wlan',qroot,folder);run(cmd,build.context.CONTEXT,folder/'compile-actual-qdrv-unit')
  wsrc=a.candidate/'ieee80211_wireless.c';run(wcommand('ieee80211_wireless',a.output,wsrc),build.context.CONTEXT,a.output/'compile-actual-wlan-unit')
  qtext=(qroot/'qdrv_wlan.c').read_text();start=qtext.index('\tcase OM_OEM_PARAM_BBDF_WAR:');end=qtext.index('\n\tcase ',start+1);setter=qtext[start:end];start=qtext.index('\tcase OM_OEM_PARAM_BBDF_WAR:',end);end=qtext.index('\n\tcase ',start+1);getter=qtext[start:end]
  fixture='''#include <assert.h>
#include <stdint.h>
#define OM_OEM_PARAM_BBDF_WAR 483
struct qdrv_wlan {int om_bbdf_war_enabled;};
static void actual_set(struct qdrv_wlan*qw,int param,int value){switch(param){
'''+setter+'''\n default:break;}}
static void actual_get(struct qdrv_wlan*qw,int param,int*value){switch(param){
'''+getter+'''\n default:break;}}
int main(void){struct qdrv_wlan q;unsigned i;int value;for(i=0;i<65536;i++){actual_set(&q,483,(int)i);value=-1;actual_get(&q,483,&value);assert(value==!!i);actual_set(&q,483,-(int)i);value=-1;actual_get(&q,483,&value);assert(value==!!i);}return0;}
'''.replace('return0;','return 0;')
  f=a.output/'fixture.c';f.write_text(fixture);run(['gcc','-std=c11','-O1','-g','-fsanitize=address,undefined',str(f),'-o',str(a.output/'fixture')],a.output,a.output/'compile-fixture');run([str(a.output/'fixture')],a.output,a.output/'run-fixture')
  result.update(status='PASS_OFFLINE_BBDF_PREFIX_ABI_ARC_UNITS_AND_FIXTURE',layouts=prefixes,existing_private_prefix_unchanged=True,lowbool_cases=131072,fullqdrv_andwlan_changed_units_compiled=True,limit='Fullmodule rebuild/deltaqualification stillNO_GO; no firmware/runtime proof')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))


if __name__=='__main__':raise SystemExit(main())
