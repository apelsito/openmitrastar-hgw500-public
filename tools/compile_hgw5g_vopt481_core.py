"""Versioned ARC object-only481 gate reusing the pinned isolated-core builder."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import os
import sys


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    original=Path(__file__).with_name('compile_hgw5g_rbsdfs_recovered_core.py')
    text=original.read_text().replace('openmitrastar_rbsdfs_recovered.c','openmitrastar_vopt481_recovered.c')
    old="expected={'om_rbsdfs_init','om_rbsdfs_set466','om_rbsdfs_get466','om_rbsdfs_set468','om_rbsdfs_get468','om_rbsdfs_oem_radar_window','om_rbsdfs_oem_mbs_window','om_rbsdfs_oem_send_permitted','om_rbsdfs_oem_expire','om_rbsdfs_exact_frame_window'}"
    assert old in text
    text=text.replace(old,"expected={'om_vopt_initialize','om_vopt_set','om_vopt_get','om_vopt_apply','om_vopt_count_peer','om_vopt_tick'}")
    text=text.replace("{'bus_to_virt','muc_to_nocache','nocache_to_muc'}","{'bus_to_virt','muc_to_nocache','nocache_to_muc','om_vopt_byte_value'}")
    text=text.replace('PASS_ARC_RBSDFS_ISOLATED_TEN_FUNCTION_CORE_OBJECT_ONLY','PASS_ARC_VOPT481_ISOLATED_CORE_OBJECT_ONLY')
    script=a.output/'adapted-core-compiler.py';script.write_text(text,encoding='utf-8',newline='\n')
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parent)
    r=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--output',str(a.output/'compile')],env=env,capture_output=True)
    (a.output/'run.stdout').write_bytes(r.stdout);(a.output/'run.stderr').write_bytes(r.stderr)
    assert r.returncode==0,r.stderr.decode(errors='replace')
    proof=json.loads((a.output/'compile/result.json').read_text())
    proof['adaptation_pins']={str(path):sha(path)for path in[Path(__file__),original,script]}
    (a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
