"""Canonical jointmodpost receipt adapter for bounded467 scanrevision closure."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('compose_hgw5g_joint_modules_dedup.py');out=src.with_name('compose_hgw5g_dfs467_dedup.py');assert not out.exists();s=src.read_text();needle='("NO_GO_TYPED_HEADER_CLOSURE", "PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA")';assert needle in s;s=s.replace(needle,'("PASS_DFS467_SCAN_REVISION_PAIRED_SOURCE_CLOSURE",)',1);out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
