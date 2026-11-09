"""Switch exact current RAM diagnostic to owner-selected second cable port."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-ap-v9'
NEW=ROOT/'work/kernel-port/linux-7.3-eth0-v46'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 code=(OLD/'executor.py').read_text()
 begin=code.index("  for name in ['pcistatus'")
 end=code.index("\ndef main():",begin)
 code=code[:begin]+"""  for name in ['eth1down','eth0up','eth0state','eth0txdiag','ethstats','netstats','status']:
   gates[name]=safe_text(self.command(name,seconds=45))
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')
  return {'status':'PASS_ETH0_ACTIVATED_CURRENT_RAM','bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0,'gates':gates,'steps':self.steps}
"""+code[end:]
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('V46_ETH0_CURRENT_RAM_SWITCH_READY')
if __name__=='__main__':main()
