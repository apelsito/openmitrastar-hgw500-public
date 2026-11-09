"""Continue the exact stopped events-v11 trial by an owner power-cycle."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-events-v11'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-events-powercycle-v12'
STOP=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-v11/result.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version already exists')
 prior=json.loads(STOP.read_text())
 assert prior['bootm']==0 and prior['flash_writes']==prior['bootenv_writes']==0
 assert prior['error_reason']=='Controlled RAM reboot did not return to Bootbase'
 NEW.mkdir()
 code=(OLD/'executor.py').read_text()
 code=code.replace('"""Reboot the nonce-bound current RAM diagnostic and load event-syscall image.','"""Load the exact events image after the owner cycles the halted RAM unit.')
 code=code.replace('One authorized RAM reboot; no flash or environment writes.','Owner power-cycle only; no software reset, flash or environment writes.')
 start=code.index('  # Current console must prove')
 stop=code.index('  while self.clock()<deadline:',start)
 replacement="""  previous=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-v11/result.json'
  prior=json.loads(previous.read_text())
  m.BASE.require(prior['artifact']['sha256']==self.config['sha256'] and prior['bootm']==0 and prior['flash_writes']==prior['bootenv_writes']==0 and prior['error_reason']=='Controlled RAM reboot did not return to Bootbase','Exact halted trial absent')
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','artifact_sha256':self.config['sha256'],'flash_writes':0,'bootenv_writes':0,'prior_halted_trial_bound':True})+'\\n')
  print('RADIOETH73_V12_CAPTURE_READY_POWER_CYCLE_NOW',flush=True)
  deadline=self.clock()+600
"""
 code=code[:start]+replacement+code[stop:]
 code=code.replace("else:raise TimeoutError('Controlled RAM reboot did not return to Bootbase')","else:raise TimeoutError('Owner power-cycle not received')")
 code=code.replace("'bootm':self.boots,'reboots':1","'bootm':self.boots,'reboots':0")
 code=code.replace("reboots=int(bool(flow and 'reboot-current-ram' in flow.steps))","reboots=0")
 (NEW/'executor.py').write_text(code)
 (NEW/'run.ps1').write_bytes((OLD/'run.ps1').read_bytes())
 (NEW/'test_executor.py').write_bytes((OLD.parent/'linux-7.3-radioeth-powercycle-v3/test_executor.py').read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 pins[STOP.relative_to(ROOT).as_posix()]=sha(STOP)
 for p in [NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',Path(__file__)]:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('V12_OWNER_POWER_CYCLE_READY_OFFLINE')
if __name__=='__main__':main()
