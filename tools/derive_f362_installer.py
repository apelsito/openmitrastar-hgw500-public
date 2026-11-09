"""Versioned F361 installer delta: two Ethernet ports and serial-only recovery."""
from pathlib import Path
import ast,json,os,hashlib
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(name,text):
 p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.py':ast.parse(text)
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(text,encoding='utf-8',newline='\n');os.replace(tmp,p)
def shift(text):return text.replace('f361','zzcandidatezz').replace('f358','f361').replace('zzcandidatezz','f362').replace('F361','ZZCANDIDATEZZ').replace('F358','F361').replace('ZZCANDIDATEZZ','F362')
def main():
 report=PRIVATE/'analysis/f362-fullimage-20260921T200242Z/result.json';q=json.loads(report.read_text(encoding='ascii'));image=Path(q['artifact']['path'])
 previous=json.loads((ROOT/'work/kernel-port/versions/f361-installer/inputs.json').read_text(encoding='ascii'))
 item=dict(directory=str(image.parent),base=image.name.removesuffix('.webformat.bin'),bytes=q['artifact']['bytes'],sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f362',kernel_build='#358',marker='F340_WATCHDOG_BASELINE')
 uart=Path('/workspace/OpenMitraStar/f362-uart-evidence/f362-uart-20260921T200416Z-9cbb58e8/result.json')
 storeproof=PRIVATE/'analysis/f361-store-seq2-20260921T193734Z/result.json';s=json.loads(storeproof.read_text(encoding='ascii'))
 oldstore=json.loads((ROOT/'work/kernel-port/versions/f361-installer/store-binding.json').read_text(encoding='ascii'))
 binding=dict(schema='openmitrastar.f362-installer-inputs/v1',candidate=item,fallback=previous['candidate'],qualification=dict(path=str(report),sha256=sha(report),status=q['status']),serial_recovery=dict(path=str(uart),sha256=sha(uart)),boot_acceptance={**previous['boot_acceptance'],'sequence':2,'slot':'B'},additional_pins=[])
 store=dict(path=s['store'],bytes=s['bytes'],sha256=s['store_sha256'],crc32=s['store_crc32'],physical_result=dict(path=str(storeproof),sha256=sha(storeproof)),erase_audit=oldstore['erase_audit'],captured_parts=[],sequence=2,slot=1)
 put('work/kernel-port/versions/f362-installer/inputs.json',json.dumps(binding,indent=2)+'\n');put('work/kernel-port/versions/f362-installer/store-binding.json',json.dumps(store,indent=2)+'\n')
 text=shift((ROOT/'tools/f361_install_executor.py').read_text(encoding='utf-8'))
 text=text.replace("import f336_wdt_ram_executor as base","import f336_wdt_ram_executor as base\nfrom f362_recovery_delta import serial_reboot_to_prompt, verify_ethernet_response, ethernet_command, clear_pending_break")
 text=text.replace("ready='F362_READY',slot='A',sequence='1'","ready='F361_READY',slot='B',sequence='2'").replace("sequence=1,slot='A'","sequence=2,slot='B'")
 text=text.replace("        self.allowed=vocabulary(plan);", "        self.kernel_handoff_start=None;self.serial_recovery_record={};self.allowed=vocabulary(plan);")
 text=text.replace("    def verify_store(self):", "    def reboot_to_prompt(self,uart,software_recovery=False):\n        if software_recovery:return serial_reboot_to_prompt(self,uart)\n        mask=int(self.ssh('cat /proc/sys/kernel/sysrq').strip());require(mask==1 or bool(mask&128),'sysrq_reboot_disabled')\n        return super().reboot_to_prompt(uart,software_recovery=False)\n    def verify_ethernet(self):\n        return verify_ethernet_response(self.ssh(ethernet_command()))\n    def verify_store(self):")
 text=text.replace("    identity=host.wait_identity(name,uart,start);", "    uart.kernel_handoff_start=start\n    identity=host.wait_identity(name,uart,start);")
 text=text.replace("result['configuration_boot']=host.verify_configuration()", "result['configuration_boot']=host.verify_configuration();result['ethernet']=host.verify_ethernet()")
 text=text.replace("result['transport_events']=getattr(host,'transport_events',[])", "result['serial_recovery']=getattr(uart,'serial_recovery_record',{});result['transport_events']=getattr(host,'transport_events',[])")
 text=text.replace("        try:result['uart']=uart.close()", "        result['break_cleanup_verified']=clear_pending_break(uart)\n        try:result['uart']=uart.close()")
 # A cleared native BREAK is required even when the serial recovery helper fails.
 text=text.replace("or not result['final_domain_guard']\n        result['flash_command", "or not result['final_domain_guard'] or bool(getattr(uart,'serial_recovery_record',{}).get('break_attempted') and not getattr(uart,'serial_recovery_record',{}).get('break_cleared'))\n        result['flash_command")
 put('tools/f362_install_executor.py',text)
 for name in ['run_f361_install.py','run_f361_install.ps1','assert_f361_context.ps1','f361_hardware_context.ps1','test_f361_context.ps1']:
  text=shift((ROOT/'tools'/name).read_text(encoding='utf-8'))
  text=text.replace('#361','#358').replace('lyoko-foundation-6.9.8-f361-config-backend-device',previous['candidate']['version']).replace('fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f',previous['candidate']['sha256'])
  put('tools/'+name.replace('f361','f362'),text)
 print('F362_INSTALLER_DERIVED_OFFLINE')
if __name__=='__main__':main()
