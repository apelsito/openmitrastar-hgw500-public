"""Create no-layout-change ABI witness without editing frozen predecessor."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('witness_hgw5g_coex26_full_abi.py');out=src.with_name('witness_hgw5g_dfs467_full_abi.py');assert not out.exists();s=src.read_text();old="if label=='new':expressions+=['offsetof(struct ieee80211com,om_20_40_bss_coex)','sizeof(((struct ieee80211com*)0)->om_20_40_bss_coex)']";assert old in s;s=s.replace(old,"if label=='new':expressions+=[]",1).replace("extensions=list(v[-2:])if label=='new'else[]","extensions=[]")
 a=s.index(" assert new['extensions']==");b=s.index(' for path,h in pins.items():',a);s=s[:a]+s[b:];s=s.replace('PASS_ARC_COEX26_ALL_OLD_FIELDS_WIRE_SIZES_PADDING_BYTE','PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
