"""Bind Windows-accepted legacy encoding to exact paired kernel/autostart root."""
from pathlib import Path
import hashlib,json,lzma,sys,zlib,shutil
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
from init_lyoko_device_host_key import restrict_acl
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware'
OLD=DEVICE/'radio73-2g-doom-autostart-20261023-v2'
NEW=DEVICE/'radio73-2g-doom-autostart-legacy-20261023-v3'
PUBLIC=ROOT/'outputs/rea/radio73-2g-doom-autostart-offline-20261023-v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if PUBLIC.exists():raise RuntimeError('Immutable public output exists')
 PUBLIC.mkdir();restrict_acl(NEW,directory=True)
 prior=json.loads((OLD/'CONFIG.json').read_text())
 encoded=json.loads((NEW/'ENCODER_RESULT.json').read_text())
 b=json.loads(Path(prior['receipt']).read_text());q=json.loads(Path(prior['qualification']).read_text())
 assert encoded['kernel_build_result_sha256']==sha(Path(prior['receipt']))
 image=NEW/'radio73-2g-doom-autostart.ras.bin';body=image.read_bytes();row=encoded['lanes'][0]
 contract=validate_bootbase_slot('exact owner flash candidate',body,0x5e0000)
 assert contract.accepted_by_contract and sha(image)==row['image_sha256']
 decoded=lzma.decompress(body[8192:],format=lzma.FORMAT_ALONE)
 assert hashlib.sha256(decoded).hexdigest()==row['raw_sha256']==b['lanes'][0]['raw_sha256']
 assert len(decoded)==row['raw_bytes']==b['lanes'][0]['raw_bytes']
 originalqualification=PUBLIC/'KERNEL_ROOT_QUALIFICATION.json'
 originalqualification.write_bytes(Path(prior['qualification']).read_bytes())
 for lane in b['lanes']:
  new=encoded['lanes'][0 if lane['lane']=='a' else 1]
  lane.update({k:v for k,v in new.items() if k in lane})
  lane['Bootbase_contract']=image_to_dict(contract)
 b.update(status='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN',legacy_encoder_result=encoded,original_kernel_build_receipt_sha256=encoded['kernel_build_result_sha256'])
 build=PUBLIC/'BUILD_RESULT.json';build.write_text(json.dumps(b,indent=2)+'\n')
 qualification=q|{'status':'PASS_INDEPENDENT_2G_FLATCPIO_LZMA_ENTRY_PREFIX_ROOT_CONTRACTS','build_result_sha256':sha(build),'original_kernel_root_qualification_sha256':sha(originalqualification),'legacy_exact_raw_binding':True,'Windows_Bootbase_contract':image_to_dict(contract)}
 qualified=PUBLIC/'QUALIFICATION.json';qualified.write_text(json.dumps(qualification,indent=2)+'\n')
 shutil.copyfile(OLD/'server.pem',NEW/'server.pem')
 config=prior|{'image':str(image),'bytes':row['image_bytes'],'sha256':row['image_sha256'],'crc32':row['image_crc32'],'payload_bytes':row['payload_bytes'],'raw_sha256':row['raw_sha256'],'raw_bytes':row['raw_bytes'],'entry':row['entry'],'receipt':str(build),'receipt_sha256':sha(build),'qualification':str(qualified),'qualification_sha256':sha(qualified),'tls_cert':str(NEW/'server.pem'),'tls_cert_sha256':sha(NEW/'server.pem'),'prefix_headroom_bytes':row['prefix_headroom']}
 (NEW/'CONFIG.json').write_text(json.dumps(config,indent=2)+'\n')
 for p in NEW.iterdir():restrict_acl(p,directory=False)
 (PUBLIC/'MANIFEST.json').write_text(json.dumps(config|{'status':'PASS_OFFLINE_KERNEL_PAIR_ROOT_AND_LEGACY_ENCODING_WINDOWS_LINUX','physical_boot':'UNRUN','physical_flash':'UNRUN'},indent=2)+'\n')
 print(json.dumps({'status':'PASS_EXACT_LEGACY_FLASH_CANDIDATE_CONFIG','bytes':config['bytes'],'sha256':config['sha256'],'config':str(NEW/'CONFIG.json')}))
if __name__=='__main__':main()
