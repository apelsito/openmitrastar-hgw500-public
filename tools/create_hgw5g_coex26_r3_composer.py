"""Receipt adapter for two fresh geometry input compiles; canonical unchanged."""
from pathlib import Path

def main():
 p=Path(__file__).with_name('compose_hgw5g_coex26_dedup.py');out=p.with_name('compose_hgw5g_coex26_r3_dedup.py');assert not out.exists();s=p.read_text();needle='("PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE",)';assert needle in s;s=s.replace(needle,'("PASS_COEX26_INPUT_REVISION_PAIRED_SOURCE_CLOSURE",)',1);out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
