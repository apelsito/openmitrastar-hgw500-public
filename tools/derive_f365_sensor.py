"""Prepare a single F365 sample pair, retaining the existing owner/reset flow."""
from pathlib import Path
import ast,os,re
ROOT=Path(__file__).resolve().parents[1]
def put(p,text):
 p=Path(p)
 if p.suffix=='.py':ast.parse(text)
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(text,encoding='utf-8',newline='\n');os.replace(t,p)
def main():
 text=(ROOT/'tools/f363_sensor_executor.py').read_text(encoding='utf-8').replace('f363','f365').replace('F363','F365')
 text=text.replace('import f365_sensor_protocol as protocol','import f363_sensor_protocol as protocol')
 text=text.replace('for index in range(3):','for index in range(1):').replace("plan['sample_pairs']==3","plan['sample_pairs']==1")
 text=text.replace("result['watchdog_before']=host.preflight();", "result['watchdog_before']=host.preflight();result['thermal_before']=host.verify_thermal_disabled();")
 put(ROOT/'tools/f365_sensor_executor.py',text)
 for old,new in [('run_f363_sensor.py','run_f365_sensor.py'),('run_f363_sensor.ps1','run_f365_sensor.ps1'),('assert_f363_sensor_context.ps1','assert_f365_sensor_context.ps1'),('f363_sensor_context.ps1','f365_sensor_context.ps1')]:
  text=(ROOT/'tools'/old).read_text(encoding='utf-8').replace('f363','f365').replace('F363','F365').replace('$p.sample_pairs -ne 3','$p.sample_pairs -ne 1')
  if old=='f363_sensor_context.ps1':
   text=re.sub(r"\$c\.binding\.ExpectedVersion -cne '[^']+' -or ", '',text)
   text=text.replace("$c.baseline_sha256 -cne $p.images.f365.sha256", "$c.binding.ExpectedVersion -cne $p.images.f365.version -or $c.baseline_sha256 -cne $p.images.f365.sha256")
  put(ROOT/'tools'/new,text)
 text=(ROOT/'tools/test_f363_sensor_context.ps1').read_text(encoding='utf-8').replace('f363','f365').replace('F363','F365').replace('sample_pairs=3','sample_pairs=1')
 text=text.replace("kernel_build='#358'", "kernel_build='#358';version='fixture-f365'")
 text=re.sub(r"ExpectedVersion='[^']+'", "ExpectedVersion='fixture-f365'",text)
 put(ROOT/'tools/test_f365_sensor_context.ps1',text)
 text=(ROOT/'tools/prepare_f363_sensor.py').read_text(encoding='utf-8').replace('f363','f365').replace('F363','F365')
 text=text.replace('sample_pairs=3','sample_pairs=1').replace('three successful independent hwmon/interval pairs','one successful independent hwmon/interval pair')
 text=text.replace('work/kernel-port/versions/f365-temperature-diagnostic','work/kernel-port/versions/f365-temperature-data-diagnostic')
 text=text.replace("['temp_sens.c','topaz_temp_core.h']", "['temp_sens.c','topaz_temp_core.h','temp_diag.h']")
 text=text.replace("'test_f365_sensor.py','test_f365_sensor_error_format.py'", "'test_f365_sensor_cache.py'")
 text=text.replace('derive_f365_sensor_launchers.py','derive_f365_sensor.py')
 text=text.replace('outputs/preflight/f365-temperature-activation-20260921T213105Z','outputs/preflight/f363-temperature-activation-20260921T214010Z')
 text=text.replace('/workspace/OpenMitraStar/f365-temperature-activation/f365-sensor-20260921T213150Z-f83f8f12/result.json','/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T214213Z-12cff874/result.json')
 text=text.replace("failed['status']=='FAIL_SENSOR_WITH_F365_RETURN'", "failed['status']=='FAIL_SENSOR_WITH_F363_RETURN'")
 text=text.replace("test_f365_sensor_error_format.py'),'--result',str(out/'error-format-tests.json')],'error-format',4)", "test_f365_sensor_cache.py'),'--result',str(out/'cache-tests.json')],'cache',4),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f365_sensor_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context',4)")
 text=text.replace('Preserve known cat stderr before reset; errno label inferred from exact libc message, not a captured syscall errno.','Preserve exact cached F365 errno, DATA words, read count and elapsed time before reset; no retry after a failed read.')
 text=text.replace('PASS_OFFLINE_F365_SENSOR_ERROR_DIAGNOSTIC','PASS_OFFLINE_F365_SENSOR_DATA_DIAGNOSTIC').replace('new_format_checks=4,reused_checks=10','new_format_checks=8,reused_checks=14')
 put(ROOT/'tools/prepare_f365_sensor.py',text)
 print('F365_SENSOR_PREPARED_NO_IMAGE_OR_HARDWARE')
if __name__=='__main__':main()
