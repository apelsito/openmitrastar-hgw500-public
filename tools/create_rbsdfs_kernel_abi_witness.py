"""MeasureappendedkernelRBSstate andeveryoldhostfield/enclosingQDRVshift."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/witness_hgw5g_dfs467_full_abi.py').read_text()
s=s.replace("if label=='new':expressions+=[]","if label=='new':expressions+=['offsetof(struct ieee80211com,om_rbsdfs)','sizeof(((struct ieee80211com*)0)->om_rbsdfs)']")
s=s.replace('extensions=[],object_sha256','extensions=({\'rbsdfs\':{\'offset\':v[-2],\'size\':v[-1]}}if label==\'new\'else{}),object_sha256')
s=s.replace('assert delta==0','assert delta>0 and delta<=256;assert new[\'extensions\'][\'rbsdfs\'][\'offset\']==old[\'sizes\'][\'ieee80211com\']and new[\'extensions\'][\'rbsdfs\'][\'size\']==delta')
s=s.replace('PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED','PASS_ARC_RBSDFS_OLD_HOST_PREFIX_WIRE_ABI_AND_EXACT_APPEND_SHIFT')
t=ROOT/'tools/witness_hgw5g_rbsdfs_kernel_abi.py';assert not t.exists();t.write_text(s,newline='\n')
