"""Print exactnames/attrs ofadded andmissing symbols for scopedreview."""
from pathlib import Path
import json
from qualify_f370_qdrv_module import Elf
ROOT=Path(__file__).resolve().parents[1]
for c in('qdrv','wlan','wlan_scan_ap'):
 op=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2/a-joint'/c/(c+'.ko');np=ROOT/'outputs/rea/weather478-pair-20261022T234500Z-r1/a-joint'/c/(c+'.ko');old,new=Elf(op),Elf(np)
 os={s['name']for s in old.syms if s['name']};ns={s['name']for s in new.syms if s['name']}
 for label,e,keys in[('missing',old,os-ns),('added',new,ns-os)]:
  for s in e.syms:
   if s['name']in keys:print(json.dumps(dict(component=c,change=label,name=s['name'],section=e.symsection(s),type=s['type'],bind=s['bind'],size=s['size'],bytes=e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']].hex()if s['size']<80 else None)))
