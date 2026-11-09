from pathlib import Path
import sys,json,dataclasses
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from bootbase_contract_emulator import validate_bootbase_slot
p=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radio73-2g-doom-autostart-legacy-20261023-v3/radio73-2g-doom-autostart.ras.bin'
r=validate_bootbase_slot('legacy candidate',p.read_bytes(),0x5e0000)
print(json.dumps(dataclasses.asdict(r),indent=2))
