"""Derive bounded467 three-unit builder over immutable qualified29 closure."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('build_hgw5g_coex26_incremental.py');out=src.with_name('build_hgw5g_dfs467_incremental.py');assert not out.exists();s=src.read_text();s=s.replace("qual['status']=='PASS_OFFLINE_COC25_INITIALIZED_RETAINED_IC_SEVEN_MODULE_CLOSURE'and qual['reproducible']","qual['status']=='PASS_OFFLINE_CONSOLIDATED29_RECORDS_SOURCE_MODULE_CHECKPOINT'")
 s=s.replace('PASS_ARC_COEX26_ALL_OLD_FIELDS_WIRE_SIZES_PADDING_BYTE','PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED')
 s=s.replace("{'source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_input.c','source/wlan/ieee80211_node.c','source/wlan/ieee80211_wireless.c'}","{'source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c'}")
 a=s.index(" oldh=(a.parent_source/");b=s.index(" for root in('source','headers'):",a)
 s=s[:a]+" oldh=(a.parent_source/'headers/net80211/ieee80211_var.h').read_text();newh=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();normalized=newh.replace('void ieee80211_pm_queue_work(struct ieee80211com *ic); int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);','void ieee80211_pm_queue_work(struct ieee80211com *ic);');assert normalized==oldh and len(newh.splitlines())==len(oldh.splitlines())\n"+s[b:]
 s=s.replace('driver5g-ops-20261022-coc25-full-closure-r6/result.json','consolidated29-full-pair-20261022T214100Z-r2/result.json').replace("if r['component']=='wlan']","if r['component']=='wlan'and r['lane']=='a']")
 s=s.replace('PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE','PASS_DFS467_THREE_UNITS_PAIRED_INITIALIZED_PARENT_CLOSURE').replace('new_compiled_units=8,reused_units=108','new_compiled_units=6,reused_units=110').replace('54wholeparentunitsreusedperlaneonlysource/paddingABI/headerlineadmitted; fourchangedunitsfreshperlane','55wholeparentunitsreusedperlaneonlyexactsource/ABI/headerlineadmitted; threechangedunitsfreshperlane')
 out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
