"""Normalize exact provisioned CRLF hash to LF without changing its value."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-webhash-v24'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 # Hash bytes stay solely in private RAM file and shell variables. Test shape
 # before replacing; retain owner permissions; never relax credential checks.
 scripts={
 'runtime':'uname -r',
 'hash_fix':"p=/run/openmitrastar/secrets/web.password.sha256; h=$(tr -d '\\r\\n' < $p); printf %s \"$h\" | grep -Eq '^[0-9a-fA-F]{64}$' && { umask 077; printf '%s\\n' \"$h\" > $p.new && chmod 600 $p.new && mv $p.new $p; }; echo HASH_NORMALIZE_RC=$?; unset h",
 'check':"head -n 1 /run/openmitrastar/secrets/web.password.sha256 | wc -c; head -n 1 /run/openmitrastar/secrets/web.password.sha256 | grep -Eq '^[0-9a-fA-F]{64}$'; echo HASH_READY_RC=$?; id -u",
 'finish':'cat /proc/uptime',
 }
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R23-'+self.nonce[:8]+'-'+name","marker='R24-'+self.nonce[:8]+'-'+name")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V24_PRIVATE_HASH_NORMALIZE_READY')
if __name__=='__main__':main()
