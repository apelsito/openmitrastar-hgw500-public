"""Repair exact old/new pins and continue the stopped shell without reboot."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-auth-v33'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-auth-v34'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 code=(OLD/'executor.py').read_text()
 code=code.replace("if name=='old_pin':m.BASE.require('74128b573bf0a9e007862a50fdd5ee0747a41d6e380a7f476fd70d47ed62b06f'", "if name=='old_pin':m.BASE.require('7ff57b2cebe3f75c18daef7d259e80d5f2c3315b31551173897a9bd26ab376f0'")
 start=code.index('  status=self.synchronize_nonce');end=code.index('  for name in SCRIPTS:',start)
 code=code[:start]+"  self.safe();self.fresh();self.s.write(b'\\x03\\x15\\n',timeout=3);time.sleep(.2)\n  gates={}\n"+code[end:]
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py','expected-upload.cgi']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',NEW/'expected-upload.cgi']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V34_CURRENT_SHELL_PINS_CORRECTED')
if __name__=='__main__':main()
