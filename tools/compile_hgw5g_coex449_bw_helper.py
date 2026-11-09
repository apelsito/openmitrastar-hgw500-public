"""Actual ARC typed compilation of standalone recovered changeBW helper."""
import argparse
import hashlib
import json
from pathlib import Path
from build_hgw5g_typed_header_closure import compile_command,run
import build_f370_qdrv_module as qb

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--helper',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);q=a.candidate/'source/qdrv';w=a.candidate/'source/wlan';h=a.candidate/'headers';source=w/'ieee80211_node.c';prefix='\n'.join(x for x in source.read_text().splitlines()if x.startswith('#include'))+'\n';file=a.output/'witness.c';file.write_text(prefix+a.helper.read_text());pins={str(a.helper):sha(a.helper),str(source):sha(source),str(h/'net80211/ieee80211_var.h'):sha(h/'net80211/ieee80211_var.h'),str(Path(__file__)):sha(__file__)};cmd,_=compile_command('wlan','ieee80211_node',a.output,q,w,h);cmd[-1]=str(file);cmd[cmd.index('-o')+1]=str(a.output/'witness.o');run(cmd,qb.context.CONTEXT,a.output/'compile');assert all(sha(p)==x for p,x in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_ARC_ACTUAL_TYPED_CHANGE_BW_HELPER',hardware_accessed=False,firmware_eligible=False,helper_sha256=pins[str(a.helper)],object_sha256=sha(a.output/'witness.o'),limits='TypedARCcompileonly; actualhostorderfixture separate; nohardwareorfirmwareacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
