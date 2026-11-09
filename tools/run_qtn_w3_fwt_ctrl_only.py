#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];IMAGE=ROOT/"work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin";IMAGE_SHA="5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358";PRODUCT_IMAGE=ROOT/"work/tftp/omvl/linux510-product-rootfs-ram-equivalent-v1-RAM-ONLY.bin";PRODUCT_SHA="08503e290dbe84ed7d6b5d0fdbcedc4087b2fb9f26b69db418d4f2e971500255";ART=ROOT/"outputs/kernel-port/quantenna-linux510-v89-radiohw-fwt-arbtrace-20260818-0115";MANIFEST=ROOT/"work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_ARBTRACE_SIGNED_ARTIFACT.json";CLOSED_GATE=ROOT/"work/mission-state/w3-offline/W3_FWT_CTRL_ONLY_GATE.env";APPROVED_GATE=ROOT/"work/mission-state/w3-offline/W3_FWT_CTRL_ONLY_GATE.approved.env";REMOTE=ROOT/"tools/qtn_w3_fwt_ctrl_only_remote.sh";RAM=ROOT/"outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc";RAM_SHA="8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6";REL="5.10.260-openmitrastar-radiohw";ACK="OPENMITRASTAR_QTN_W3_FWT_CTRL_ONLY"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(c,t=120):subprocess.run(c,cwd=ROOT,check=True,timeout=t)
def vals(path):return dict(x.split("=",1) for x in path.read_text().splitlines() if x and not x.startswith("#"))
def restore_product(host):
 run(["pwsh.exe","-NoProfile","-File","tools/run_product_rootfs_ram_candidate.ps1","-ExecuteRam","-AckRamOnly","OPENMITRASTAR_PRODUCT_ROOTFS_RAM_ONLY"],600)
 run([sys.executable,"tools/ramssh_exec.py","uname -r; test -r /etc/openmitrastar-release; echo W3_PRODUCT_RESTORE_SSH_PASS","--host",host],60)
 print("W3_PRODUCT_RESTORE_PASS image_sha256="+PRODUCT_SHA)
def main():
 a=argparse.ArgumentParser();a.add_argument("--execute",action="store_true");a.add_argument("--ack");a.add_argument("--host",default="192.168.1.200");a.add_argument("--server-ip",default="192.168.1.43");a.add_argument("--port",default="COM3");x=a.parse_args()
 if sha(IMAGE)!=IMAGE_SHA or sha(RAM)!=RAM_SHA or sha(PRODUCT_IMAGE)!=PRODUCT_SHA:raise SystemExit("pinned input hash mismatch")
 run([sys.executable,"tools/qtn_w3_artifact_gate.py","--manifest",str(MANIFEST),"--verify"]);gate=APPROVED_GATE if x.execute else CLOSED_GATE;g=vals(gate);print({"mode":"execute" if x.execute else "dry-run","approved":g["W3_FWT_CTRL_ONLY_APPROVED"],"gate_sha256":sha(gate),"snapshot_restore":True,"added":"fwt_ctrl.ko","forbidden":["qdrv","wlan","RF","flash"]})
 if not x.execute:print("W3_FWT_CTRL_ONLY_DRY_RUN_PASS=1");return 0
 if x.ack!=ACK or g["W3_FWT_CTRL_ONLY_APPROVED"]!="1":raise SystemExit("FWT gate not approved")
 tftp=cap=None
 try:
  tftp=subprocess.Popen([sys.executable,"tools/tftp_serve_once.py","--root",str(IMAGE.parent),"--bind","0.0.0.0","--port","69","--timeout","480","--once"],cwd=ROOT);time.sleep(.6)
  run(["pwsh.exe","-NoProfile","-File","tools/reboot_boot_ramssh.ps1","-Port",x.port,"-Filename",IMAGE.name,"-ServerIp",x.server_ip,"-ClientIp",x.host,"-TimeoutSeconds","480","-EntropyPromptPattern","(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED","-EntropyOkPattern","OMPRODUCT_SERIAL_ENTROPY_OK bits=256","-ReadyPattern","OMPRODUCT_READY state=(ready|degraded)"],600)
  run([sys.executable,"tools/ramssh_exec.py","dmesg|grep -E 'OMWDT stage=(armed|pet first=1)'","--host",x.host]);cap=subprocess.Popen(["pwsh.exe","-NoProfile","-File","tools/capture_topaz_uart.ps1","-Port",x.port,"-Seconds","240","-OutputDirectory",str(ROOT/"outputs/uart-live"/("w3-fwt-"+time.strftime("%Y%m%d-%H%M%S")))],cwd=ROOT)
  run([sys.executable,"tools/ramssh_exec.py","rm -rf /tmp/w3-qtn-fwt;mkdir -p /tmp/w3-qtn-fwt","--host",x.host])
  mods=["platform/ruby/qtn_pm_qos_compat.ko","platform/ruby/board_compat.ko","platform/ruby/runtime_compat.ko","platform/ruby/qtn_platform_support.ko","platform/ruby/iputil.ko","platform/ruby/dmautil.ko","platform/topaz/switch_vlan.ko","platform/topaz/fwt_if.ko","platform/topaz/hbm.ko","platform/topaz/topaz_congest_queue.ko","platform/topaz/switch_tqe.ko","platform/fwt/fwt_ctrl.ko"]
  for rel in mods:
   s=ART/"rootfs/lib/modules"/REL/"extra/quantenna"/rel;run([sys.executable,"tools/ramssh_upload.py",str(s),"/tmp/w3-qtn-fwt/"+s.name,"--host",x.host,"--mode","0600"])
  for s,d,m in [(RAM,"/tmp/w3-qtn-fwt/ram_insmod","0700"),(gate,"/tmp/W3_FWT_CTRL_ONLY_GATE.env","0600"),(REMOTE,"/tmp/qtn_w3_fwt_ctrl_only_remote.sh","0700")]:run([sys.executable,"tools/ramssh_upload.py",str(s),d,"--host",x.host,"--mode",m])
  run([sys.executable,"tools/ramssh_exec.py","sed -i 's/\\r$//' /tmp/W3_FWT_CTRL_ONLY_GATE.env /tmp/qtn_w3_fwt_ctrl_only_remote.sh;sh /tmp/qtn_w3_fwt_ctrl_only_remote.sh /tmp/w3-qtn-fwt /tmp/W3_FWT_CTRL_ONLY_GATE.env","--host",x.host,"--timeout","180"],210)
  if cap and cap.poll() is None:cap.terminate();cap=None
  if tftp and tftp.poll() is None:tftp.terminate();tftp=None
  restore_product(x.host)
 except Exception:
  if cap and cap.poll() is None:cap.terminate();cap=None
  if tftp and tftp.poll() is None:tftp.terminate();tftp=None
  try:run(["pwsh.exe","-NoProfile","-File","tools/uart_sysrq_reboot.ps1","-Port",x.port],60)
  except Exception:pass
  restore_product(x.host)
  raise
 finally:
  if cap and cap.poll() is None:cap.terminate()
  if tftp and tftp.poll() is None:tftp.terminate()
 print("W3_FWT_CTRL_ONLY_EXPERIMENT_PASS=1 hardware_rollback=PASS product_restore=PASS");return 0
if __name__=="__main__":raise SystemExit(main())
