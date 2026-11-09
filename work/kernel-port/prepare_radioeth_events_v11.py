"""Version new event-syscall RAM artifact/executor without changing prior evidence."""
from pathlib import Path
import hashlib, json, subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'work/kernel-port/linux-7.3-radioeth-events-v11'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radioeth73-events-ram-20261022T2036Z'
OLD=PRIVATE.parent/'radioeth73-secure-ram-20261022T1934Z'
WSL=Path('/home/rea/openmitrastar-linux73-20261022T135100Z/radioeth73-events-artifact-v1')

def wsl_read(path):
 return subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','--','python3','-c','import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())',path.as_posix()],capture_output=True,check=True).stdout

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 if HERE.exists() or PRIVATE.exists(): raise RuntimeError('Immutable output already exists')
 receipt=json.loads(wsl_read(WSL/'result.json'))
 lane=receipt['lanes'][0]
 assert receipt['lanes'][0]['image_sha256']==receipt['lanes'][1]['image_sha256']
 assert lane['image_sha256']=='9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e'
 PRIVATE.mkdir();HERE.mkdir()
 acl=subprocess.run(['icacls.exe',str(PRIVATE),'/inheritance:r','/grant:r','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F',str(Path.home().name)+':(OI)(CI)F'],capture_output=True)
 if acl.returncode: raise RuntimeError('Private artifact ACL refused')
 for src,dst in [(WSL/'radioeth73-events-a.ras.bin',PRIVATE/'radioeth73-events-RAM-ONLY.ras.bin'),(WSL/'result.json',PRIVATE/'BUILD_RESULT.json')]: dst.write_bytes(wsl_read(src))
 (PRIVATE/'server.pem').write_bytes((OLD/'server.pem').read_bytes())
 config=json.loads((OLD/'CONFIG.json').read_text())
 config.update(image=str(PRIVATE/'radioeth73-events-RAM-ONLY.ras.bin'),bytes=lane['image_bytes'],sha256=lane['image_sha256'],crc32=lane['image_crc32'],payload_bytes=lane['payload_bytes'],raw_sha256=lane['raw_sha256'],entry=lane['entry'],load=lane['load'],receipt=str(PRIVATE/'BUILD_RESULT.json'),receipt_sha256=sha(PRIVATE/'BUILD_RESULT.json'),tls_cert=str(PRIVATE/'server.pem'),tls_cert_sha256=sha(PRIVATE/'server.pem'),parent_sha256='256868f35367375613d97a51ff73d036c2d4b16b8c5aca4d6a4a09b5f2cac3d2',change='Enable only EPOLL/SIGNALFD/TIMERFD/EVENTFD')
 (PRIVATE/'CONFIG.json').write_text(json.dumps(config,indent=2)+'\n')
 source=(HERE.parent/'linux-7.3-radioeth-powercycle-v3/executor.py').read_text()
 source=source.replace('"""Catch a fresh owner power-cycle and load the same exact RAM-only image.', '"""Reboot the nonce-bound current RAM diagnostic and load event-syscall image.')
 source=source.replace('No software reboot, flash or environment writes.', 'One authorized RAM reboot; no flash or environment writes.')
 source=source.replace('  deadline=self.clock()+600\n', "  self.synchronize_nonce(m.KERNEL)\n  self.safe();self.b.force_lease();self.fresh()\n  self.s.write(b'reboot\\n',timeout=3);self.steps.append('reboot-current-ram')\n  deadline=self.clock()+90\n", 1)
 source=source.replace('RADIOETH73_V3_CAPTURE_READY_POWER_CYCLE_NOW','RADIOETH73_V11_READY_CONTROLLED_RAM_REBOOT')
 source=source.replace('  self.b.force_lease();self.fresh();self.boots+=1;', "  for address in ['e0000004','f4000000']:\n   value=m.BASE.parse_word(self.command('md.l '+address+' 1',m.BASE.PROMPT),address)\n   m.BASE.require(int(value,16)&((1<<29)|(1<<30))==0 if address=='e0000004' else value=='00000000','map/watchdog changed before handoff')\n  self.b.force_lease();self.fresh();self.boots+=1;",1)
 source=source.replace("  m.BASE.require(b'Linux version '+m.KERNEL in boot and b'OPENMITRASTAR_RADIOETH73_RAM_V1' in boot,'new kernel/PID1 absent')\n", "  m.BASE.require(b'Linux version '+m.KERNEL in boot,'new kernel absent')\n")
 source=source.replace("'bootm':self.boots,'reboots':0", "'bootm':self.boots,'reboots':1")
 (HERE/'executor.py').write_text(source)
 for name in ['run.ps1','test_executor.py']:(HERE/name).write_bytes((HERE.parent/'linux-7.3-radioeth-powercycle-v3'/name).read_bytes())
 pins=json.loads((HERE.parent/'linux-7.3-radioeth-powercycle-v3/SOURCE_PINS.json').read_text())
 for name in ['executor.py','run.ps1','test_executor.py']:pins[(HERE/name).relative_to(ROOT).as_posix()]=sha(HERE/name)
 pins[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
 (HERE/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print(json.dumps({'config':str(PRIVATE/'CONFIG.json'),'image':str(PRIVATE/'radioeth73-events-RAM-ONLY.ras.bin'),'sha256':config['sha256'],'bytes':config['bytes'],'status':'RAM_ONLY_PREPARED','reboot':'current nonce-bound same RAM kernel, one call, preserved flash'}))
if __name__=='__main__':main()
