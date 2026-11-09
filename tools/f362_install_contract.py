"""F362 firmware prefix and exact seq2 journal binding, fallback F361."""
from pathlib import Path
import hashlib,json
import f358_install_contract as prior
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT,DEVICE=prior.ROOT,prior.DEVICE
LIVE,PREFIX,SLOT,STORE,STORE_BYTES=prior.LIVE,prior.PREFIX,prior.SLOT,prior.STORE,prior.STORE_BYTES
LOAD,READBACK,SCRATCH,PNP,BOOTARGS=prior.LOAD,prior.READBACK,prior.SCRATCH,prior.PNP,prior.BOOTARGS
sha,crc,require,protected_backups=prior.sha,prior.crc,prior.require,prior.protected_backups
BINDING=ROOT/'work/kernel-port/versions/f362-installer/inputs.json'
STORE_BINDING=ROOT/'work/kernel-port/versions/f362-installer/store-binding.json'
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f362-evidence')
def binding():
 d=json.loads(BINDING.read_text(encoding='ascii'));require(d['schema']=='openmitrastar.f362-installer-inputs/v1','binding_schema');return d
def store_binding():
 d=json.loads(STORE_BINDING.read_text(encoding='ascii'));p=Path(d['path']);require(p.stat().st_size==STORE_BYTES and sha(p)==d['sha256'] and crc(p.read_bytes())==d['crc32'],'store_bytes')
 proof=d['physical_result'];require(sha(proof['path'])==proof['sha256'],'store_proof_hash');r=json.loads(Path(proof['path']).read_text(encoding='ascii'))
 require(r['status']=='PASS_PRIVATE_STORE_CAPTURE_AFTER_NORMAL_SAVE' and r['sequence']==2 and r['slot']==1 and r['store_sha256']==d['sha256'] and r['store_crc32']==d['crc32'],'store_proof_binding')
 audit=d['erase_audit'];require(sha(audit['path'])==audit['sha256'],'erase_audit_hash');r=json.loads(Path(audit['path']).read_text(encoding='ascii'));require(r['status']=='PASS_STATIC_EXCLUSIVE_PREFIX_END' and r['end_exclusive']==STORE and all(r['checks'].values()),'erase_exclusive');return d
def images():
 b=binding();s=store_binding();store=Path(s['path']).read_bytes();result={}
 for name,spec in [('f362',b['candidate']),('f361',b['fallback'])]:
  folder=Path(spec['directory']);path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes()
  require(len(data)==spec['bytes'] and len(data)<PREFIX and sha(path)==spec['sha256'] and sha(folder/'manifest.json')==spec['manifest_sha256'],'image_binding')
  contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','bootbase_contract')
  prefix=data+b'\xff'*(PREFIX-len(data));full=prefix+store
  result[name]={**spec,'path':str(path),'known_hosts_path':str(folder/spec['known_hosts']),'crc32':crc(data),'prefix_crc32':crc(prefix),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'preserved_store_sha256':s['sha256'],'full_slot_scope':'firmware prefix plus exact seq2 store'}
 require(Path(result['f362']['known_hosts_path']).read_bytes()==Path(result['f361']['known_hosts_path']).read_bytes(),'SSH_identity_changed')
 require(result['f362']['full_slot_crc32']=='1a6e28c0' and result['f361']['full_slot_crc32']=='815b9440','fullslot_with_seq2');return result
def validate_proofs():
 b=binding();q=b['qualification'];require(sha(q['path'])==q['sha256'],'qualification_hash');r=json.loads(Path(q['path']).read_text(encoding='ascii'));require(r['status']==q['status'] and r['artifact']['sha256']==b['candidate']['sha256'] and r['manifest_sha256']==b['candidate']['manifest_sha256'],'qualification_binding')
 u=b['serial_recovery'];require(sha(u['path'])==u['sha256'],'serial_proof_hash');r=json.loads(Path(u['path']).read_text(encoding='ascii'));require(r['status']=='PASS_SERIAL_SYSRQ_AND_AUTONOMOUS_F361_RETURN' and r['sysrq_requests']==1 and r['sysrq_dispatch_seen'] and r['containment_confirmed'] and not r['retain_lease_required'] and r['after']['sequence']=='2','serial_recovery_proof')
 return prior.validate_proofs()+[q,u,store_binding()['erase_audit']]
