"""Reuse the tested F359 lease/nonce/claim launcher for one thermal trial."""
from pathlib import Path
import ast,os
ROOT=Path(__file__).resolve().parents[1]
def put(name,text):
 p=ROOT/'tools'/name
 if p.suffix=='.py':ast.parse(text)
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(text,encoding='utf-8',newline='\n');os.replace(t,p)
def main():
 for source,dest in [('run_f359_observe.py','run_f363_sensor.py'),('run_f359_observe.ps1','run_f363_sensor.ps1'),('assert_f359_context.ps1','assert_f363_sensor_context.ps1')]:
  text=(ROOT/'tools'/source).read_text(encoding='utf-8').replace('F359','F363_SENSOR').replace('f359_hardware_context','f363_sensor_context').replace('f359_observe_executor','f363_sensor_executor').replace('f359-observe','f363-sensor').replace('f359-evidence','f363-temperature-activation').replace('outputs/claims/f359','outputs/claims/f363-sensor').replace('f358-live-observe-once','f363-sensor-activation-once').replace('.images.f358','.images.f363').replace('.provider','.sensor_module').replace('provider_sha256','sensor_sha256')
  text=text.replace('PASS_OFFLINE_LIVE_OBSERVE_GATE','PASS_OFFLINE_SENSOR_ACTIVATION').replace('$p.allow_program -isnot [bool] -or $p.allow_program -or $p.ram_kernel_boot -or $p.tftp_allowed','$p.flash_writes -isnot [bool] -or $p.flash_writes -or $p.autoboot_intercept -or $p.activation_attempts -ne 1 -or $p.sample_pairs -ne 3')
  text=text.replace('allow_program=$false;','flash_writes=$false;').replace('PASS_F363_SENSOR_OBSERVE_CONTEXT','PASS_F363_SENSOR_CONTEXT')
  put(dest,text)
 print('F363_SENSOR_LAUNCHERS_PREPARED_NO_HARDWARE')
if __name__=='__main__':main()
