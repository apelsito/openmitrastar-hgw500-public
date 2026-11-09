"""Qualify session with GET semantics before exact allowlisted POST upload."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-assets-auth-v32'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 scripts={'runtime':'uname -r','old_pin':'sha256sum /www/__assets.cgi','auth_method':"sed -i 's@auth=$(/bin/sh@auth=$(REQUEST_METHOD=GET /bin/sh@' /www/__assets.cgi",'permission':'chmod 755 /www/__assets.cgi; sha256sum /www/__assets.cgi','after':'cat /proc/uptime'}
 source=(ROOT/'outputs/doom/linux73-https-assets-v31/upload.cgi').read_bytes()
 changed=source.replace(b'auth=$(/bin/sh',b'auth=$(REQUEST_METHOD=GET /bin/sh')
 assert changed!=source
 (NEW/'expected-upload.cgi').write_bytes(changed)
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R23-'+self.nonce[:8]+'-'+name","marker='R32-'+self.nonce[:8]+'-'+name")
 code=code.replace("   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')","   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')\n   if name=='old_pin':m.BASE.require('b1de8751f91aadb92c8bd590c5d59471fcd5f5ae6445b6ec20385b6ce984d3e8' in gates[name],'CGI parent drift')\n   if name=='permission':m.BASE.require('"+hashlib.sha256(changed).hexdigest()+"' in gates[name],'CGI auth patch drift')")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',NEW/'expected-upload.cgi']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V32_AUTH_READ_METHOD_EXACT_PATCH')
if __name__=='__main__':main()
