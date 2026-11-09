#!/usr/bin/env python3
"""Lab-only switch-TQE probe using DRAM in place of missing Topaz SRAM."""
from __future__ import annotations
import argparse, hashlib, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IMAGE=ROOT/"work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
IMAGE_SHA="5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358"
ART=ROOT/"outputs/kernel-port/quantenna-linux510-v89-radiohw-switch-irqmap-20260818-2355"
MANIFEST=ROOT/"work/mission-state/w3-offline/W3_V89_RADIOHW_SWITCH_IRQMAP_SIGNED_ARTIFACT.json"
CLOSED_GATE=ROOT/"work/mission-state/w3-offline/W3_SWITCH_TQE_DRAMLAB_GATE.env"
APPROVED_GATE=ROOT/"work/mission-state/w3-offline/W3_SWITCH_TQE_DRAMLAB_GATE.approved.env"
REMOTE=ROOT/"tools/qtn_w3_switch_tqe_dramlab_remote.sh"
RAM_INSMOD=ROOT/"outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
RAM_INSMOD_SHA="8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6"
RELEASE="5.10.260-openmitrastar-radiohw"
ACK="OPENMITRASTAR_QTN_W3_SWITCH_TQE_DRAMLAB"

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd:list[str],timeout:int=120)->None:subprocess.run(cmd,cwd=ROOT,check=True,timeout=timeout)
def gate_values(path:Path)->dict[str,str]:
 return dict(line.split("=",1) for line in path.read_text().splitlines() if line and not line.startswith("#"))

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--execute",action="store_true");ap.add_argument("--ack");ap.add_argument("--host",default="192.168.1.200");ap.add_argument("--server-ip",default="192.168.1.43");ap.add_argument("--port",default="COM3");args=ap.parse_args()
 if sha(IMAGE)!=IMAGE_SHA:raise SystemExit("watchdog image hash mismatch")
 if sha(RAM_INSMOD)!=RAM_INSMOD_SHA:raise SystemExit("ram_insmod hash mismatch")
 run([sys.executable,"tools/qtn_w3_artifact_gate.py","--manifest",str(MANIFEST),"--verify"])
 gate=APPROVED_GATE if args.execute else CLOSED_GATE
 g=gate_values(gate);print({"mode":"execute" if args.execute else "dry-run","lab_only":True,"production_sram_ready":g["W3_PRODUCTION_SRAM_READY"],"approved":g["W3_SWITCH_TQE_DRAMLAB_APPROVED"],"gate_sha256":sha(gate),"fallback":"DRAM laboratory probe only","forbidden":["fwt_ctrl","qdrv","wlan","GPIO","sensors","RF","flash"]})
 if not args.execute:print("W3_SWITCH_TQE_DRAMLAB_DRY_RUN_PASS=1");return 0
 if args.ack!=ACK:raise SystemExit(f"require --ack {ACK}")
 if g["W3_SWITCH_TQE_DRAMLAB_APPROVED"]!="1" or g["W3_PRODUCTION_SRAM_READY"]!="0" or g["W3_HARDWARE_ACTIVE_APPROVED"]!="0":raise SystemExit("lab gate conditions not met")
 tftp=capture=None
 try:
  tftp=subprocess.Popen([sys.executable,"tools/tftp_serve_once.py","--root",str(IMAGE.parent),"--bind","0.0.0.0","--port","69","--timeout","480","--once"],cwd=ROOT)
  time.sleep(.6)
  run(["pwsh.exe","-NoProfile","-File","tools/reboot_boot_ramssh.ps1","-Port",args.port,"-Filename",IMAGE.name,"-ServerIp",args.server_ip,"-ClientIp",args.host,"-TimeoutSeconds","480","-EntropyPromptPattern","(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED","-EntropyOkPattern","OMPRODUCT_SERIAL_ENTROPY_OK bits=256","-ReadyPattern","OMPRODUCT_READY state=(ready|degraded)"],600)
  run([sys.executable,"tools/ramssh_exec.py","dmesg | grep -E 'OMWDT stage=(armed|pet first=1)'","--host",args.host])
  out=ROOT/"outputs/uart-live"/("w3-switch-dramlab-"+time.strftime("%Y%m%d-%H%M%S"));capture=subprocess.Popen(["pwsh.exe","-NoProfile","-File","tools/capture_topaz_uart.ps1","-Port",args.port,"-Seconds","180","-OutputDirectory",str(out)],cwd=ROOT)
  run([sys.executable,"tools/ramssh_exec.py","rm -rf /tmp/w3-qtn-dramlab; mkdir -p /tmp/w3-qtn-dramlab","--host",args.host])
  mods=["platform/ruby/qtn_pm_qos_compat.ko","platform/ruby/board_compat.ko","platform/ruby/runtime_compat.ko","platform/ruby/qtn_platform_support.ko","platform/ruby/iputil.ko","platform/ruby/dmautil.ko","platform/topaz/switch_vlan.ko","platform/topaz/fwt_if.ko","platform/topaz/hbm.ko","platform/topaz/topaz_congest_queue.ko","platform/topaz/switch_tqe.ko"]
  for rel in mods:
   src=ART/"rootfs/lib/modules"/RELEASE/"extra/quantenna"/rel;run([sys.executable,"tools/ramssh_upload.py",str(src),"/tmp/w3-qtn-dramlab/"+src.name,"--host",args.host,"--mode","0600"])
  for src,dst,mode in [(RAM_INSMOD,"/tmp/w3-qtn-dramlab/ram_insmod","0700"),(gate,"/tmp/W3_SWITCH_TQE_DRAMLAB_GATE.env","0600"),(REMOTE,"/tmp/qtn_w3_switch_tqe_dramlab_remote.sh","0700")]:run([sys.executable,"tools/ramssh_upload.py",str(src),dst,"--host",args.host,"--mode",mode])
  cmd="sed -i 's/\\r$//' /tmp/W3_SWITCH_TQE_DRAMLAB_GATE.env /tmp/qtn_w3_switch_tqe_dramlab_remote.sh; sh /tmp/qtn_w3_switch_tqe_dramlab_remote.sh /tmp/w3-qtn-dramlab /tmp/W3_SWITCH_TQE_DRAMLAB_GATE.env"
  run([sys.executable,"tools/ramssh_exec.py",cmd,"--host",args.host,"--timeout","150"],180)
 except Exception:
  if capture and capture.poll() is None:capture.terminate()
  try: run(["pwsh.exe","-NoProfile","-File","tools/uart_sysrq_reboot.ps1","-Port",args.port],60)
  except Exception: pass
  try: run(["pwsh.exe","-NoProfile","-File","tools/run_product_rootfs_ram_candidate.ps1","-ExecuteRam","-AckRamOnly","OPENMITRASTAR_PRODUCT_ROOTFS_RAM_ONLY"],600)
  except Exception: pass
  raise
 finally:
  if capture and capture.poll() is None:capture.terminate()
  if tftp and tftp.poll() is None:tftp.terminate()
 print("W3_SWITCH_TQE_DRAMLAB_EXPERIMENT_PASS=1");return 0
if __name__=="__main__":raise SystemExit(main())
