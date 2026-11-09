"""Read-only compact build receipt with selected facts, not source/credentials."""
from pathlib import Path
import json
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
p=BASE/'radio73-common-r3-context-v1/result.json'
r=json.loads(p.read_text())
print(json.dumps({'status':r['status'],'release':r['release'],'started_utc':r['started_utc'],'lanes':[{'name':l['name'],'ABI':l['ABI'],'module_count':l['module_count'],'kernel_module_count':l['kernel_module_count'],'native_C_units':l['native_C_units'],'kernel_sha256':l['kernel_sha256'],'dtb_sha256':l['dtb_sha256']} for l in r['lanes']]},indent=2))
