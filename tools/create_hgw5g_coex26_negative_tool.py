"""Derive paired Coex26 mutation tests without editing frozen CoC25 tests."""
from pathlib import Path

def main():
 original=Path(__file__).with_name('test_hgw5g_coc25_delta_negative.py');out=original.with_name('test_hgw5g_coex26_delta_negative.py');assert not out.exists();s=original.read_text().replace('audit_hgw5g_coc25_controlled_modules','audit_hgw5g_coex26_modules').replace('PASS_ELEVEN_SOURCE25_PARSED_NEGATIVE_DELTA_CASES','PASS_ELEVEN_SOURCE26_PARSED_NEGATIVE_DELTA_CASES');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
