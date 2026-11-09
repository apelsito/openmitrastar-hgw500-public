"""Keep the proven launcher/lease mechanics; change only first-SAVE authority."""
from pathlib import Path
import ast,os
ROOT=Path(__file__).resolve().parents[1]
def main():
 for old,new in [('run_f359_observe.py','run_f360_save.py'),('run_f359_observe.ps1','run_f360_save.ps1'),('assert_f359_context.ps1','assert_f360_context.ps1'),('f359_hardware_context.ps1','f360_hardware_context.ps1')]:
  text=(ROOT/'tools'/old).read_text(encoding='utf-8').replace('F359','F360').replace('f359','f360').replace('f360_observe_executor','f360_save_executor').replace('f360-observe','f360-save')
  text=text.replace('PASS_OFFLINE_LIVE_OBSERVE_GATE','PASS_OFFLINE_FIRST_SAVE_GATE').replace('PASS_F360_OBSERVE_CONTEXT','PASS_F360_SAVE_CONTEXT').replace('f358-live-observe-once','f358-first-config-save')
  if old.endswith('.ps1'):
   text=text.replace('$p.allow_program -or','-not $p.allow_program -or').replace('$c.allow_program -or','-not $c.allow_program -or').replace('allow_program=$false','allow_program=$true')
   text=text.replace("($p.observation_commands -join '|') -cne 'observe'","($p.operations -join '|') -cne 'save|load'")
   text=text.replace("-Owner 'F360_LIVE_OBSERVE'","-Owner 'F360_FIRST_SAVE'")
  if old=='run_f359_observe.ps1':
   text=text.replace("purpose='f358-first-config-save';baseline_sha256", "purpose='f358-first-config-save';payload_sha256=$p.payload.sha256;baseline_sha256")
  if old=='f359_hardware_context.ps1':
   text=text.replace("$c.allow_program -isnot [bool]", "$c.payload_sha256 -cne '073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9' -or $c.allow_program -isnot [bool]")
   text=text.replace("($p.operations -join '|') -cne 'save|load' -or", "($p.operations -join '|') -cne 'save|load' -or $p.save_calls -ne 1 -or $p.rollback_erase_allowed -isnot [bool] -or $p.rollback_erase_allowed -or $p.payload.sha256 -cne $c.payload_sha256 -or")
  if new.endswith('.py'):ast.parse(text)
  path=ROOT/'tools'/new;tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path)
 print('F360_LAUNCHERS_READY')
if __name__=='__main__':main()
