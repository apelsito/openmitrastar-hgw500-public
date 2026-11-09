"""Export only non-sensitive build/qualification receipts; no firmware/key export."""
from pathlib import Path
import hashlib,json
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
WINDOWS=Path('/workspace/user-home/Desktop/MitraStar')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 build=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
 qualification=BASE/'radioeth73-integrated-r2-qualified-v1'
 b=json.loads((build/'result.json').read_text());q=json.loads((qualification/'result.json').read_text())
 if b['status']!='PASS_PAIRED_RAM_INTEGRATION_PHYSICAL_UNRUN' or q['status']!='PASS_INDEPENDENT_ELF_CPIO_BOOTBASE_RAM_CONTRACTS':raise RuntimeError('Qualified receipts absent')
 if q['builder_receipt_sha256']!=sha(build/'result.json'):raise RuntimeError('Qualified receipt binding changed')
 out=WINDOWS/'outputs/rea/radioeth73-integrated-r2-20261023-offline-v1'
 if out.exists():raise RuntimeError('Immutable output exists')
 out.mkdir()
 for src,name in [(build/'result.json','BUILD_RESULT.json'),(qualification/'result.json','RAM_CONTRACT_RESULT.json')]:
  (out/name).write_bytes(src.read_bytes())
 manifest={'status':'PASS_PAIRED_AND_INDEPENDENT_RAM_CONTRACTS_PHYSICAL_UNRUN','classification':'RAM_DIAGNOSTIC_NO_FLASH','private_artifact_directory':str(build),'image':b['lanes'][0],'build_receipt_sha256':sha(build/'result.json'),'qualification_receipt_sha256':sha(qualification/'result.json'),'module_count':len(b['module_hashes'])+1,'unchanged_radio_and_ethernet_hashes':True,'game_files':b['game_files'],'game_raw_bytes':b['game_raw_bytes'],'hardware_accessed':False,'flash_writes':0,'bootenv_writes':0,'limits':['Private image remains only in local Linux build directory; no private keys copied to public evidence.','Complete common radio ABI/kernel and SRAM activation pending.','R2 has not booted on the HGW; parent traffic proof does not transfer.','RAM payload exceeds allowed flash prefix; no flash authorization requested or assumed.']}
 (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (out/'SHA256SUMS').write_text('\n'.join(sha(p)+'  '+p.name for p in sorted(out.glob('*.json')))+'\n')
 print(json.dumps({'status':manifest['status'],'image_bytes':manifest['image']['image_bytes'],'image_sha256':manifest['image']['image_sha256'],'output':str(out)}))
if __name__=='__main__':main()
