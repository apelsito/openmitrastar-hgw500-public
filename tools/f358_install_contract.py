"""Exact F358 candidate binding plus canonical F340 fallback; no device access."""
from pathlib import Path
import hashlib,json
import f346_install_contract as original
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT,DEVICE=original.ROOT,original.DEVICE
LIVE,PREFIX,SLOT,STORE,STORE_BYTES=original.LIVE,original.PREFIX,original.SLOT,original.STORE,original.STORE_BYTES
LOAD,READBACK,SCRATCH,PNP,BOOTARGS=original.LOAD,original.READBACK,original.SCRATCH,original.PNP,original.BOOTARGS
sha,crc,require,protected_backups=original.sha,original.crc,original.require,original.protected_backups
BINDING=ROOT/'work/kernel-port/versions/f358-installer/inputs.json'
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f358-evidence')
def binding():
    data=json.loads(BINDING.read_text(encoding='ascii'));require(data['schema']=='openmitrastar.f358-installer-inputs/v1','input_binding_schema');return data
def images():
    candidate=binding()['candidate'];require(candidate['kernel_build']=='#358' and '-f358-' in candidate['version'] and candidate['marker']=='F340_WATCHDOG_BASELINE','candidate_identity')
    result={}
    for name,spec in [('f358',candidate),('f340',original.SPECS['f340'])]:
        folder=Path(spec['directory']) if Path(spec['directory']).is_absolute() else DEVICE/spec['directory'];path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes();manifest=folder/'manifest.json'
        require(len(data)==spec['bytes'] and hashlib.sha256(data).hexdigest()==spec['sha256'] and sha(manifest)==spec['manifest_sha256'],'image_binding');require(len(data)<PREFIX,'store_overlap')
        contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','bootbase_contract')
        full=data+b'\xff'*(SLOT-len(data));prefix=data+b'\xff'*(PREFIX-len(data))
        result[name]={**spec,'directory':str(folder),'path':str(path),'crc32':crc(data),'prefix_crc32':crc(prefix),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'known_hosts_path':str(folder/spec['known_hosts'])}
    require(Path(result['f358']['known_hosts_path']).read_bytes()==Path(result['f340']['known_hosts_path']).read_bytes(),'SSH_identity_changed');return result
def validate_proofs():
    source=binding();proofs=original.validate_proofs();item=source['qualification'];require(sha(item['path'])==item['sha256'],'candidate_qualification_hash');data=json.loads(Path(item['path']).read_text(encoding='ascii'))
    require(data['status']==item['status']=='PASS_OFFLINE_FULL_IMAGE_BACKEND_INACTIVE','candidate_qualification_status')
    require(data['artifact']['sha256']==source['candidate']['sha256'] and data['artifact']['bytes']==source['candidate']['bytes'] and data['manifest_sha256']==source['candidate']['manifest_sha256'] and data['product_version']==source['candidate']['version'],'candidate_qualification_binding')
    require(data['bootbase']=='PASS' and data['slot_fit'] is True and data['reproducible'] is True and data['backend_autoload'] is False and data['startup_mmio_or_writes'] is False and data['watchdog_automatic_arm'] is False and data['hardware_actions'] is False,'candidate_qualification_scope')
    return proofs+[item]
