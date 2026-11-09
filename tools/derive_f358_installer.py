"""Minimal profile adaptation of the physically proven F346 installer. Offline."""
from pathlib import Path
import ast,hashlib,os,shutil
ROOT=Path(__file__).resolve().parents[1]
def put(name,text):
    if shutil.disk_usage('C:/').free<=500*1024*1024:raise RuntimeError('disk_admission_floor')
    path=ROOT/'tools'/name
    if path.exists():raise RuntimeError('output_already_exists_'+name)
    if path.suffix=='.py':ast.parse(text)
    tmp=path.with_name(path.name+'.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path)
def main():
    source=ROOT/'tools/f346_install_executor.py';data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!='ae4175cad9cb5d45035e6e1c05357ad955b597964e27e66e27158914814fda5d':raise RuntimeError('F346_source_drift')
    text=data.decode('utf-8').replace('f346_install_contract','f358_install_contract').replace('assert_f346_context','assert_f358_context').replace('OM_F346_CONTEXT','OM_F358_CONTEXT').replace('PASS_F346_INSTALL_CONTEXT','PASS_F358_INSTALL_CONTEXT').replace('openmitrastar.f346-','openmitrastar.f358-')
    text=text.replace("['images']['f340']","['images']['candidate358']").replace("['images']['f321']","['images']['f340']").replace("['images']['candidate358']","['images']['f358']")
    for old,new in [("host.identity('f321')","host.identity('f340')"),("boot_written(uart,host,plan,'f340'","boot_written(uart,host,plan,'candidate358'"),("boot_written(uart,host,plan,'f321'","boot_written(uart,host,plan,'f340'"),("boot_written(uart,host,plan,'candidate358'","boot_written(uart,host,plan,'f358'"),("host.platform('f340'","host.platform('candidate358'"),("host.platform('f321'","host.platform('f340'"),("host.platform('candidate358'","host.platform('f358'")]:text=text.replace(old,new)
    for old,new in [('f346-private-backup','f358-private-backup'),('backup-reference-f321','backup-reference-f340'),('current_f321_crc32','current_f340_crc32'),("result['f340_identity']","result['f358_identity']"),('install-f340','install-f358'),('boot-f340','boot-f358'),('platform-f340','platform-f358'),('restore-f321','restore-f340'),('boot-f321-return','boot-f340-return'),('platform-f321','platform-f340'),('complete-f340-kept','complete-f358-kept'),('complete-f321-returned','complete-f340-returned'),('PASS_F340_PERSISTENT_WATCHDOG_BASELINE','PASS_F358_PERSISTENT_BASELINE'),('FAILED_F340_WITH_EXACT_F321_RETURN','FAILED_F358_WITH_EXACT_F340_RETURN')]:text=text.replace(old,new)
    text=text.replace('"""F340 install with the verified TFTP/UART primitives and F321 write protocol.','"""F358 install with the verified F346 TFTP/UART/write protocol and F340 return.').replace('F346 lease/nonce context.','F358 lease/nonce context.')
    text=text.replace("result['rollback_reference']=host.backup_reference()","result['baseline_watchdog']=host.watchdog_inactive();result['rollback_reference']=host.backup_reference()")
    text=text.replace("result['return_platform']=host.platform('f340',out/'platform-f340')","result['return_platform']=host.platform('f340',out/'platform-f340');result['returned_watchdog']=host.watchdog_inactive()")
    put('f358_install_executor.py',text)
    fixture=(ROOT/'tools/test_f346_install.py').read_text(encoding='utf-8').split('class Flow(unittest.TestCase):')[0]
    fixture=fixture.replace('f346_install_executor','f358_install_executor').replace('f346_install_contract','f358_install_contract').replace('f340','candidate358').replace('f321','f340').replace('candidate358','f358')
    fixture=fixture.replace('f358=self.plan','f340=self.plan')
    put('f358_install_test_fixture.py',fixture)
    text=(ROOT/'tools/run_f346_watchdog_install.ps1').read_text(encoding='utf-8')
    text=text.replace('F346','F358').replace('f346_install_executor','f358_install_executor').replace('f346_hardware_context','f358_hardware_context').replace('openmitrastar.f346-','openmitrastar.f358-').replace('f346-install-','f358-install-')
    text=text.replace('.images.f340','.images.candidate358').replace('.images.f321','.images.f340').replace('.images.candidate358','.images.f358')
    text=text.replace('f340-install-conditional-f321-return','f358-install-conditional-f340-return').replace("-Owner 'F358_F340_INSTALL'","-Owner 'F358_INSTALL_F340_RETURN'")
    anchor=". (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')"
    text=text.replace(anchor,"if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'F358_REQUIRES_WINDOWS_POWERSHELL_51'}\n"+anchor)
    text=text.replace("$dir=Join-Path $F358Root ('outputs\\handoff-live\\f358-install-'", "$dir=Join-Path $plan.evidence_root ('f358-install-'")
    put('run_f358_install.ps1',text)
    text=(ROOT/'tools/assert_f346_context.ps1').read_text(encoding='utf-8').replace('f346_hardware_context','f358_hardware_context').replace('F346','F358')
    put('assert_f358_context.ps1',text)
    print('F358_PROFILE_DERIVATION_READY_NO_HARDWARE')
if __name__=='__main__':main()
