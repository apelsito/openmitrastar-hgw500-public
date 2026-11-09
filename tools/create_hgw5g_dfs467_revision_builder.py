"""Bind only the bounded467 empty-list guard revision to two fresh scan compiles."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('build_hgw5g_coex26_input_revision.py');out=src.with_name('build_hgw5g_dfs467_scan_revision.py');assert not out.exists();s=src.read_text().replace('PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE','PASS_DFS467_THREE_UNITS_PAIRED_INITIALIZED_PARENT_CLOSURE').replace('source/wlan/ieee80211_input.c','source/wlan/ieee80211_scan.c').replace("n=='ieee80211_input'","n=='ieee80211_scan'").replace('PASS_COEX26_INPUT_REVISION_PAIRED_SOURCE_CLOSURE','PASS_DFS467_SCAN_REVISION_PAIRED_SOURCE_CLOSURE').replace('retained_source26_changed_compiles=6,qualified_parent_whole_units_reused=108','retained_dfs467_changed_compiles=4,qualified_parent_whole_units_reused=110');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
