"""Create R3 qualifier binding two new geometry compiles and actualmath proofs."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('qualify_hgw5g_coex26_closure.py');out=src.with_name('qualify_hgw5g_coex26_r3_closure.py');assert not out.exists();s=src.read_text().replace('from audit_hgw5g_coex26_modules','from audit_hgw5g_coex26_r3_modules').replace("with_name('audit_hgw5g_coex26_modules.py')","with_name('audit_hgw5g_coex26_r3_modules.py')")
 old="assert br['status']=='PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE'and br['new_compiled_units']==8 and br['reused_units']==108 and br['reproducible']";new="assert br['status']=='PASS_COEX26_INPUT_REVISION_PAIRED_SOURCE_CLOSURE'and br['new_input_compiles']==2 and br['retained_source26_changed_compiles']==6 and br['qualified_parent_whole_units_reused']==108 and br['reproducible']";assert old in s;s=s.replace(old,new)
 s=s.replace("assert proof[0]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_input.c')and proof[2]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_wireless.c')","assert proof[0]['source_sha256']==sha(ROOT/'outputs/rea/coex449-source26-stable-lines-20261022T192000Z-r2/source/wlan/ieee80211_input.c')and proof[2]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_wireless.c')")
 anchor="  review=read(a.review);assert review['status'].startswith('PASS_')and not review['hardware_accessed'];"
 insert="""  geometry=[]
  for folder,status in [('coex449-source26-bss-geometry-fixture-20261022T192700Z-r1','PASS_ACTUAL_COEX26_OEM_BSS_LOW16_SIGNED8_GEOMETRY'),('coex449-source26-public-bss-geometry-20261022T192800Z-r2','PASS_ACTUAL_COEX26_PUBLIC_PARSER_WITH_BSS_GEOMETRY')]:
   d=ROOT/'outputs/rea'/folder;r=read(d/'result.json');assert r['status']==status and r['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_input.c');geometry.append(r);import_pins(d/'input-pins.json')
   for f in d.iterdir():
    if f.is_file():pins[str(f)]=sha(f)
"""
 assert anchor in s;s=s.replace(anchor,insert+anchor,1);s=s.replace("review['status'].startswith('PASS_')","review['status']=='PASS_INDEPENDENT_COEX26_R3_BSS_GEOMETRY_AND_CONSUMER_SOURCE_SCOPE_PENDING_MODULES'",1)
 s=s.replace('driver5g-ops-20261022-coex26-negative-audit-r1','driver5g-ops-20261022-coex26-r3-negative-audit-r1').replace('PASS_ELEVEN_SOURCE26_PARSED_NEGATIVE_DELTA_CASES','PASS_ELEVEN_SOURCE26_R3_PARSED_NEGATIVE_DELTA_CASES')
 s=s.replace('PASS_OFFLINE_COEX26_REAL_TIMER_RX_BW_CONSUMER_MODULE_CLOSURE','PASS_OFFLINE_COEX26_R3_OEM_BSS_GEOMETRY_TIMER_RX_BW_MODULE_CLOSURE')
 s=s.replace('changed_units_compiled=8,','new_input_compiles=2,retained_source26_changed_compiles=6,')
 s=s.replace("negative_cases=11,pins_verified=","geometry_pair_cases=geometry[0]['pair_cases'],geometry_report_cases=geometry[0]['report_cases'],actual_parser_geometry_cases=geometry[1]['cases'],negative_cases=11,pins_verified=")
 out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
