"""Derive a separate exact-control receipt admission without editing composers."""
from pathlib import Path

def main():
 original=Path(__file__).with_name('compose_hgw5g_joint_modules_dedup.py');target=Path(__file__).with_name('compose_hgw5g_exact_control_dedup.py');assert not target.exists();s=original.read_text();old='("NO_GO_TYPED_HEADER_CLOSURE", "PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA")';new='("PASS_SAME_HEADER_EXACT_SOURCE_CONTROL_OBJECT_CLOSURE",)';assert s.count(old)==1;s=s.replace(old,new,1);s=s.replace('source-built modules with one validated retained export contract','source-built exact header-control modules with one validated export contract',1);target.write_text(s,newline='\n');print(target)

if __name__=='__main__':main()
