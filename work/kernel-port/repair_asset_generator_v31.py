"""Repair unexecuted generator text; prior physical v30 evidence remains intact."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=ROOT/'work/kernel-port/prepare_secure_ram_assets_generated_v31.py'
 text=p.read_text();text=text.replace('recovery="""','recovery=r"""');p.write_text(text)
 folder=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-v31'
 p=folder/'executor.py';text=p.read_text()
 text=text.replace("b'"+chr(3)+chr(21)+chr(10)+"'",r"b'\x03\x15\n'")
 p.write_text(text)
 compile(text,str(p),'exec')
 pins=json.loads((folder/'SOURCE_PINS.json').read_text())
 for f in [Path(__file__),p,ROOT/'work/kernel-port/prepare_secure_ram_assets_generated_v31.py']:
  pins[f.relative_to(ROOT).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
 (folder/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('UNEXECUTED_V31_GENERATOR_REPAIRED')
if __name__=='__main__':main()
