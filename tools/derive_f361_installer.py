"""Small F358 installer adaptation: preserve real journal data through firmware updates."""
from pathlib import Path
import ast,os
ROOT=Path(__file__).resolve().parents[1]
def put(name,text):
 path=ROOT/'tools'/name
 if path.suffix=='.py':ast.parse(text)
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,path)
def main():
 text=(ROOT/'tools/f358_install_executor.py').read_text(encoding='utf-8').replace('f358_install_contract','f361_install_contract').replace('assert_f358_context','assert_f361_context').replace('OM_F358_CONTEXT','OM_F361_CONTEXT').replace('PASS_F358_INSTALL_CONTEXT','PASS_F361_INSTALL_CONTEXT').replace('openmitrastar.f358-','openmitrastar.f361-')
 text=text.replace("['images']['f358']","['images']['candidate361']").replace("['images']['f340']","['images']['f358']").replace("['images']['candidate361']","['images']['f361']")
 for old,new in [("host.identity('f340')","host.identity('f358')"),("boot_written(uart,host,plan,'f358'","boot_written(uart,host,plan,'candidate361'"),("boot_written(uart,host,plan,'f340'","boot_written(uart,host,plan,'f358'"),("boot_written(uart,host,plan,'candidate361'","boot_written(uart,host,plan,'f361'"),("host.platform('f358'","host.platform('candidate361'"),("host.platform('f340'","host.platform('f358'"),("host.platform('candidate361'","host.platform('f361'")]:text=text.replace(old,new)
 for old,new in [('f358-private-backup','f361-private-backup'),('backup-reference-f340','backup-reference-f358'),('current_f340_crc32','current_f358_crc32'),("result['f358_identity']","result['f361_identity']"),('install-f358','install-f361'),('boot-f358','boot-f361'),('platform-f358','platform-f361'),('restore-f340','restore-f358'),('boot-f340-return','boot-f358-return'),('platform-f340','platform-f358'),('complete-f358-kept','complete-f361-kept'),('complete-f340-returned','complete-f358-returned'),('PASS_F358_PERSISTENT_BASELINE','PASS_F361_PRESERVED_JOURNAL'),('FAILED_F358_WITH_EXACT_F340_RETURN','FAILED_F361_WITH_F358_AND_PRESERVED_JOURNAL')]:text=text.replace(old,new)
 text=text.replace("plan['erased_store_crc32']","plan['store']['crc32']")
 text=text.replace("        flash_crc(uart,c.LIVE,c.PREFIX,plan['erased_prefix_crc32'])","        flash_crc(uart,c.LIVE,c.PREFIX,plan['erased_prefix_crc32'])\n        # Non-FF journal is checked immediately after erase, before programming.\n        flash_crc(uart,c.STORE,c.STORE_BYTES,store_crc)")
 marker='    def watchdog_inactive(self):'
 method='''    def verify_store(self):
        rows=self.ssh('cat /proc/mtd').splitlines();matches=[row for row in rows if row.endswith(b'"lyoko_store"')]
        require(len(matches)==1 and re.fullmatch(rb'mtd4:\\s+001c0000\\s+00010000\\s+"lyoko_store"',matches[0]),'unique_store_geometry')
        flags=int(self.ssh('cat /sys/class/mtd/mtd4/flags').strip(),0);require(not flags&0x400,'store_mtd_not_readonly')
        output=self.ssh('[ -c /dev/mtd4 ] && sha256sum /dev/mtd4',timeout=60).split()
        require(output==[self.plan['store']['sha256'].encode(),b'/dev/mtd4'],'preserved_store_changed')
        return dict(sha256=self.plan['store']['sha256'],bytes=self.plan['store']['bytes'],read_only_mtd=True)
    def verify_configuration(self):
        command="printf 'ready='; cat /run/openmitrastar/config-journal/ready; cat /run/openmitrastar/config-journal/state; printf 'active_sha256='; sha256sum /run/openmitrastar/config/active.conf | awk '{print $1}'; printf 'allow_hw='; cat /sys/module/qtn_f356_journal/parameters/allow_hw; printf 'allow_program='; cat /sys/module/qtn_f356_journal/parameters/allow_program"
        pairs=[line.split('=',1) for line in self.ssh(command).decode('ascii').splitlines()]
        require(all(len(row)==2 for row in pairs) and len({row[0] for row in pairs})==len(pairs),'config_boot_response')
        rows=dict(pairs);expected=self.plan['boot_acceptance']['payload_sha256']
        require(rows==dict(ready='F361_READY',slot='A',sequence='1',sha256=expected,source='journal',active_sha256=expected,allow_hw='Y',allow_program='Y'),'journal_not_applied_or_backend_unready')
        return dict(source='journal',sequence=1,slot='A',active_sha256=expected,backend_allow_hw=True,backend_allow_program=True)
'''
 text=text.replace(marker,method+marker)
 text=text.replace("result['baseline_watchdog']=host.watchdog_inactive();", "result['baseline_watchdog']=host.watchdog_inactive();result['store_before']=host.verify_store();")
 text=text.replace("result['watchdog']=host.watchdog_inactive()", "result['watchdog']=host.watchdog_inactive();result['store_after']=host.verify_store();result['configuration_boot']=host.verify_configuration()")
 text=text.replace("result['returned_watchdog']=host.watchdog_inactive()", "result['returned_watchdog']=host.watchdog_inactive();result['returned_store']=host.verify_store()")
 text=text.replace("require(plan['images']==c.images(),'image_contract')", "require(plan['images']==c.images() and plan['store']==c.store_binding(),'image_and_store_contract')")
 text=text.replace('F358 install with the verified F346 TFTP/UART/write protocol and F340 return.','F361 firmware-prefix install preserving the committed journal; F358 return.').replace('F358 lease/nonce context.','F361 lease/nonce context.')
 put('f361_install_executor.py',text)
 fixture=(ROOT/'tools/f358_install_test_fixture.py').read_text(encoding='utf-8').replace('f358_install_executor','f361_install_executor').replace('f358_install_contract','f361_install_contract').replace('f358','candidate361').replace('f340','f358').replace('candidate361','f361').replace('f361=self.plan','f340=self.plan').replace('f358=self.plan','f340=self.plan')
 fixture=fixture.replace("self.flash=bytearray(self.images['f358']+b'\\xff'*(c.SLOT-len(self.images['f358'])))", "self.flash=bytearray(self.images['f358']+b'\\xff'*(c.PREFIX-len(self.images['f358']))+Path(plan['store']['path']).read_bytes())")
 fixture=fixture.replace('    def watchdog_inactive(self):',"    def verify_store(self):\n        actual=hashlib.sha256(bytes(self.s.flash[c.PREFIX:])).hexdigest()\n        x.require(actual==self.plan['store']['sha256'],'model_store_drift')\n        return dict(sha256=actual,read_only_mtd=True)\n    def verify_configuration(self):\n        return dict(source='journal',sequence=1)\n    def watchdog_inactive(self):")
 put('f361_install_test_fixture.py',fixture)
 for old,new in [('run_f358_install.py','run_f361_install.py'),('run_f358_install.ps1','run_f361_install.ps1'),('assert_f358_context.ps1','assert_f361_context.ps1')]:
  text=(ROOT/'tools'/old).read_text(encoding='utf-8').replace('F358','F361').replace('f358_hardware_context','f361_hardware_context').replace('f358_install_executor','f361_install_executor').replace('openmitrastar.f358-','openmitrastar.f361-').replace('f358-install-','f361-install-').replace('f358-evidence','f361-evidence')
  text=text.replace('.images.f358','.images.candidate361').replace('.images.f340','.images.f358').replace('.images.candidate361','.images.f361')
  text=text.replace('f358-install-conditional-f340-return','f361-install-conditional-f358-return').replace('f361-install-conditional-f340-return','f361-install-conditional-f358-return')
  text=text.replace('F361_INSTALL_F340_RETURN','F361_INSTALL_F358_PRESERVE_STORE')
  if old=='run_f358_install.ps1':text=text.replace('prefix_bytes=0x5e0000;', 'prefix_bytes=0x5e0000;store_sha256=$plan.store.sha256;')
  put(new,text)
 print('F361_STORE_PRESERVING_INSTALLER_DERIVED_NO_HARDWARE')
if __name__=='__main__':main()
