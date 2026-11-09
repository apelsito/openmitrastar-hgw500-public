"""Newr4exactcoreheaderatbothsharedandlocalinclude locations, nosemanticdelta."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 for d in('source','headers'):shutil.copytree(a.parent/d,a.output/d)
 path=a.output/'source/wlan/openmitrastar_rbsdfs_recovered.h';path.write_bytes((a.parent/'headers/net80211/openmitrastar_rbsdfs_recovered.h').read_bytes());r=json.loads((a.parent/'result.json').read_text());r.update(status='SOURCE_ONLY_RBS466468_KERNEL_R4_EXACT_LOCAL_CORE_HEADER_PENDING',revision='r4',parent_revision=str(a.parent),parent_revision_sha256=sha(a.parent/'result.json'),changed_sources={**r['changed_sources'],'source/wlan/openmitrastar_rbsdfs_recovered.h':sha(path)},exact_header_in_two_include_locations=True);(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
