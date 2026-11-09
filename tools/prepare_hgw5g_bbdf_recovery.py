"""Source-only BBDF483 recovery with a private append-only QDRV field.

Both existing WLAN forwarding and command11/76byte parameter transport remain.
No OEM raw offset is transplanted; every pre-existing private struct member is
preserved. Candidate full QDRV/WLAN builds and ABI/delta gates remain required.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--qdrv-parent',type=Path,required=True);p.add_argument('--wlan-parent',type=Path,required=True);p.add_argument('--oem-qdrv-set',type=Path,required=True);p.add_argument('--oem-qdrv-get',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.wlan_parent)=='9e31def106b6d73ce0d350ce292521b814bb62dd6fc86ab7e5ca24ceac91d71a'
 assert sha(a.qdrv_parent/'qdrv_wlan.c')=='bd5d98aef3e1411fe93b30d195df3ea40827c403818d7fd5c629328431a6ae2f'
 setev=json.loads(a.oem_qdrv_set.read_text());getev=json.loads(a.oem_qdrv_get.read_text());assert setev['ok'] and getev['ok']
 sets=setev['data']['raw_result']['value']['pseudocode'];gets=getev['data']['raw_result']['value']['pseudocode']
 assert 'case 0x1e3:' in sets and '(iVar16 + 0x5d3d) = param_3 != 0' in sets
 assert 'param_2 == 0x1e3' in gets and "(iVar7 + 0x5d3d) != '\\0'" in gets
 a.output.mkdir(parents=True,exist_ok=False);qroot=a.output/'source/qdrv';shutil.copytree(a.qdrv_parent,qroot)
 shutil.copytree(a.qdrv_parent.parent/'wlan',a.output/'source/wlan')
 qheader=qroot/'qdrv_wlan.h';old_header=qheader.read_text();anchor='\tstruct shared_params *sp;\n};';assert old_header.count(anchor)==1
 field='\t/* Recovered OEM483 local state; private append preserves earlier offsets. */\n\tbool om_bbdf_war_enabled;\n'
 qheader.write_text(old_header.replace(anchor,'\tstruct shared_params *sp;\n'+field+'};'),newline='\n')
 qc=qroot/'qdrv_wlan.c';old_q=qc.read_text();macro='#define OM_OEM_PARAM_BBDF_WAR 483\n';new_q=old_q.replace('#define NET_IP_ALIGN 2',macro+'#define NET_IP_ALIGN 2',1)
 setstart=new_q.index('static void qdrv_wlan_80211_setparam(');brace=new_q.index('{',new_q.index('switch (param)',setstart))
 setcase='\n\tcase OM_OEM_PARAM_BBDF_WAR:\n\t\tqw->om_bbdf_war_enabled = !!value;\n\t\tbreak;\n'
 new_q=new_q[:brace+1]+setcase+new_q[brace+1:]
 getstart=new_q.index('static int qdrv_wlan_80211_getparam(');brace=new_q.index('{',new_q.index('switch (param)',getstart))
 getcase='\n\tcase OM_OEM_PARAM_BBDF_WAR:\n\t\t*value = !!qw->om_bbdf_war_enabled;\n\t\tbreak;\n'
 new_q=new_q[:brace+1]+getcase+new_q[brace+1:];assert new_q.replace(macro,'',1).replace(setcase,'',1).replace(getcase,'',1)==old_q
 qc.write_text(new_q,newline='\n')
 old_w=a.wlan_parent.read_text();new_w=old_w.replace('#define OM_OEM_PARAM_DEVICE_MODE 451',macro+'#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 setstart=new_w.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=new_w.index('{',new_w.index('switch (param)',setstart))
 wset='\n\tcase OM_OEM_PARAM_BBDF_WAR:\n\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);\n\t\tbreak;\n'
 new_w=new_w[:brace+1]+wset+new_w[brace+1:]
 getstart=new_w.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=new_w.index('{',new_w.index('switch (param[0] & 0xffff)',getstart))
 wget='\n\tcase OM_OEM_PARAM_BBDF_WAR:\n\t\tieee80211_param_from_qdrv(vap, param[0] & 0xffff, &param[0], NULL, 0);\n\t\tbreak;\n'
 new_w=new_w[:brace+1]+wget+new_w[brace+1:]
 start=new_w.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new_w.index('\n};',start)
 entries='\n\t{ OM_OEM_PARAM_BBDF_WAR,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "bbdf_war_en" },\n\t{ OM_OEM_PARAM_BBDF_WAR,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_bbdfwar_en" },'
 new_w=new_w[:end]+entries+new_w[end:];assert new_w.replace(macro,'',1).replace(wset,'',1).replace(wget,'',1).replace(entries,'',1)==old_w
 ws=a.output/'ieee80211_wireless.c';ws.write_text(new_w,newline='\n')
 diffs=''.join(difflib.unified_diff(old_header.splitlines(True),qheader.read_text().splitlines(True),fromfile='a/src/qdrv/qdrv_wlan.h',tofile='b/src/qdrv/qdrv_wlan.h'))+''.join(difflib.unified_diff(old_q.splitlines(True),new_q.splitlines(True),fromfile='a/src/qdrv/qdrv_wlan.c',tofile='b/src/qdrv/qdrv_wlan.c'))+''.join(difflib.unified_diff(old_w.splitlines(True),new_w.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'))
 (a.output/'bbdf-recovery.patch').write_text(diffs,newline='\n')
 result=dict(status='SOURCE_ONLY_BBDF_TWO_OPS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,total_original_entries_added=14,functional_ops_added=12,faithful_unsupported=2,remaining_original_table_gaps=30,nac_prototype_included=False,qdrv_source_sha256=sha(qc),qdrv_header_sha256=sha(qheader),wlan_source_sha256=sha(ws),oem_set_sha256=sha(a.oem_qdrv_set),oem_get_sha256=sha(a.oem_qdrv_get),change='Privateappend-onlybool QDRVstate; ordinaryexistingSETPARAM11 transport, noRFactivation',gates=['AllprivateQDRVprefixoffsets preserved andsizegrowth witnessed','CompleteallQDRVcunits rebuild, fulldeltaqualification','WLANtable580entries equality pluspairclosure','MuCexactfirmwarecontract andruntimegate separate'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
