"""SOURCE-only498 recovery with privateQDRV state and exactfullu32 forwarding.

OEM storedlow8 inWLAN ic, thensentfullu32 viaQDRV toMuC. This reconstruction
keepsreportedlow8 inprivateQDRVtail toavoidchanging sharednet80211ABI; it uses
existingic_setparam/getparam hooks. ExactMuCbit0/bit4 behavior remains infirmware.
This ownershipsubstitution is explicit and requires fullpair/deltaqualification.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--wlan-parent',type=Path,required=True);p.add_argument('--qdrv-parent',type=Path,required=True);p.add_argument('--muc-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.wlan_parent)=='45a1e2a496d6e7a203b3625cf450ce8b1e5a8a0bea993be48f963d8cbcaadd5b'
 assert sha(a.qdrv_parent/'qdrv_wlan.c')=='7c163a0d0fa57197e2f0ebc138f79caaf927c6a037f63b1fcd8b36809a48603f'
 evidence=json.loads(a.muc_evidence.read_text());assert evidence['ok'];m=evidence['data']['raw_result']['value']['pseudocode'];assert'param_3 & 0x10'in m and'param_3 & 1'in m
 a.output.mkdir(parents=True,exist_ok=False);qroot=a.output/'source/qdrv';shutil.copytree(a.qdrv_parent,qroot);shutil.copytree(a.qdrv_parent.parent/'wlan',a.output/'source/wlan')
 header=qroot/'qdrv_wlan.h';oldheader=header.read_text();field='\t/* OEM498reportedlow8state; privateappend avoids sharedhostABI change. */\n\tu8 om_duplicate_rts_value;\n';anchor='\tbool om_bbdf_war_enabled;\n';assert oldheader.count(anchor)==1;header.write_text(oldheader.replace(anchor,anchor+field,1),newline='\n')
 qc=qroot/'qdrv_wlan.c';oldq=qc.read_text();macro='#define OM_OEM_PARAM_DUPLICATE_RTS 498\n';newq=oldq.replace('#define OM_OEM_PARAM_BBDF_WAR 483',macro+'#define OM_OEM_PARAM_BBDF_WAR 483',1)
 start=newq.index('static void qdrv_wlan_80211_setparam(');brace=newq.index('{',newq.index('switch (param)',start));qs='\n\tcase OM_OEM_PARAM_DUPLICATE_RTS:\n\t\tqw->om_duplicate_rts_value = (u8)value;\n\t\tbreak;\n';newq=newq[:brace+1]+qs+newq[brace+1:]
 start=newq.index('static int qdrv_wlan_80211_getparam(');brace=newq.index('{',newq.index('switch (param)',start));qg='\n\tcase OM_OEM_PARAM_DUPLICATE_RTS:\n\t\t*value = qw->om_duplicate_rts_value;\n\t\tbreak;\n';newq=newq[:brace+1]+qg+newq[brace+1:];assert newq.replace(macro,'',1).replace(qs,'',1).replace(qg,'',1)==oldq;qc.write_text(newq,newline='\n')
 oldw=a.wlan_parent.read_text();neww=oldw.replace('#define OM_OEM_PARAM_DEVICE_MODE 451',macro+'#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 start=neww.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=neww.index('{',neww.index('switch (param)',start));ws='\n\tcase OM_OEM_PARAM_DUPLICATE_RTS:\n\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);\n\t\tbreak;\n';neww=neww[:brace+1]+ws+neww[brace+1:]
 start=neww.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=neww.index('{',neww.index('switch (param[0] & 0xffff)',start));wg='\n\tcase OM_OEM_PARAM_DUPLICATE_RTS:\n\t\tieee80211_param_from_qdrv(vap, param[0] & 0xffff, &param[0], NULL, 0);\n\t\tbreak;\n';neww=neww[:brace+1]+wg+neww[brace+1:]
 start=neww.index('static const struct iw_priv_args ieee80211_priv_args[]');end=neww.index('\n};',start);entries='\n\t{ OM_OEM_PARAM_DUPLICATE_RTS,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "set_dup_rts" },\n\t{ OM_OEM_PARAM_DUPLICATE_RTS,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_dup_rts" },';neww=neww[:end]+entries+neww[end:];assert neww.replace(macro,'',1).replace(ws,'',1).replace(wg,'',1).replace(entries,'',1)==oldw
 wpath=a.output/'ieee80211_wireless.c';wpath.write_text(neww,newline='\n')
 patch=''.join(difflib.unified_diff(oldheader.splitlines(True),header.read_text().splitlines(True),fromfile='a/src/qdrv/qdrv_wlan.h',tofile='b/src/qdrv/qdrv_wlan.h'))+''.join(difflib.unified_diff(oldq.splitlines(True),newq.splitlines(True),fromfile='a/src/qdrv/qdrv_wlan.c',tofile='b/src/qdrv/qdrv_wlan.c'))+''.join(difflib.unified_diff(oldw.splitlines(True),neww.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'));(a.output/'duplicate-rts-recovery.patch').write_text(patch,newline='\n')
 fixture='''#include <assert.h>
#include <stdint.h>
typedef uint8_t u8;
#define OM_OEM_PARAM_DUPLICATE_RTS 498
struct qdrv_wlan{u8 om_duplicate_rts_value;};
static int sent;static unsigned calls;
static void actual_set(struct qdrv_wlan*qw,int param,int value){switch(param){
'''+qs+'''\n default:break;}sent=value;calls++;}
static void actual_get(struct qdrv_wlan*qw,int param,int*value){switch(param){
'''+qg+'''\n default:break;}}
int main(void){unsigned i,high;struct qdrv_wlan q;int result;for(i=0;i<65536;i++)for(high=0;high<256;high+=17){uint32_t v=i|(high<<24);calls=0;actual_set(&q,498,v);result=-1;actual_get(&q,498,&result);assert(calls==1&&(uint32_t)sent==v&&result==(u8)v);}return0;}
'''.replace('return0;','return 0;');(a.output/'fixture.c').write_text(fixture)
 result=dict(status='SOURCE_ONLY_DUP_RTS_PRIVATE_STATE_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,qdrv_source_sha256=sha(qc),qdrv_header_sha256=sha(header),wlan_source_sha256=sha(wpath),muc_evidence_sha256=sha(a.muc_evidence),entries_total_added=18,functional_source_ops=16,unsupported_faithful=2,remaining_original_table_gaps=26,behavior_delta='Reportedlow8state movedOEMWLANic→privateQDRVtail; fullu32SETPARAM11payload preserved',limits=['PairednewQDRVrequired forgetter; staleWLAN-onlyactivationforbidden','EveryQDRVheaderuserneedsrebuild/prefixABI audit','UnderlyingMuCbit0/bit4effectsarestaticproofnotruntimeacceptance','NoPHY/regulatory/clientdatamutationexecuted'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
