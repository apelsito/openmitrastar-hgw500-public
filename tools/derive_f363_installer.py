"""Prepare F363 executors now; bind only a real qualified candidate later."""
from pathlib import Path
import argparse,ast,hashlib,json,os,shutil
ROOT=Path(__file__).resolve().parents[1]
BASE_PLAN=ROOT/'outputs/preflight/f362-install-20260921T201143Z/plan.json'
BASE_RESULT=Path('/workspace/OpenMitraStar/f362-evidence/f362-install-20260921T201238Z-d650b1af/result.json')
DEST=ROOT/'work/kernel-port/versions/f363-installer'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,why):
 if not value:raise ValueError(why)
def put(path,text):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.suffix=='.py':ast.parse(text)
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path)
def shift(text):
 return text.replace('F361_READY','QQREADYQQ').replace('f362','qqcandidateqq').replace('f361','f362').replace('qqcandidateqq','f363').replace('F362','QQCANDIDATEQQ').replace('F361','F362').replace('QQCANDIDATEQQ','F363').replace('QQREADYQQ','F361_READY')
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--candidate-result',type=Path);a=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'disk_admission')
 require(sha(BASE_PLAN)=='57501957cf30853b5b1e2f7b935430ca1aafea2cca0b1b516ab98c0e0ed735cb','tested_base_plan')
 plan=json.loads(BASE_PLAN.read_text(encoding='ascii'));result=json.loads(BASE_RESULT.read_text(encoding='ascii'))
 require(result['status']=='PASS_F362_PRESERVED_JOURNAL' and result['containment_confirmed'] and not result['retain_lease_required'],'physical_baseline')
 baseline=json.loads((ROOT/'work/kernel-port/versions/f362-installer/inputs.json').read_text(encoding='ascii'))
 fallback=baseline['candidate'];require(fallback['sha256']==result['writer']['image'] and result['writer']['full_slot_crc32']=='1a6e28c0','baseline_image')
 baseline_record=dict(fallback=fallback,physical_result=dict(path=str(BASE_RESULT),sha256=sha(BASE_RESULT)),tested_plan=dict(path=str(BASE_PLAN),sha256=sha(BASE_PLAN)))
 put(DEST/'baseline.json',json.dumps(baseline_record,indent=2)+'\n')
 source=ROOT/'tools/f362_install_executor.py';require(sha(source)==plan['sources'][str(source)],'tested_executor_drift')
 text=shift(source.read_text(encoding='utf-8')).replace('from f363_recovery_delta import','from f362_recovery_delta import')
 text=text.replace('import f336_wdt_ram_executor as base','import f336_wdt_ram_executor as base\nimport f363_thermal_status as thermal')
 text=text.replace('    def verify_store(self):','    def verify_thermal_disabled(self):\n        return thermal.validate(self.ssh(thermal.command()))\n    def verify_store(self):')
 text=text.replace("result['ethernet']=host.verify_ethernet()","result['ethernet']=host.verify_ethernet();result['thermal_default']=host.verify_thermal_disabled()")
 put(ROOT/'tools/f363_install_executor.py',text)
 for name in ['run_f362_install.py','run_f362_install.ps1','assert_f362_context.ps1','f362_hardware_context.ps1','test_f362_context.ps1']:
  source=ROOT/'tools'/name;require(sha(source)==plan['sources'][str(source)],'tested_launcher_drift');text=shift(source.read_text(encoding='utf-8'))
  text=text.replace('lyoko-foundation-6.9.9-f362-config-persistence-device',fallback['version']).replace('0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af',fallback['sha256'])
  put(ROOT/'tools'/name.replace('f362','f363'),text)
 text=shift((ROOT/'tools/prepare_f362_install.py').read_text(encoding='utf-8'))
 text=text.replace("'delta',7)","'delta',3)").replace('adaptation_tests=11','adaptation_tests=7')
 text=text.replace("c.BINDING,c.STORE_BINDING,", "c.BINDING,c.BASELINE,c.STORE_BINDING,")
 text=text.replace("  write_target='mtd4/linux_live'", "  thermal_default=binding['thermal_default'],sensor_activation_allowed=False,\n  write_target='mtd4/linux_live'")
 text=text.replace("F363 platform27 plus both Ethernet netdevs/IRQ/DT mapping in br0; either carrier accepted. Exact seq2 store unchanged.", "F363 platform27, dual Ethernet and seq2 store unchanged; thermal cached state is disabled with no activation attempt. No temperature sampling or activation.")
 text=text.replace("# Primary driver source binds the exact registration/IRQ readback strings.", "# Reuse Ethernet acceptance; pin only the thermal wrapper source delta.")
 text=text.replace(" pins={str(path):c.sha(path)", " files.add(c.ROOT/'work/kernel-port/versions/f363-temperature-diagnostic/temp_sens.c')\n pins={str(path):c.sha(path)")
 text=text.replace('PASS_OFFLINE_F363_STORE_AND_SERIAL_RECOVERY','PASS_OFFLINE_F363_INACTIVE_THERMAL_INSTALLER')
 put(ROOT/'tools/prepare_f363_install.py',text)
 if a.candidate_result:
  q=json.loads(a.candidate_result.read_text(encoding='ascii'));require(q['status'].startswith('PASS_'),'candidate_not_qualified');artifact=q['artifact'];path=Path(artifact['path']);folder=path.parent
  require(path.stat().st_size==artifact['bytes'] and sha(path)==artifact['sha256'] and sha(folder/'manifest.json')==q['manifest_sha256'],'candidate_artifact_drift')
  version=q['product_version'];require(version in ('lyoko-foundation-6.9.11-f363-temperature-diagnostic-device','lyoko-foundation-6.9.11-f363r2-temperature-owner-device') and q['kernel_build']=='#358','candidate_profile')
  candidate=dict(directory=str(folder),base=path.name.removesuffix('.webformat.bin'),bytes=artifact['bytes'],sha256=artifact['sha256'],manifest_sha256=q['manifest_sha256'],version=version,known_hosts='known_hosts.f363',kernel_build=q['kernel_build'],marker='F340_WATCHDOG_BASELINE')
  record=dict(schema='openmitrastar.f363-installer-inputs/v1',candidate=candidate,fallback=fallback,qualification=dict(path=str(a.candidate_result.resolve()),sha256=sha(a.candidate_result),status=q['status']),baseline=baseline_record,serial_recovery=baseline['serial_recovery'],boot_acceptance=baseline['boot_acceptance'],thermal_default=dict(enabled=0,activation_attempted=0,activation_error=-19,sensor_mmio=False))
  put(DEST/'inputs.json',json.dumps(record,indent=2)+'\n')
 print(json.dumps(dict(status='CANDIDATE_BOUND' if a.candidate_result else 'PREPARED_WAITING_REAL_CANDIDATE',hardware_actions=False,plan_sealed=False)))
if __name__=='__main__':main()
