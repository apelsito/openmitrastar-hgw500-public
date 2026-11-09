"""Create SOURCE26 receipt adapter without changing frozen canonical composer."""
from pathlib import Path

def main():
 original=Path(__file__).with_name('compose_hgw5g_joint_modules_dedup.py');out=original.with_name('compose_hgw5g_coex26_dedup.py');assert not out.exists();s=original.read_text();needle='("NO_GO_TYPED_HEADER_CLOSURE", "PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA")';assert s.count(needle)==1;s=s.replace(needle,'("PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE",)',1);out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
