"""Read-only compareactivepreparedr3 toalreadyverifiedr4completepins."""
import json,hashlib
from pathlib import Path
pins=Path('/home/rea/openmitrastar-aelita-source-validation-20261022T230400Z-r4/kernel-source-pins.json');r3=Path('/home/rea/openmitrastar-aelita-source-validation-20261022T230200Z-r3/kernel-source');out=Path('/workspace/user-home/Desktop/MitraStar/outputs/rea/aelita-active-r3-input-verification-20261022T234500Z-r1');out.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
expected=json.loads(pins.read_text());bad=[]
for rel,h in expected.items():
 p=r3/rel
 if not p.is_file()or sha(p)!=h:bad.append({'path':rel,'expected':h,'actual':sha(p)if p.is_file()else None})
r={'status':'PASS_ACTIVE_R3_SOURCE_EQUALS_VERIFIED_R4_95986_PINS'if not bad else'NO_GO_ACTIVE_R3_SOURCE_DELTA','hardware_accessed':False,'read_only':True,'files_checked':len(expected),'differences':bad,'source_pins_sha256':sha(pins),'active_input':str(r3)};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
