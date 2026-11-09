"""Seal the first real configuration SAVE plan; preparation is strictly offline."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys
import f360_save_executor as executor
import f358_install_contract as c
import f346_powershell as desktop_ps
CONTRACT=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f360-config-contract-20260921T182515Z/manifest.json'
CONTRACT_SHA='387a62850583db4c1cac6db207200cc806eddc1d550c845ce42135d972c1b4dc'
PREVIOUS=c.ROOT/'outputs/preflight/f359-observe-20260921T180606Z/plan.json'
PHYSICAL=Path('/workspace/OpenMitraStar/f359-evidence/f359-observe-20260921T180806Z-10cd4f98/result.json')
def main():
 executor.disk_floor();c.require(c.sha(CONTRACT)==CONTRACT_SHA,'private_expectation_drift');expected=json.loads(CONTRACT.read_text(encoding='ascii'))
 c.require(expected['status']=='PASS_PRIVATE_CONFIG_EXPECTATION' and expected['payload_values_changed'] is False and expected['generation']['save_calls']==1 and expected['generation']['slot']==0 and expected['generation']['sequence']==1 and expected['rollback']['erase_allowed'] is False,'private_expectation_scope')
 c.require(c.sha(PREVIOUS)=='a146edec9ac8d41ddfd08ec422b78f874da5fb9c69dd28ca7c956773364bad55','previous_plan_drift');prior=json.loads(PREVIOUS.read_text(encoding='ascii'))
 c.require(c.sha(PHYSICAL)=='3fc6c70a53bfec5894a2b57f33ec53cf0708f8f429e76debdf33e62776182037','observe_proof_drift');live=json.loads(PHYSICAL.read_text(encoding='ascii'))
 c.require(live['status']=='PASS_F359_READONLY_OBSERVE_AND_F358_RETURN' and live['observation']['id']=='c22018' and live['observation']['common_bp0']==1 and live['observation']['status_register']==0 and live['observation']['security_register']==0 and live['return']['platform']['checks']==27 and live['containment_confirmed'] is True,'positive_observation_required')
 images={'f358':c.images()['f358']};payload=expected['payload'];c.require(0<payload['bytes']<=4096,'payload_limit')
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
 for path,digest in expected['source_pins'].items():c.require(c.sha(path)==digest,'expectation_source_drift');files.add(Path(path))
 for item in [payload,*expected['artifacts'].values()]:c.require(c.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'],'expected_artifact_drift');files.add(Path(item['path']))
 art=expected['artifacts'];prefix=Path(images['f358']['path']).read_bytes()+b'\xff'*(c.PREFIX-images['f358']['bytes']);store=Path(art['expected-store.bin']['path']).read_bytes()
 c.require(c.crc(prefix)==expected['expected_after_save']['firmware_prefix_crc32'] and c.crc(prefix+store)==expected['expected_after_save']['full_slot_crc32'] and len(store)==c.STORE_BYTES,'expected_full_slot_binding')
 c.require(Path(art['expected-dc-dd.bin']['path']).read_bytes()==Path(art['expected-dc.bin']['path']).read_bytes()+Path(art['expected-dd.bin']['path']).read_bytes(),'expected_pair_binding')
 executor.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for path in (executor.EVIDENCE_ROOT,*executor.EVIDENCE_ROOT.parents):c.require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'evidence_reparse')
 files.update([CONTRACT,PREVIOUS,PHYSICAL,c.BINDING]);files.update(Path(path) for path in prior['sources'])
 files.update(c.ROOT/'tools'/name for name in ['derive_f360_executor.py','derive_f360_launchers.py','f360_executor_header.inc','f360_executor_footer.inc','prepare_f360_save.py','test_f360_save.py','test_f360_context.ps1','test_f356_observe.py','run_f360_save.py','run_f360_save.ps1','f360_hardware_context.ps1','assert_f360_context.ps1'])
 pins={str(path):c.sha(path) for path in sorted(files)}
 out=c.ROOT/'outputs/preflight'/('f360-save-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 jobs=[([sys.executable,str(c.ROOT/'tools/test_f360_save.py'),'--result',str(out/'save-tests.json')],'save-tests'),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f360_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests')]
 for args,name in jobs:
  r=subprocess.run(args,env=desktop_ps.environment() if name=='context-tests' else None,capture_output=True,timeout=120);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
  if r.returncode:executor.save(out/'result.json',dict(status='FAIL_ADAPTATION_TESTS',test=name,hardware_actions=False))
  c.require(r.returncode==0,name+'_failed')
 tests={}
 for name,count in [('save',7),('context',4)]:
  path=out/(name+'-tests.json');r=json.loads(path.read_text(encoding='ascii'));c.require(r['passed'] is True and r['tests']==count,'test_count');tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
 c.require(all(c.sha(path)==digest for path,digest in pins.items()),'source_drift_during_tests')
 carry={key:prior[key] for key in ['provider','cli','supervisor','loader','known_hosts','uart_pnp_device_id','physical_lock_dir','network']}
 plan=dict(schema='openmitrastar.f360-save-plan/v1',status='PASS_OFFLINE_FIRST_SAVE_GATE',sources=pins,tests=tests,images=images,protected=c.protected_backups(),bootargs=c.BOOTARGS,**carry,
  payload=payload,expected=expected,private_contract=dict(path=str(CONTRACT),sha256=CONTRACT_SHA),positive_observe=dict(path=str(PHYSICAL),sha256=c.sha(PHYSICAL)),
  operations=['save','load'],save_calls=1,allow_program=True,one_shot=True,rollback_erase_allowed=False,ram_kernel_boot=False,tftp_allowed=False,radio_actions=False,hardware_actions=False,evidence_root=str(executor.EVIDENCE_ROOT.resolve()),
  success_policy='One SAVE seq1/DC, one validated LOAD hash/length, clean unload/CEASE/reset, immutable F358 firmware prefix/protected, expected NEW store/full-slot CRC and private byte-exact DC/DD+storeSHA after reboot.',
  failure_policy='No second SAVE, no erase restoration, no unload after uncertain transaction. CEASE/reset, verify F358 prefix/protected and archive private DC/DD on return; incomplete journal may remain and backend is not auto-loaded.',
  privacy='Payload only via stdin/RAM0600; MTD readback stored in private ACL child directory; public metadata contains hashes/lengths only.',
  limits=['Initial DC/DD and remaining store must be verified FF before ARM','Provider permits DC/DD only; the first empty-journal transaction must choose DC slot0 sequence1','Firmware prefixCRCdf453410 is immutable; full-slotCRC legitimately changes from4d006632 to3e8db0dc','No interpretation of IDc22018 as an exact35F/36E part','No WiFi or deliberate CPU/bus halt tests'])
 path=out/'plan.json';executor.save(path,plan);digest=c.sha(path);executor.load_plan(path,digest)
 for args,name in [([sys.executable,str(c.ROOT/'tools/run_f360_save.py'),'--plan',str(path),'--plan-sha256',digest],'default-launcher'),([sys.executable,str(c.ROOT/'tools/f360_save_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-worker')]:
  r=subprocess.run(args,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);c.require(r.returncode==0 and not r.stderr,name+'_failed')
 summary=dict(status='PASS_OFFLINE_F360_FIRST_SAVE',plan=str(path),plan_sha256=digest,adaptation_tests=11,source_pins=len(pins),payload_sha256=payload['sha256'],payload_bytes=payload['bytes'],evidence_root=str(executor.EVIDENCE_ROOT),hardware_actions=False,default_entrypoints_read_only=True)
 executor.save(out/'result.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
