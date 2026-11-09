"""F363 thermal diagnostic install with the proven F362 recovery baseline."""
from pathlib import Path
import hashlib,json
import f362_install_contract as prior
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT,DEVICE=prior.ROOT,prior.DEVICE
LIVE,PREFIX,SLOT,STORE,STORE_BYTES=prior.LIVE,prior.PREFIX,prior.SLOT,prior.STORE,prior.STORE_BYTES
LOAD,READBACK,SCRATCH,PNP,BOOTARGS=prior.LOAD,prior.READBACK,prior.SCRATCH,prior.PNP,prior.BOOTARGS
sha,crc,require,protected_backups=prior.sha,prior.crc,prior.require,prior.protected_backups
store_binding=prior.store_binding
BINDING=ROOT/'work/kernel-port/versions/f363-installer/inputs.json'
BASELINE=ROOT/'work/kernel-port/versions/f363-installer/baseline.json'
STORE_BINDING=prior.STORE_BINDING
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f363-evidence')
def binding():
 d=json.loads(BINDING.read_text(encoding='ascii'));require(d['schema']=='openmitrastar.f363-installer-inputs/v1','binding_schema');return d
def images():
 b=binding();s=store_binding();store=Path(s['path']).read_bytes();result={}
 for name,spec in [('f363',b['candidate']),('f362',b['fallback'])]:
  folder=Path(spec['directory']);path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes()
  require(len(data)==spec['bytes'] and len(data)<PREFIX and sha(path)==spec['sha256'] and sha(folder/'manifest.json')==spec['manifest_sha256'],'image_binding')
  contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','bootbase_contract')
  prefix=data+b'\xff'*(PREFIX-len(data));full=prefix+store
  result[name]={**spec,'path':str(path),'known_hosts_path':str(folder/spec['known_hosts']),'crc32':crc(data),'prefix_crc32':crc(prefix),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'preserved_store_sha256':s['sha256'],'full_slot_scope':'firmware prefix plus exact seq2 store'}
 require(Path(result['f363']['known_hosts_path']).read_bytes()==Path(result['f362']['known_hosts_path']).read_bytes(),'SSH_identity_changed');require(result['f362']['full_slot_crc32']=='1a6e28c0','fallback_seq2_crc')
 q=json.loads(Path(b['qualification']['path']).read_text(encoding='ascii'));require(result['f363']['full_slot_crc32']==q['full_slot']['crc32'],'candidate_fullslot_crc');return result
def validate_proofs():
 b=binding();q=b['qualification'];require(sha(q['path'])==q['sha256'],'qualification_hash');r=json.loads(Path(q['path']).read_text(encoding='ascii'));require(r['status']==q['status'] and r['status'].startswith('PASS_') and r['artifact']['sha256']==b['candidate']['sha256'] and r['manifest_sha256']==b['candidate']['manifest_sha256'],'qualification_binding')
 p=b['baseline']['physical_result'];require(sha(p['path'])==p['sha256'],'baseline_proof_hash');r=json.loads(Path(p['path']).read_text(encoding='ascii'));require(r['status']=='PASS_F362_PRESERVED_JOURNAL' and r['writer']['image']==b['fallback']['sha256'] and r['writer']['full_slot_crc32']=='1a6e28c0' and r['store_after']['sha256']==store_binding()['sha256'] and r['configuration_boot']['sequence']==2 and r['containment_confirmed'] and not r['retain_lease_required'],'baseline_proof')
 return prior.validate_proofs()+[q,p,b['baseline']['tested_plan']]
