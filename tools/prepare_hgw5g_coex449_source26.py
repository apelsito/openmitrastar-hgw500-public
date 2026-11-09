"""Recover OEM449 policy and real OBSS/RX bandwidth consumers atop CoC25.

Only a new source directory is written. The u8 policy uses a compiler-proven
host padding byte between new CoC flags and its completed level. Do not claim
layout preservation until the full ARC old-member witness passes.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--helper',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();pp=json.loads((a.parent/'result.json').read_text());assert pp['total_original_entries_added']==25;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');changes={};patch=[]
 def change(rel,text):
  path=a.output/rel;old=path.read_text();path.write_text(text,newline='\n');changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 rel='headers/net80211/ieee80211_var.h';old=(a.output/rel).read_text();anchor='\tbool om_coc_pm_pending;\n';assert old.count(anchor)==1;new=old.replace(anchor,anchor+'\t/* OEM449 policy in unused host padding; ARC witness is mandatory. */\n\tu8 om_20_40_bss_coex;\n',1);proto='void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);';assert new.count(proto)==1;new=new.replace(proto,proto+'\nvoid om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);',1);change(rel,new)
 rel='source/qdrv/qdrv_wlan.c';old=(a.output/rel).read_text();needle='\tic->ic_obss_scan_enable = 1;';assert old.count(needle)==1;change(rel,old.replace(needle,'\tic->om_20_40_bss_coex = 1;\n'+needle,1))
 rel='source/wlan/ieee80211_node.c';old=(a.output/rel).read_text();anchor='/*\n * Restore bandwidth to initial state.\n */';assert old.count(anchor)==1;change(rel,old.replace(anchor,a.helper.read_text()+'\nEXPORT_SYMBOL(om_ieee80211_change_bw);\n\n'+anchor,1))
 rel='source/wlan/ieee80211_wireless.c';old=(a.output/rel).read_text();new=old.replace('#define OM_OEM_PARAM_COC_MOVE_NDFS 491','#define OM_OEM_PARAM_20_40_BSS_COEX 449\n#define OM_OEM_PARAM_COC_MOVE_NDFS 491',1);start=new.index('void ieee80211_start_obss_scan_timer(');end=new.index('void ieee80211_finish_csa(',start);frag=new[start:end];needle='if (!IEEE80211_IS_11NG_40(ic) || !ic->ic_obss_scan_enable)';assert frag.count(needle)==1;frag=frag.replace(needle,needle[:-1]+' ||\n\t    !READ_ONCE(ic->om_20_40_bss_coex))',1);new=new[:start]+frag+new[end:];start=new.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');switch=new.index('switch (param)',start);brace=new.index('{',switch);new=new[:brace+1]+'''\n\tcase OM_OEM_PARAM_20_40_BSS_COEX:
\t\tWRITE_ONCE(ic->om_20_40_bss_coex,(u8)!!value);
\t\treturn 0;
'''+new[brace+1:];start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);new=new[:end]+'''\n\t{ OM_OEM_PARAM_20_40_BSS_COEX,
\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,0,"20_40_bss_coex" },'''+new[end:];change(rel,new)
 rel='source/wlan/ieee80211_input.c';old=(a.output/rel).read_text();new=old
 # Check completed scan inventory and the received public coexistence action.
 needle='if (change_bw && IEEE80211_IS_11NG_40(ic)) {';assert new.count(needle)==2;new=new.replace(needle,'if (change_bw && IEEE80211_IS_11NG_40(ic) &&\n\t    READ_ONCE(ic->om_20_40_bss_coex)) {')
 wire='ieee80211_param_to_qdrv(vap, IEEE80211_PARAM_BW_SEL_MUC, BW_HT20, NULL, 0);'
 # These three sites are exactly check-mode, public-action, AP association.
 assert new.count(wire)==3;new=new.replace(wire,'om_ieee80211_change_bw(vap,BW_HT20,0);')
 # STA current-BSS HTinfo downgrade and non-HT OBSS beacon downgrade.
 needle='(ic->ic_opmode == IEEE80211_M_STA) &&\n\t\t\t\t\tIEEE80211_IS_11NG_40(ic) && vap->iv_bss &&';assert new.count(needle)==1;new=new.replace(needle,'(ic->ic_opmode == IEEE80211_M_STA) &&\n\t\t\t\t\tREAD_ONCE(ic->om_20_40_bss_coex) &&\n\t\t\t\t\tIEEE80211_IS_11NG_40(ic) && vap->iv_bss &&',1)
 wire='ieee80211_param_to_qdrv(vap,\n\t\t\t\t\t\tIEEE80211_PARAM_BW_SEL_MUC, BW_HT20, NULL, 0);';assert new.count(wire)==2;new=new.replace(wire,'om_ieee80211_change_bw(vap,BW_HT20,0);')
 needle='if (ic->ic_curmode == IEEE80211_MODE_11NG_HT40PM) {';assert new.count(needle)==1;new=new.replace(needle,'if (ic->ic_curmode == IEEE80211_MODE_11NG_HT40PM &&\n\t\t\t\t    READ_ONCE(ic->om_20_40_bss_coex)) {',1)
 needle='if ((ni->ni_coex & WLAN_20_40_BSS_COEX_40MHZ_INTOL) ||\n\t\t    (ni->ni_coex & WLAN_20_40_BSS_COEX_20MHZ_WIDTH_REQ) ||\n\t\t    (ni->ni_htcap.cap & IEEE80211_HTCAP_C_40_INTOLERANT)) {';assert new.count(needle)==1;new=new.replace(needle,'if (READ_ONCE(ic->om_20_40_bss_coex) &&\n\t\t    ((ni->ni_coex & WLAN_20_40_BSS_COEX_40MHZ_INTOL) ||\n\t\t    (ni->ni_coex & WLAN_20_40_BSS_COEX_20MHZ_WIDTH_REQ) ||\n\t\t    (ni->ni_htcap.cap & IEEE80211_HTCAP_C_40_INTOLERANT))) {',1)
 # Bound public IE lengths before reading/mutating node state. This fixes the
 # retained parser's unchecked report walk, a declared safety adaptation.
 start=new.index('ieee80211_recv_action_public_coex(');end=new.index('/*\n * Process a public action frame',start);frag=new[start:end]
 needle='if ((efrm - (u_int8_t *)ia) < sizeof(struct ieee80211_20_40_coex_param)) {';assert frag.count(needle)==1;frag=frag.replace(needle,'if (efrm - frm < sizeof(struct ieee80211_20_40_coex_param)) {',1)
 needle='if (coex_ie->param_id != IEEE80211_ELEMID_20_40_BSS_COEX) {';assert frag.count(needle)==1;frag=frag.replace(needle,'if (coex_ie->param_id != IEEE80211_ELEMID_20_40_BSS_COEX ||\n\t    coex_ie->param_len != 1) {',1)
 needle='\tni->ni_coex =  coex_ie->coex_param;';assert frag.count(needle)==1;frag=frag.replace(needle,'''\t/* A present channel report owns its declared bytes before node mutation. */
\tif (efrm - (u_int8_t *)(coex_ie + 1) >= 2 &&
\t    *((u_int8_t *)(coex_ie + 1)) == IEEE80211_ELEMID_20_40_IT_CH_REP) {
\t\tch_rep_ie = (struct ieee80211_20_40_in_ch_rep *)(coex_ie + 1);
\t\tif (ch_rep_ie->param_len < 1 ||
\t\t    ch_rep_ie->param_len > efrm - (u_int8_t *)ch_rep_ie - 2) {
\t\t\tvap->iv_stats.is_rx_elem_toosmall++;
\t\t\treturn;
\t\t}
\t}
'''+needle,1);frag=frag.replace('if (efrm - frm > 3) {','if (efrm - frm >= 3) {',1);new=new[:start]+frag+new[end:];change(rel,new)
 (a.output/'coex449-recovery.patch').write_text(''.join(patch),newline='\n');result=dict(status='SOURCE_ONLY_COEX449_REAL_TIMER_RX_BW_CONSUMERS_26_RECORDS_PENDING_GATES',hardware_accessed=False,firmware_eligible=False,total_original_entries_added=26,remaining_original_table_gaps=18,parent_manifest_sha256=sha(a.parent/'result.json'),changed_sources=changes,helper_sha256=sha(a.helper),policy='u8booldefault1; candidatepaddingoffset22667mustARCwitness',consumers=['start_obss_scan_timer','check_mode scanresult','publicaction coex','APassociationintolerance','STABSSHTinfobeacon','APnonHTOBSSbeacon'],beacon_policy='ExistingIEproducerunchanged; exactOEMflagnotusedtoremovebeaconIEs',safety_adaptation='publiccoexIElen1/reportparamlen boundedbeforemutation; originalparserOOBnotreproduced',limits='Sourceonly; fulloldmember/paddingABI, actualparse/gate/helperfixture, pairedARC/globaldelta stillrequired. NoRF/regulatory/PHY/traffic/boot/release')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
