"""Read-only path discovery limited to known working locations."""
from pathlib import Path
import json
base=Path('/home/rea')
for pattern in ['*r24*','*r25*','*sram*pair*','*quantenna*','*aelita*']:
 print(json.dumps({'pattern':pattern,'paths':[str(p) for p in base.glob(pattern)]}))
root=Path('/workspace/user-home/Desktop/MitraStar/repos/openmitrastar-hgw500-quantenna-5ghz-driver')
for rel in ['vendor/legacy-firmware-source','original-Quantenna-GPL','src/CURRENT']:
 p=root/rel;print(json.dumps({'path':str(p),'exists':p.exists(),'children':sorted(x.name for x in p.iterdir())[:15] if p.is_dir() else [],'text':p.read_text().strip() if p.is_file() else None}))
candidate=Path('/workspace/user-home/Desktop/MitraStar/outputs/rea/linux73-carrier-writer-candidate-20261023T053000Z-r24')
r=json.loads((candidate/'result.json').read_text())
for key in ['kernel_source','context','pins']:
 print(json.dumps({key:r.get(key)}))
for p in base.glob('*r24*'):
 for rel in ['a/source/platform/topaz/.switch_tqe.o.cmd','a/.qdrv.o.cmd','a/.qdrv.ko.cmd']:
  f=p/rel
  if f.is_file():
   text=f.read_text()
   import re
   paths=sorted(set(re.findall(r'/[^ \n]*legacy[^ \n]*|/[^ \n]*GPL[^ \n]*',text)))
   print(json.dumps({'cmd_file':str(f),'GPL_candidates':paths[:12]}))
   break
