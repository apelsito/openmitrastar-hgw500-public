"""Firmware-prefix identities plus an independently pinned mutable store."""
from pathlib import Path
import hashlib,json
import f358_install_contract as prior
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT,DEVICE=prior.ROOT,prior.DEVICE
LIVE,PREFIX,SLOT,STORE,STORE_BYTES=prior.LIVE,prior.PREFIX,prior.SLOT,prior.STORE,prior.STORE_BYTES
LOAD,READBACK,SCRATCH,PNP,BOOTARGS=prior.LOAD,prior.READBACK,prior.SCRATCH,prior.PNP,prior.BOOTARGS
sha,crc,require,protected_backups=prior.sha,prior.crc,prior.require,prior.protected_backups
BINDING=ROOT/'work/kernel-port/versions/f361-installer/inputs.json'
STORE_BINDING=ROOT/'work/kernel-port/versions/f361-installer/store-binding.json'
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f361-evidence')
def binding():
 data=json.loads(BINDING.read_text(encoding='ascii'));require(data['schema']=='openmitrastar.f361-installer-inputs/v1','candidate_binding_schema');return data
def store_binding():
 data=json.loads(STORE_BINDING.read_text(encoding='ascii'));path=Path(data['path']);require(path.stat().st_size==STORE_BYTES and sha(path)==data['sha256'] and crc(path.read_bytes())==data['crc32'],'preserved_store_bytes')
 proof=data['physical_result'];require(sha(proof['path'])==proof['sha256'],'store_physical_proof');record=json.loads(Path(proof['path']).read_text(encoding='ascii'))
 require(record['status']=='PASS_F360_CONFIG_SAVED_AND_PERSISTED' and record['return']['store_snapshot']['store_sha256']==data['sha256'] and record['return']['readback']['store_crc32']==data['crc32'],'store_physical_binding')
 audit=data['erase_audit'];require(sha(audit['path'])==audit['sha256'],'erase_audit_drift');review=json.loads(Path(audit['path']).read_text(encoding='ascii'));require(review['status']=='PASS_STATIC_EXCLUSIVE_PREFIX_END' and review['end_exclusive']==STORE and all(review['checks'].values()),'erase_end_contract');return data
def images():
 original=prior.images()['f358'];candidate=binding()['candidate'];preserved=store_binding();store=Path(preserved['path']).read_bytes();result={}
 require('-f361-' in candidate['version'],'candidate_version')
 for name,spec in [('f361',candidate),('f358',original)]:
  folder=Path(spec['directory']) if Path(spec['directory']).is_absolute() else DEVICE/spec['directory'];path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes()
  require(len(data)==spec['bytes'] and sha(path)==spec['sha256'] and sha(folder/'manifest.json')==spec['manifest_sha256'],'firmware_prefix_artifact')
  require(len(data)<PREFIX,'firmware_overlaps_store');contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','bootbase_contract')
  prefix=data+b'\xff'*(PREFIX-len(data));full=prefix+store
  result[name]={**spec,'directory':str(folder),'path':str(path),'known_hosts_path':str(folder/spec['known_hosts']),'crc32':crc(data),'prefix_crc32':crc(prefix),
   'manifest_ff_full_slot_crc32':crc(data+b'\xff'*(SLOT-len(data))),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'preserved_store_sha256':preserved['sha256'],'full_slot_scope':'firmware prefix plus exact preserved journal snapshot'}
 require(Path(result['f361']['known_hosts_path']).read_bytes()==Path(result['f358']['known_hosts_path']).read_bytes(),'SSH_identity_changed');return result
def validate_proofs():
 data=binding();item=data['qualification'];require(sha(item['path'])==item['sha256'],'candidate_qualification_hash');q=json.loads(Path(item['path']).read_text(encoding='ascii'));require(q['status']==item['status'] and q['status'].startswith('PASS'),'candidate_qualification_status')
 require(q['artifact']['sha256']==data['candidate']['sha256'] and q['artifact']['bytes']==data['candidate']['bytes'] and q['manifest_sha256']==data['candidate']['manifest_sha256'],'candidate_qualification_binding')
 return prior.validate_proofs()+[item,store_binding()['erase_audit']]
