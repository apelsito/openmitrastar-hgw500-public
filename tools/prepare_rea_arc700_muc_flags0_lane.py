"""Derive isolated REA static lane for the proven MuC ARC700 flags0 artifact.

Original ELF headers and installed/runtime parent remain unchanged. This is a
bounded analyst admission change, not upstream-supported architecture proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 manifest_path=a.parent/'manifest.json';before=sha(manifest_path);manifest=json.loads(manifest_path.read_text());runtime=Path(manifest['runtime'])
 a.output.mkdir(parents=True,exist_ok=False);derived=a.output/'rea-agents';derived.mkdir()
 for name in('dist','bridge','scripts'):shutil.copytree(runtime/name,derived/name)
 for name in('package.json','LICENSE','README.md'):shutil.copyfile(runtime/name,derived/name)
 (derived/'node_modules').symlink_to((runtime/'node_modules').resolve(),target_is_directory=True)
 changes=[]
 for file in(derived/'dist').rglob('*.js'):
  old=file.read_text();needle='![0x3, 0x303, 0x403].includes(readU32(36))'
  if needle not in old:continue
  new=old.replace(needle,'![0x0, 0x3, 0x303, 0x403].includes(readU32(36))').replace('flags 0x3/0x303/0x403','flags 0x0/0x3/0x303/0x403')
  oldsha=sha(file);file.write_text(new);changes.append(dict(path=str(file.relative_to(derived)),parent_sha256=oldsha,derived_sha256=sha(file)))
 assert len(changes)==3 and sha(manifest_path)==before
 manifest.update(runtime=str(derived),parent_manifest_sha256=before,parent_lab=str(a.parent),muc_flags0_patches=changes,status='DERIVED_MUC_FLAGS0_STATIC_LANE_REQUIRES_ARTIFACT_ASSEMBLY_VERIFICATION',admission_delta='Admit genuineARC32LE EM93 flags0 for exactMuC codewindow only; noheaderrelabeling',parent_runtime_modified=False,installed_rea_modified=False,original_artifacts_modified=False,hardware_accessed=False)
 (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(output=str(a.output),patches=len(changes),parent_unchanged=True)))


if __name__=='__main__':main()
