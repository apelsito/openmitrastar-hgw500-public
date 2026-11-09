"""Prepare F364 target identity; require real F363 install/return before sealing."""
from pathlib import Path
import argparse,ast,hashlib,json,os,shutil
ROOT=Path(__file__).resolve().parents[1]
REPORT=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f364r3-fullimage-20260921T212001Z/result.json')
DEST=ROOT/'work/kernel-port/versions/f364-installer'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(value,why):
 if not value:raise ValueError(why)
def put(path,text):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.suffix=='.py':ast.parse(text)
 t=path.with_suffix(path.suffix+'.tmp');t.write_text(text,encoding='utf-8',newline='\n');os.replace(t,path)
def shift(text):
 return text.replace('f363','qqcandidateqq').replace('f362','f363').replace('qqcandidateqq','f364').replace('F363','QQCANDIDATEQQ').replace('F362','F363').replace('QQCANDIDATEQQ','F364')
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--baseline-install',type=Path);ap.add_argument('--sensor-return',type=Path);a=ap.parse_args();require(bool(a.baseline_install)==bool(a.sensor_return),'both_physical_proofs_required');require(shutil.disk_usage(ROOT).free>500*1024*1024,'disk_admission')
 q=json.loads(REPORT.read_text(encoding='ascii'));require(q['status']=='PASS_OFFLINE_LIFETIME_START_HASH_FIXED_IMAGE' and q['kernel_config_dt_byte_identical_f363'] is True and q['f363r2_owner_guard_preserved'] is True,'candidate_contract')
 old=json.loads((ROOT/'work/kernel-port/versions/f363-installer/inputs.json').read_text(encoding='ascii'));fallback=old['candidate'];p=Path(q['artifact']['path'])
 require(sha(p)==q['artifact']['sha256'] and p.stat().st_size==q['artifact']['bytes'] and sha(p.parent/'manifest.json')==q['manifest_sha256'],'candidate_artifact_binding')
 require(q['recovery']['sha256']==fallback['sha256'] and q['recovery']['version']==fallback['version'],'F363_recovery_image')
 candidate=dict(directory=str(p.parent),base=p.name.removesuffix('.webformat.bin'),bytes=q['artifact']['bytes'],sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f364',kernel_build=fallback['kernel_build'],marker=fallback['marker'])
 binding=dict(schema='openmitrastar.f364-installer-inputs/v1',candidate=candidate,fallback=fallback,qualification=dict(path=str(REPORT),sha256=sha(REPORT),status=q['status']),serial_recovery=old['serial_recovery'],boot_acceptance=old['boot_acceptance'],thermal_default=old['thermal_default'])
 put(DEST/'inputs.json',json.dumps(binding,indent=2)+'\n')
 text=shift((ROOT/'tools/f363_install_executor.py').read_text(encoding='utf-8')).replace('from f363_recovery_delta import','from f362_recovery_delta import').replace('import f364_thermal_status as thermal','import f363_thermal_status as thermal')
 old_import='from f362_recovery_delta import serial_reboot_to_prompt, verify_ethernet_response, ethernet_command, clear_pending_break'
 require(text.count(old_import)==1,'base_ethernet_import_changed')
 text=text.replace(old_import,'from f362_recovery_delta import serial_reboot_to_prompt, clear_pending_break\nfrom f364_ethernet_identity import verify_ethernet_response, ethernet_command')
 put(ROOT/'tools/f364_install_executor.py',text)
 for n in ['run_f363_install.py','run_f363_install.ps1','assert_f363_context.ps1','f363_hardware_context.ps1','test_f363_context.ps1']:
  text=shift((ROOT/'tools'/n).read_text(encoding='utf-8')).replace('lyoko-foundation-6.9.10-f363-dual-ethernet-device',fallback['version']).replace(old['fallback']['sha256'],fallback['sha256'])
  put(ROOT/'tools'/n.replace('f363','f364'),text)
 text=shift((ROOT/'tools/prepare_f363_install.py').read_text(encoding='utf-8'))
 text=text.replace('work/kernel-port/versions/f364-temperature-diagnostic/temp_sens.c','work/kernel-port/versions/f363-temperature-diagnostic/temp_sens.c')
 text=text.replace('PASS_OFFLINE_F364_INACTIVE_THERMAL_INSTALLER','PASS_OFFLINE_F364_LIFETIME_INSTALLER')
 text=text.replace("serial_recovery=binding['serial_recovery'],", "serial_recovery=binding['serial_recovery'],baseline_proofs=c.baseline_binding(),")
 text=text.replace(" pins={str(path):c.sha(path)"," files.add(c.ROOT/'tools/test_f364_ethernet_identity.py');files.add(Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/f363.dtb'))\n pins={str(path):c.sha(path)")
 text=text.replace("'context',4)]:","'context',4),([PROGRAM,str(c.ROOT/'tools/test_f364_ethernet_identity.py'),'--result',str(out/'ethernet-identity-tests.json')],'ethernet-identity',6)]:")
 text=text.replace('adaptation_tests=7','adaptation_tests=13')
 text=text.replace('F364 platform27, dual Ethernet and seq2 store unchanged;', 'F364 platform27, dual Ethernet verified from bound DT properties and live IRQ/bridge/carrier without boot-log dependence, and seq2 store unchanged;')
 put(ROOT/'tools/prepare_f364_install.py',text)
 if a.baseline_install:
  for path in (a.baseline_install,a.sensor_return):require(path.is_file(),'physical_proof_missing')
  baseline=dict(install=dict(path=str(a.baseline_install.resolve()),sha256=sha(a.baseline_install)),sensor_return=dict(path=str(a.sensor_return.resolve()),sha256=sha(a.sensor_return)))
  put(DEST/'baseline.json',json.dumps(baseline,indent=2)+'\n')
 print(json.dumps(dict(status='PHYSICAL_PROOFS_BOUND_REVIEW_REQUIRED' if a.baseline_install else 'PREPARED_WAITING_F363_PHYSICAL_RETURN',hardware_actions=False,plan_sealed=False)))
if __name__=='__main__':main()
