#!/usr/bin/env python3
from __future__ import annotations
import re, subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REMOTE=ROOT/"tools/qtn_w3_congest_only_remote.sh"
RUNNER=ROOT/"tools/run_qtn_w3_congest_only.ps1"
GATE=ROOT/"work/mission-state/w3-offline/W3_CONGEST_ONLY_GATE.env"
APPROVED=ROOT/"work/mission-state/w3-offline/W3_CONGEST_ONLY_GATE.approved.env"
SRC=ROOT/"work/linux510-radio-port/quantenna/platform/topaz/topaz_congest_queue.c"

class CongestOnlyTests(unittest.TestCase):
    def test_gate_closed_and_hbm_proven(self):
        t=GATE.read_text(); self.assertIn("W3_CONGEST_ONLY_APPROVED=0",t); self.assertIn("W3_HBM_ONLY_PROVEN=1",t); self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0",t)
        a=APPROVED.read_text(); self.assertIn("W3_CONGEST_ONLY_APPROVED=0",a); self.assertIn("W3_HBM_ONLY_PROVEN=1",a); self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0",a)
    def test_module_lifecycle_is_reversible_and_mmio_free(self):
        t=SRC.read_text(); self.assertIn("OMCGQ stage=module-ready allocation=deferred mmio=none",t); self.assertIn("module_exit(topaz_congest_queue_module_exit)",t); self.assertIn("tasklet_kill",t)
    def test_remote_adds_only_congest_after_hbm(self):
        t=REMOTE.read_text(); active=re.findall(r"^insmod .*?(hbm|topaz_congest_queue|switch_tqe|qdrv|wlan|gpio|temp_sens|temp_sensor|fwt_ctrl)\.ko",t,re.M); self.assertEqual(active,["hbm","topaz_congest_queue"]); self.assertLess(t.index('insmod "$root/hbm.ko"'),t.index('insmod "$root/topaz_congest_queue.ko"')); self.assertIn("rmmod topaz_congest_queue",t); self.assertNotRegex(t,re.compile(r"^insmod .*?(switch_tqe|qdrv|wlan)\.ko",re.M))
    def test_runner_watchdog_uart_and_dry_run(self):
        t=RUNNER.read_text(); self.assertIn("OMWDT stage=(armed|pet first=1)",t); self.assertIn("capture_topaz_uart.ps1",t); self.assertIn("uart_sysrq_reboot.ps1",t); self.assertNotRegex(t,re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"));
        p=subprocess.run(["pwsh.exe","-NoProfile","-Command",f"[void][scriptblock]::Create((Get-Content -Raw '{RUNNER}'))"],cwd=ROOT,capture_output=True,text=True,timeout=30); self.assertEqual(p.returncode,0,p.stderr)
        d=subprocess.run(["pwsh.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(RUNNER)],cwd=ROOT,capture_output=True,text=True,timeout=60); self.assertEqual(d.returncode,0,d.stderr); self.assertIn("W3_CONGEST_ONLY_DRY_RUN_PASS=1",d.stdout)

if __name__=="__main__": unittest.main(verbosity=2)
