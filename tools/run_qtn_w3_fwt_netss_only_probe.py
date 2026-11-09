#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IMAGE=ROOT/'work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin'
IMAGE_SHA='5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358'
PRODUCT=ROOT/'work/tftp/omvl/linux510-product-rootfs-ram-equivalent-v1-RAM-ONLY.bin'
PRODUCT_SHA='08503e290dbe84ed7d6b5d0fdbcedc4087b2fb9f26b69db418d4f2e971500255'
ART=ROOT/'outputs/kernel-port/quantenna-linux510-v89-radiohw-fwt-netss-only-20260818-0515'
MANIFEST=ROOT/'work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_NETSS_ONLY_SIGNED_ARTIFACT.json'
CLOSED=ROOT/'work/mission-state/w3-offline/W3_FWT_NETSS_ONLY_PROBE_GATE.env'
APPROVED=ROOT/'work/mission-state/w3-offline/W3_FWT_NETSS_ONLY_PROBE_GATE.approved.env'
REMOTE=ROOT/'tools/qtn_w3_fwt_netss_only_probe_remote.sh'
UART_WAITER=ROOT/'tools/wait_topaz_uart_marker.ps1'
RAM=ROOT/'outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc'
RAM_SHA='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
REL='5.10.260-openmitrastar-radiohw'
ACK='OPENMITRASTAR_QTN_W3_FWT_NETSS_ONLY_PROBE'
PATTERN=r'OMFWT1B target=netss stage=complete rc=-?[0-9]+'

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def run(c:list[str],t:int=120)->None:subprocess.run(c,cwd=ROOT,check=True,timeout=t)
def vals(p:Path)->dict[str,str]:return dict(x.split('=',1) for x in p.read_text().splitlines() if x and not x.startswith('#'))
def restore(host:str)->None:
 run(['pwsh.exe','-NoProfile','-File','tools/run_product_rootfs_ram_candidate.ps1','-ExecuteRam','-AckRamOnly','OPENMITRASTAR_PRODUCT_ROOTFS_RAM_ONLY'],600)
 run([sys.executable,'tools/ramssh_exec.py','uname -r;echo W3_PRODUCT_RESTORE_SSH_PASS','--host',host],60)

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--ack');p.add_argument('--host',default='192.168.1.200');p.add_argument('--server-ip',default='192.168.1.43');p.add_argument('--port',default='COM3');a=p.parse_args()
 if sha(IMAGE)!=IMAGE_SHA or sha(PRODUCT)!=PRODUCT_SHA or sha(RAM)!=RAM_SHA:raise SystemExit('pinned input mismatch')
 run([sys.executable,'tools/qtn_w3_artifact_gate.py','--manifest',str(MANIFEST),'--verify'])
 gate=APPROVED if a.execute else CLOSED; approved=vals(gate)['W3_FWT_NETSS_ONLY_PROBE_APPROVED']
 print({'mode':'execute' if a.execute else 'dry-run','approved':approved,'logical_date':'2026-08-18','pulse_mask':'0x00000080','ioss_write':False,'enet0_reset':False,'fwt_table_access':False,'flash':False})
 if not a.execute:print('W3_FWT_NETSS_ONLY_PROBE_DRY_RUN_PASS=1');return 0
 if a.ack!=ACK or approved!='1':raise SystemExit('probe gate not approved')
 tftp=waiter=None; sysrq=False
 try:
  tftp=subprocess.Popen([sys.executable,'tools/tftp_serve_once.py','--root',str(IMAGE.parent),'--bind','0.0.0.0','--port','69','--timeout','480','--once'],cwd=ROOT);time.sleep(.6)
  run(['pwsh.exe','-NoProfile','-File','tools/reboot_boot_ramssh.ps1','-Port',a.port,'-Filename',IMAGE.name,'-ServerIp',a.server_ip,'-ClientIp',a.host,'-TimeoutSeconds','480','-EntropyPromptPattern','(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED','-EntropyOkPattern','OMPRODUCT_SERIAL_ENTROPY_OK bits=256','-ReadyPattern','OMPRODUCT_READY state=(ready|degraded)'],600)
  rr='/tmp/w3-qtn-fwt-n80'; run([sys.executable,'tools/ramssh_exec.py',f'rm -rf {rr};mkdir -p {rr}','--host',a.host])
  mr=ART/'rootfs/lib/modules'/REL/'extra/quantenna/platform/ruby'
  for s,d,m in ((mr/'qtn_platform_support.ko',f'{rr}/qtn_platform_support.ko','0600'),(mr/'board_compat.ko',f'{rr}/board_compat.ko','0600'),(RAM,f'{rr}/ram_insmod','0700'),(gate,'/tmp/W3_FWT_NETSS_ONLY_PROBE_GATE.env','0600'),(REMOTE,'/tmp/qtn_w3_fwt_netss_only_probe_remote.sh','0700')):
   run([sys.executable,'tools/ramssh_upload.py',str(s),d,'--host',a.host,'--mode',m])
  out=ROOT/'outputs/uart-live'/'w3-fwt-netss-only-20260818';waiter=subprocess.Popen(['pwsh.exe','-NoProfile','-File',str(UART_WAITER),'-Port',a.port,'-Pattern',PATTERN,'-TimeoutSeconds','120','-OutputDirectory',str(out)],cwd=ROOT);time.sleep(.5)
  subprocess.run([sys.executable,'tools/ramssh_exec.py',"sed -i 's/\\r$//' /tmp/W3_FWT_NETSS_ONLY_PROBE_GATE.env /tmp/qtn_w3_fwt_netss_only_probe_remote.sh; sh /tmp/qtn_w3_fwt_netss_only_probe_remote.sh /tmp/w3-qtn-fwt-n80 /tmp/W3_FWT_NETSS_ONLY_PROBE_GATE.env",'--host',a.host,'--timeout','20'],cwd=ROOT,timeout=30)
  if waiter.wait(timeout=135)!=0:raise RuntimeError('UART completion marker absent')
  waiter=None;run(['pwsh.exe','-NoProfile','-File','tools/uart_sysrq_reboot.ps1','-Port',a.port,'-WaitSeconds','45'],60);sysrq=True
  if tftp.poll() is None:tftp.terminate();tftp=None
  restore(a.host)
 except Exception:
  if waiter is not None and waiter.poll() is None:waiter.terminate()
  if tftp is not None and tftp.poll() is None:tftp.terminate()
  if not sysrq:
   try:run(['pwsh.exe','-NoProfile','-File','tools/uart_sysrq_reboot.ps1','-Port',a.port,'-WaitSeconds','45'],60)
   except Exception:pass
  restore(a.host);raise
 finally:
  if waiter is not None and waiter.poll() is None:waiter.terminate()
  if tftp is not None and tftp.poll() is None:tftp.terminate()
 print('W3_FWT_NETSS_ONLY_PROBE_PASS=1 uart=PASS product_restore=PASS');return 0

if __name__=='__main__':raise SystemExit(main())
