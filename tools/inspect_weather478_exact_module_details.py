"""Bounded exactdiagnosticbytes andgeneratedswitchtable metadata, read-only."""
from pathlib import Path
import json
from qualify_f370_qdrv_module import Elf
ROOT=Path(__file__).resolve().parents[1]
old=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2/a-joint';new=ROOT/'outputs/rea/weather478-pair-20261022T234500Z-r1/a-joint'
for c in('qdrv','wlan','wlan_scan_ap'):
 for label,path in [('old',old),('new',new)]:
  e=Elf(path/c/(c+'.ko'))
  for s in e.syms:
   if s['name']=='qdrv_wlan_exit':print(json.dumps(dict(component=c,lane=label,name=s['name'],bytes=e.byname[e.symsection(s)]['data'][s['value']+962:s['value']+964].hex())))
   if s['name'].startswith('CSWTCH.'):
    raw=e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']];print(json.dumps(dict(component=c,lane=label,name=s['name'],bytes=s['size'],value=s['value'],body=raw.hex())))
