"""ARC compiler witness for existing net80211 fields; no hardware access.

Measures the actual port ABI using retained QDRV flags. These offsets are not
OEM mappings by themselves; each proposed correspondence needs artifact proof.
"""
import argparse
import json
from pathlib import Path
import struct

import build_f370_qdrv_module as build
from compile_hgw5g_cca_abi_fixture import run,sha
from recover_hgw5g_driver_ops import Elf


FIELDS = [
 "ic_flags", "ic_opmode", "ic_extender_role", "ic_max_system_bw", "ic_bss_bw",
 "ic_obss_scan_enable", "ic_obss_scan_count", "ic_dfs_chans_available_for_cac",
 "ic_getparam", "ic_setparam", "ic_set_channel", "ic_beacon_update",
 "cca_fix_disable", "auto_cca_enable", "ic_rx_bar_sync",
 "sta_dfs_info.sta_dfs_strict_mode", "sta_dfs_info.sta_dfs_strict_msr_cac",
 "sta_dfs_info.sta_dfs_tx_chan_close_time", "ic_extender_rbs_bw",
 "ic_extender_mbs_ocac", "ic_vap_default_state", "ic_tx_max_ampdu_size",
 "ic_dyn_peer_rts", "ic_peer_rts", "ic_extender_bgscanintvl",
]
VAP = ["iv_opmode", "iv_tx_amsdu", "iv_tx_max_amsdu", "iv_coex", "iv_pmf", "iv_flags",
       "iv_flags_ext", "iv_ba_control", "iv_fixed_rate", "iv_bss", "iv_newstate"]


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False)
 source=build.BASE
 prefix=(source/"qdrv_wlan.c").read_text().split("/* Delay prior to enabling hang detection */",1)[0]
 names=["ic."+x for x in FIELDS]+["vap."+x for x in VAP]+["ic.size","vap.size"]
 expr=["offsetof(struct ieee80211com,"+x+")" for x in FIELDS]+["offsetof(struct ieee80211vap,"+x+")"for x in VAP]+["sizeof(struct ieee80211com)","sizeof(struct ieee80211vap)"]
 expr+= ["sizeof(((struct ieee80211com*)0)->"+x+")" for x in FIELDS]+["sizeof(((struct ieee80211vap*)0)->"+x+")"for x in VAP]
 names+=["ic."+x+".width"for x in FIELDS]+["vap."+x+".width"for x in VAP]
 prefix+="\nconst unsigned om_extended_layout[]={"+",".join(expr)+"};\n"
 path=a.output/"witness.c";path.write_text(prefix)
 cmd,_=build.command("qdrv_wlan",source,a.output);cmd[-1]=str(path);cmd[cmd.index("-o")+1]=str(a.output/"witness.o")
 cmd.insert(cmd.index("-c"),"-I"+str(source));run(cmd,build.context.CONTEXT,a.output/"arc-layout")
 elf=Elf(a.output/"witness.o");symbol=next(s for s in elf.syms if s["name"]=="om_extended_layout")
 data=elf.sections[symbol["section"]]["data"][symbol["value"]:symbol["value"]+symbol["size"]]
 result=dict(status="PASS_ARC_PORT_LAYOUT_NOT_OEM_MAPPING",hardware_accessed=False,fields=dict(zip(names,struct.unpack("<"+"I"*len(names),data))),witness_sha256=sha(a.output/"witness.o"))
 (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))


if __name__=="__main__":main()
