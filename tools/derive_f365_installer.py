"""Create only F365 files; bind real candidate and installed F364 when supplied."""
from pathlib import Path
import argparse,ast,hashlib,json,os,re,shutil
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'work/kernel-port/versions/f365-installer'
STABLE_ETHERNET='f364_ethernet_identity'
STABLE_DTB='/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/f363.dtb'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(value,why):
 if not value:raise ValueError(why)
def put(p,text):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.py':ast.parse(text)
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(text,encoding='utf-8',newline='\n');os.replace(t,p)
def shift(text):
 # This admission module is shared by candidate and fallback. Its filename,
 # import and test references must not become a nonexistent F365 module.
 text=text.replace(STABLE_ETHERNET,'qqstableethernetqq').replace(STABLE_DTB,'qqstabledtbqq')
 return text.replace('f364','qqcandidateqq').replace('f363','f364').replace('qqcandidateqq','f365').replace('F364','QQCANDIDATEQQ').replace('F363','F364').replace('QQCANDIDATEQQ','F365').replace('qqstableethernetqq',STABLE_ETHERNET).replace('qqstabledtbqq',STABLE_DTB)

def candidate_binding(result_path,old):
 q=json.loads(result_path.read_text(encoding='ascii'));fallback=old['candidate']
 require(q['schema']=='openmitrastar.f365-temperature-data-image/v1' and q['status']=='PASS_OFFLINE_CACHED_TEMPERATURE_DATA_IMAGE','candidate_not_qualified')
 require(q['reproducible'] is True and q['bootbase']=='PASS' and q['slot_fit'] is True and q['automatic_sensor_activation'] is False and q['kernel_config_dt_qdrv_unchanged'] is True and q['provider_preload_gate_unchanged'] is True and q['helper_existing_actions_unchanged'] is True,'candidate_diagnostic_scope')
 p=Path(q['artifact']['path']);require(p.stat().st_size==q['artifact']['bytes'] and sha(p)==q['artifact']['sha256'] and sha(p.parent/'manifest.json')==q['manifest_sha256'],'candidate_artifact')
 require('-f365-' in q['product_version'] and q['recovery']['sha256']==fallback['sha256'] and q['recovery']['bytes']==fallback['bytes'] and q['recovery']['version']==fallback['version'] and q['recovery']['kernel_build']==fallback['kernel_build'] and sha(q['source_image_result'])==old['qualification']['sha256'],'candidate_parent_profile')
 candidate=dict(directory=str(p.parent),base=p.name.removesuffix('.webformat.bin'),bytes=q['artifact']['bytes'],sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f365',kernel_build=q['recovery']['kernel_build'],marker=fallback['marker'])
 return dict(schema='openmitrastar.f365-installer-inputs/v1',candidate=candidate,fallback=fallback,qualification=dict(path=str(result_path.resolve()),sha256=sha(result_path),status=q['status']),serial_recovery=old['serial_recovery'],boot_acceptance=old['boot_acceptance'],thermal_default=old['thermal_default'])
def prepare_template(source):
 text=shift(source).replace('work/kernel-port/versions/f364-temperature-diagnostic/temp_sens.c','work/kernel-port/versions/f365-temperature-data-diagnostic/temp_sens.c').replace('PASS_OFFLINE_F365_LIFETIME_INSTALLER','PASS_OFFLINE_F365_CACHED_SENSOR_DIAGNOSTIC_INSTALLER')
 text=text.replace("files.add(c.ROOT/'work/kernel-port/versions/f365-temperature-data-diagnostic/temp_sens.c')", "files.add(c.ROOT/'work/kernel-port/versions/f365-temperature-data-diagnostic/temp_sens.c');files.add(c.ROOT/'work/kernel-port/versions/f365-temperature-data-diagnostic/temp_diag.h')")
 text=re.sub(r"'delta',\d+\)","'delta',4)",text)
 text=text.replace("'test_f365_install_delta.py',", "'test_f365_install_delta.py','test_f365_derivation.py',")
 text=text.replace("for args,name,count in [", "for args,name,count in [([PROGRAM,str(c.ROOT/'tools/test_f365_derivation.py'),'--result',str(out/'derivation-tests.json')],'derivation',3),",1)
 text=re.sub(r'adaptation_tests=\d+',"adaptation_tests=sum(item['count'] for item in tests.values())",text)
 return text

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--candidate-result',type=Path);ap.add_argument('--baseline-install',type=Path);a=ap.parse_args();require(shutil.disk_usage(ROOT).free>500*1024*1024,'disk_admission')
 old=json.loads((ROOT/'work/kernel-port/versions/f364-installer/inputs.json').read_text(encoding='ascii'));fallback=old['candidate']
 original=(ROOT/'tools/f364_install_executor.py').read_text(encoding='utf-8')
 require(any(isinstance(node,ast.ImportFrom) and node.module==STABLE_ETHERNET and {'verify_ethernet_response','ethernet_command'} <= {name.name for name in node.names} for node in ast.parse(original).body),'stable_ethernet_import_missing')
 text=shift(original).replace('import f364_thermal_status as thermal','import f365_thermal_status as thermal')
 text=text.replace('import f365_thermal_status as thermal','import f365_thermal_status as thermal\nfrom f365_failure_snapshot import save_failure_snapshot')
 text=text.replace("        can_recover=reboot_started", "        result['failure_snapshot_written']=save_failure_snapshot(out,result)\n        can_recover=reboot_started")
 put(ROOT/'tools/f365_install_executor.py',text)
 for n in ['run_f364_install.py','run_f364_install.ps1','assert_f364_context.ps1','f364_hardware_context.ps1','test_f364_context.ps1']:
  original=(ROOT/'tools'/n).read_text(encoding='utf-8');text=shift(original).replace(shift(old['fallback']['version']),fallback['version']).replace(old['fallback']['sha256'],fallback['sha256'])
  put(ROOT/'tools'/n.replace('f364','f365'),text)
 text=prepare_template((ROOT/'tools/prepare_f364_install.py').read_text(encoding='utf-8'))
 put(ROOT/'tools/prepare_f365_install.py',text)
 if a.candidate_result:
  binding=candidate_binding(a.candidate_result,old)
  put(DEST/'inputs.json',json.dumps(binding,indent=2)+'\n')
 if a.baseline_install:
  require(a.baseline_install.is_file(),'physical_baseline_missing');r=json.loads(a.baseline_install.read_text(encoding='ascii'))
  require(r['status']=='PASS_F364_PRESERVED_JOURNAL' and r['writer']['image']==fallback['sha256'] and r['writer']['byte_compare'] is True and r['containment_confirmed'] is True and r['retain_lease_required'] is False,'physical_F364_PASS_required')
  put(DEST/'baseline.json',json.dumps(dict(install=dict(path=str(a.baseline_install.resolve()),sha256=sha(a.baseline_install))),indent=2)+'\n')
 print(json.dumps(dict(status='PREPARED_NO_PLAN',real_candidate_bound=bool(a.candidate_result),physical_baseline_bound=bool(a.baseline_install),hardware_actions=False)))
if __name__=='__main__':main()
