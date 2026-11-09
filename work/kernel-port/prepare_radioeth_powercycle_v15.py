"""Rearm exact events image after the recorded transfer control failure."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-events-powercycle-v12'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-events-powercycle-v15'
STOP=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-powercycle-v12/result.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Immutable version exists')
 prior=json.loads(STOP.read_text())
 assert prior['bootm']==prior['flash_writes']==prior['bootenv_writes']==0
 assert prior['error_reason']=='unexpected byte in UART control dialogue'
 NEW.mkdir()
 code=(OLD/'executor.py').read_text().replace('radioeth73-events-physical-v11/result.json','radioeth73-events-physical-powercycle-v12/result.json')
 code=code.replace("prior['error_reason']=='Controlled RAM reboot did not return to Bootbase'","prior['error_reason']=='unexpected byte in UART control dialogue'")
 code=code.replace('RADIOETH73_V12_CAPTURE_READY_POWER_CYCLE_NOW','RADIOETH73_V15_CAPTURE_READY_POWER_CYCLE_NOW')
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [STOP,Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('V15_OFFLINE_REARM_READY')
if __name__=='__main__':main()
