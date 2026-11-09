"""Recover OEM dev-mode getter and two faithful unsupported table entries.

This source-only candidate extends seven-entry R2 without altering that artifact.
Getter451 is proven by both existing EXTENDER_ROLE283 getter and exact OEM
REPEATER38 bit. Entries465set/495get faithfully retain OEM -EOPNOTSUPP.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--parent",type=Path,required=True);p.add_argument("--oem-get",type=Path,required=True);p.add_argument("--case-map",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 original=a.parent.read_text();assert sha(a.parent)=="20eb551bac555ecc1df370c3c33dc0509eee82fd45bb2ad43d447c3ce429f955"
 evidence=json.loads(a.oem_get.read_text());text=evidence["data"]["raw_result"]["value"]["pseudocode"]
 assert "case 0x11b:" in text and "(iVar8 + 0x5c28)" in text
 assert "case 0x1c3:" in text and "(iVar8 + 0x9c) & 0x40000" in text
 maps=json.loads(a.case_map.read_text());unsupported=[r for r in maps["records"]if (r["cmd"],r["direction"])in((465,"set"),(495,"get"))]
 assert len(unsupported)==2 and all(r["default_target"]for r in unsupported)
 macros="""/* OEM451 reports role1/2 first, else repeater3 or normal0. Two advertised
 * OEM entries below remain unsupported; adding their records enables no feature. */
#define OM_OEM_PARAM_DEVICE_MODE 451
#define OM_OEM_PARAM_IGNORE_ICAC_SELECTION 465
#define OM_OEM_PARAM_FT_OVER_DS 495

"""
 i=original.index("#define OM_OEM_PARAM_MIN_CAC");candidate=original[:i]+macros+original[i:]
 sig="ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,"
 getstart=candidate.index(sig);getbrace=candidate.index("{",candidate.index("switch (param[0] & 0xffff)",getstart))
 getcases="""
\tcase OM_OEM_PARAM_DEVICE_MODE:
\t\tif (ic->ic_extender_role == IEEE80211_EXTENDER_ROLE_MBS)
\t\t\tparam[0] = 1;
\t\telse if (ic->ic_extender_role == IEEE80211_EXTENDER_ROLE_RBS)
\t\t\tparam[0] = 2;
\t\telse
\t\t\tparam[0] = ieee80211_is_repeater(ic) ? 3 : 0;
\t\tbreak;
\tcase OM_OEM_PARAM_FT_OVER_DS:
\t\treturn -EOPNOTSUPP;
"""
 candidate=candidate[:getbrace+1]+getcases+candidate[getbrace+1:]
 setsig="ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,"
 setstart=candidate.index(setsig);setbrace=candidate.index("{",candidate.index("switch (param)",setstart))
 setcases="\n\tcase OM_OEM_PARAM_IGNORE_ICAC_SELECTION:\n\t\treturn -EOPNOTSUPP;\n"
 candidate=candidate[:setbrace+1]+setcases+candidate[setbrace+1:]
 table=candidate.index("static const struct iw_priv_args ieee80211_priv_args[]");end=candidate.index("\n};",table)
 entries='\n\t{ OM_OEM_PARAM_DEVICE_MODE,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_dev_mode" },\n\t{ OM_OEM_PARAM_IGNORE_ICAC_SELECTION,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "ignr_icac_sel" },\n\t{ OM_OEM_PARAM_FT_OVER_DS,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_ft_over_ds" },'
 candidate=candidate[:end]+entries+candidate[end:]
 assert candidate.replace(macros,"",1).replace(getcases,"",1).replace(setcases,"",1).replace(entries,"",1)==original
 a.output.mkdir(parents=True,exist_ok=False);source=a.output/"ieee80211_wireless.c";source.write_text(candidate,newline="\n")
 patch="".join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile="a/src/wlan/ieee80211_wireless.c",tofile="b/src/wlan/ieee80211_wireless.c"));(a.output/"devmode-unsupported.patch").write_text(patch,newline="\n")
 result=dict(status="SOURCE_ONLY_EIGHT_RECOVERED_OPERATIONS_TWO_FAITHFUL_UNSUPPORTED_ENTRIES",hardware_accessed=False,firmware_eligible=False,parent_sha256=sha(a.parent),candidate_sha256=sha(source),entries_total_added_to_original=10,functional_operations_added=8,faithful_unsupported_entries=2,original_table_gaps_remaining=34,oem_getparam_sha256=sha(a.oem_get),case_map_sha256=sha(a.case_map),constraints="No scans, channel, DFS, radio state or firmware commands introduced; fullmodule gate pending")
 (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))


if __name__=="__main__":main()
