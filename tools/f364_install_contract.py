"""F364 lifetime integration; accepted F363 and its sensor return are required."""
from pathlib import Path
import hashlib,json
import f363_install_contract as prior
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
ROOT,DEVICE=prior.ROOT,prior.DEVICE
LIVE,PREFIX,SLOT,STORE,STORE_BYTES=prior.LIVE,prior.PREFIX,prior.SLOT,prior.STORE,prior.STORE_BYTES
LOAD,READBACK,SCRATCH,PNP,BOOTARGS=prior.LOAD,prior.READBACK,prior.SCRATCH,prior.PNP,prior.BOOTARGS
sha,crc,require,protected_backups=prior.sha,prior.crc,prior.require,prior.protected_backups
store_binding=prior.store_binding
BINDING=ROOT/'work/kernel-port/versions/f364-installer/inputs.json'
BASELINE=ROOT/'work/kernel-port/versions/f364-installer/baseline.json'
STORE_BINDING=prior.STORE_BINDING
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f364-evidence')
def binding():
 b=json.loads(BINDING.read_text(encoding='ascii'));require(b['schema']=='openmitrastar.f364-installer-inputs/v1','binding_schema');return b
def baseline_binding():
 b=binding();s=store_binding();p=json.loads(BASELINE.read_text(encoding='ascii'));rows={}
 for kind,item in p.items():require(sha(item['path'])==item['sha256'],'baseline_proof_hash');rows[kind]=json.loads(Path(item['path']).read_text(encoding='ascii'))
 installed=rows['install'];returned=rows['sensor_return']
 require(installed['status']=='PASS_F363_PRESERVED_JOURNAL' and installed['writer']['image']==b['fallback']['sha256'] and installed['writer']['full_slot_crc32']=='b8f8acc1' and installed['store_after']['sha256']==s['sha256'] and installed['thermal_default']['enabled'] is False and installed['containment_confirmed'] and not installed['retain_lease_required'],'F363_physical_install')
 require(returned['status'] in ('PASS_F363_SENSOR_SAMPLES_AND_AUTONOMOUS_RETURN','FAIL_SENSOR_WITH_F363_RETURN') and returned['software_recovery'] is False and returned['baseline_returned'] is True and returned['return_identity']['uts']=='#358 @1790006400' and returned['thermal_after']['enabled'] is False and returned['thermal_after']['activation_attempted'] is False and returned['configuration_after']['sequence']==2 and returned['store_after']['sha256']==s['sha256'] and returned['platform_after']['status']=='PASS' and returned['platform_after']['checks']==27 and returned['watchdog_after']['device_opened']==0 and int(returned['watchdog_after']['control'],16)&1==0 and returned['containment_confirmed'] and not returned['retain_lease_required'],'F363_sensor_return_not_proven')
 return {**p,'sensor_status':returned['status'],'sensor_error':returned.get('error'),'temperature_accepted':returned['status']=='PASS_F363_SENSOR_SAMPLES_AND_AUTONOMOUS_RETURN','safe_return_verified':True}
def images():
 b=binding();s=store_binding();store=Path(s['path']).read_bytes();result={}
 for name,spec in [('f364',b['candidate']),('f363',b['fallback'])]:
  folder=Path(spec['directory']);path=folder/(spec['base']+'.webformat.bin');data=path.read_bytes();require(len(data)==spec['bytes'] and len(data)<PREFIX and sha(path)==spec['sha256'] and sha(folder/'manifest.json')==spec['manifest_sha256'],'image_binding')
  contract=image_to_dict(validate_bootbase_slot(name,data,SLOT));require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','bootbase_contract')
  prefix=data+b'\xff'*(PREFIX-len(data));full=prefix+store
  result[name]={**spec,'path':str(path),'known_hosts_path':str(folder/spec['known_hosts']),'crc32':crc(data),'prefix_crc32':crc(prefix),'full_slot_crc32':crc(full),'full_slot_sha256':hashlib.sha256(full).hexdigest(),'preserved_store_sha256':s['sha256'],'full_slot_scope':'firmware prefix plus exact seq2 store'}
 require(Path(result['f364']['known_hosts_path']).read_bytes()==Path(result['f363']['known_hosts_path']).read_bytes(),'SSH_identity_changed');require(result['f364']['full_slot_crc32']=='d7a19077' and result['f363']['full_slot_crc32']=='b8f8acc1','operational_fullslot_crc');return result
def validate_proofs():
 b=binding();q=b['qualification'];require(sha(q['path'])==q['sha256'],'qualification_hash');r=json.loads(Path(q['path']).read_text(encoding='ascii'));require(r['status']==q['status'] and r['status']=='PASS_OFFLINE_LIFETIME_START_HASH_FIXED_IMAGE' and r['kernel_config_dt_byte_identical_f363'] is True and r['f363r2_owner_guard_preserved'] is True and r['artifact']['sha256']==b['candidate']['sha256'] and r['manifest_sha256']==b['candidate']['manifest_sha256'],'qualification_binding')
 p=baseline_binding();return prior.validate_proofs()+[q,p['install'],p['sensor_return']]
