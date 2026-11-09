"""Bind mutation cases to actual BSS geometry residual auditor."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('test_hgw5g_coex26_delta_negative.py');out=src.with_name('test_hgw5g_coex26_r3_delta_negative.py');assert not out.exists();s=src.read_text().replace('audit_hgw5g_coex26_modules','audit_hgw5g_coex26_r3_modules').replace('PASS_ELEVEN_SOURCE26_PARSED_NEGATIVE_DELTA_CASES','PASS_ELEVEN_SOURCE26_R3_PARSED_NEGATIVE_DELTA_CASES');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
