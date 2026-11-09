"""Correct exact cookie parser without relaxing session or CSRF gates."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-auth-v32'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-auth-v33'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 source=(OLD/'expected-upload.cgi').read_bytes()
 lines=source.decode().splitlines(keepends=True)
 assert sum(l.startswith('token=') for l in lines)==1
 changed=''.join('token=${HTTP_COOKIE#OMSESSION=}\n' if l.startswith('token=') else l for l in lines).encode()
 (NEW/'expected-upload.cgi').write_bytes(changed)
 scripts={'runtime':'uname -r','old_pin':'sha256sum /www/__assets.cgi','cookie_parser':"sed -i '/^token=/c\\token=${HTTP_COOKIE#OMSESSION=}' /www/__assets.cgi",'new_pin':'sha256sum /www/__assets.cgi','after':'cat /proc/uptime'}
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R32-'+self.nonce[:8]+'-'+name","marker='R33-'+self.nonce[:8]+'-'+name")
 code=code.replace('b1de8751f91aadb92c8bd590c5d59471fcd5f5ae6445b6ec20385b6ce984d3e8',sha(OLD/'expected-upload.cgi'))
 code=code.replace("if name=='permission'","if name=='new_pin'")
 code=code.replace('7ff57b2cebe3f75c18daef7d259e80d5f2c3315b31551173897a9bd26ab376f0',hashlib.sha256(changed).hexdigest())
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',NEW/'expected-upload.cgi']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V33_EXACT_COOKIE_PARSER_PATCH')
if __name__=='__main__':main()
