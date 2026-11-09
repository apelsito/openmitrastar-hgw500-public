"""Replay independent saved-byte counterexample against corrected R2 source."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from review_hgw5g_vopt481_unsigned_saved_bytes import TEST
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();text=TEST.replace('values[78]==-1&&values[158]==-1&&values[195]==-128&&values[288]==-1','values[78]==255&&values[158]==255&&values[195]==128&&values[288]==255');inputs=[Path(__file__),Path(__file__).with_name('review_hgw5g_vopt481_unsigned_saved_bytes.py'),a.compiler,a.candidate/'openmitrastar_vopt481_recovered.c',a.candidate/'openmitrastar_vopt481_recovered.h'];pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in inputs};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-r2-unsigned-replay.c';f.write_text(text);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(a.candidate),str(f),str(a.candidate/'openmitrastar_vopt481_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_INDEPENDENT_R2_UNSIGNED_SAVED_BYTES_SIGNED_ONLY_MODE482',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest());(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
