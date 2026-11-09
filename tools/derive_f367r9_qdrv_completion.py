"""Complete qdrv against the already built peer, without rebuilding wlan."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('completion anchor '+a[:100])
 return s.replace(a,b,1)
def main():
 s=(ROOT/'tools/build_f367r9_components.py').read_text()
 s=s.replace('import hashlib,json,re,shlex,shutil,subprocess','import argparse,hashlib,json,re,shlex,shutil,subprocess')
 s=s.replace("host_test['status']=='PASS_OBSERVATION_PATCH_PRESERVES_ORIGINAL'","host_test['status']=='PASS_R2_SHARED_CALSTATE_OBSERVATION'")
 s=once(s,'def main():\n', '''def main():
 global HOST_TEST
 ap=argparse.ArgumentParser();ap.add_argument('--hostlink-test',type=Path,required=True);args=ap.parse_args();HOST_TEST=args.hostlink_test.resolve()
 peer_path=ROOT/'outputs/kernel-port/f367r9-peer-sealed-20260922T223737Z/result.json'
 peer=json.loads(peer_path.read_text());require(peer['status']=='PASS_PEER_SOURCE_AND_HEADER_PROVENANCE','peer provenance missing')
 for path,digest in peer['source_pins'].items():require(sha(path)==digest,'peer source changed')
 require(sha(peer['artifact']['path'])==peer['artifact']['sha256'] and sha(peer['module_symvers']['path'])==peer['module_symvers']['sha256'],'sealed peer changed')
''')
 s=s.replace("('f367r9-transition-'+stamp)","('f367r9-completed-'+stamp)")
 s=s.replace("build='/home/user/openmitrastar-build/f367r9-transition-'+stamp","build='/home/user/openmitrastar-build/f367r9-completed-'+stamp")
 lines=s.splitlines();selected=[line for line in lines if 'M="$build/$lane/wlan"' in line];assert len(selected)==1
 s=s.replace(selected[0],''' cp {q(linux(peer['artifact']['path']))} "$build/$lane/wlan/wlan.ko"
 cp {q(linux(peer['module_symvers']['path']))} "$build/$lane/wlan/Module.symvers"''')
 s=once(s,"for proof in (test,host_test):input_pins.update(proof['source_pins'])","for proof in (test,host_test):input_pins.update(proof['source_pins'])\n input_pins.update(peer['input_pins']);input_pins[str(peer_path.resolve())]=sha(peer_path)")
 s=once(s,"new_cross_module_trace_symbols=False,peer_parent_flags=parent_flags", "new_cross_module_trace_symbols=False,qdrv_build_count=2,wlan_build_count=1,peer_provenance=item(peer_path),reproducibility_detail={'qdrv_build_count':2,'qdrv_byte_identical':True,'wlan_build_count':1,'wlan_reused_from_sealed_peer':True,'wlan_double_build_verified':False,'complete_source_release_reproducibility_attested':False},peer_parent_flags=parent_flags")
 (ROOT/'tools/build_f367r9_qdrv_completion.py').write_bytes(s.encode());print('F367R9_QDRV_COMPLETION_READY')
if __name__=='__main__':main()
