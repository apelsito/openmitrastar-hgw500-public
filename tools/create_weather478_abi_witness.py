"""New full ABI witness with actualformerpadding weatherflag location."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/witness_hgw5g_dfs467_full_abi.py').read_text()
s=s.replace("if label=='new':expressions+=[]","if label=='new':expressions+=['offsetof(struct ieee80211com,om_weather_cac_enabled)','sizeof(((struct ieee80211com*)0)->om_weather_cac_enabled)']")
s=s.replace('extensions=[],object_sha256','extensions=({\'weather478\':{\'offset\':v[-2],\'size\':v[-1]}}if label==\'new\'else{}),object_sha256')
s=s.replace('old,new=rows','old,new=rows\n assert new[\'extensions\'][\'weather478\']=={\'offset\':22605,\'size\':1};assert old[\'fields\'][\'ieee80211com\'][\'ic_rx_bar_sync\']=={\'offset\':22604,\'size\':1};assert old[\'fields\'][\'ieee80211com\'][\'sta_dfs_info\'][\'offset\']>=22608')
s=s.replace('PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED','PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605')
t=ROOT/'tools/witness_hgw5g_weather478_full_abi.py';assert not t.exists();t.write_text(s,newline='\n')
