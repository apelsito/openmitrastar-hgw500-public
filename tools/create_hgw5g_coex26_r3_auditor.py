"""Separate auditor admitting actual BSS geometry body with full residual scope."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('audit_hgw5g_coex26_modules.py');out=src.with_name('audit_hgw5g_coex26_r3_modules.py');assert not out.exists();s=src.read_text();needle="'ieee80211_recv_mgmt'}}";assert s.count(needle)==1;s=s.replace(needle,"'ieee80211_recv_mgmt','ieee80211_20_40_operation_permitted'}}",1);s=s.replace('PASS_COMPLETE_COEX26_RESIDUAL_MODULE_SCOPE','PASS_COMPLETE_COEX26_R3_BSS_GEOMETRY_RESIDUAL_SCOPE');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
