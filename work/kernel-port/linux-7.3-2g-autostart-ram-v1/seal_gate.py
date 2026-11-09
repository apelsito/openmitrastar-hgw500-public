from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
for p in [HERE/'executor.py',HERE/'run.ps1',HERE/'test_executor.py',HERE/'test_new_flow.py',Path(__file__)]:
 pins[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(HERE/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
for name,digest in pins.items():
 if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Pin changed:'+name)
print('PASS_ALL_GATE_SOURCE_PINS')
