#!/usr/bin/env python3
from __future__ import annotations
import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];G=ROOT/"work/mission-state/w3-offline/W3_FWT_CTRL_ONLY_GATE.env";A=ROOT/"work/mission-state/w3-offline/W3_FWT_CTRL_ONLY_GATE.approved.env";FWT=ROOT/"work/linux510-radio-port/quantenna/platform/fwt/fwt.c";SW=ROOT/"work/linux510-radio-port/quantenna/platform/fwt/fwt_sw.c";REMOTE=ROOT/"tools/qtn_w3_fwt_ctrl_only_remote.sh";RUN=ROOT/"tools/run_qtn_w3_fwt_ctrl_only.py";FAILED=ROOT/"outputs/kernel-port/quantenna-linux510-v89-radiohw-fwt-reversible-20260819-0020/FAILED_SUPERSEDED.txt"
class FwtCtrlOnlyTests(unittest.TestCase):
 def test_gate_closed_and_failed_future_path_excluded(self):
  t=G.read_text();self.assertIn("W3_FWT_CTRL_ONLY_APPROVED=0",t);self.assertIn("5f3b138551352401",t);self.assertIn("03894d5d1bab4cee",t);self.assertIn("W3_FWT_CTRL_ONLY_APPROVED=1",A.read_text());self.assertTrue(FAILED.exists());self.assertIn("FAILED/SUPERSEDED",FAILED.read_text())
 def test_snapshot_precedes_first_hardware_init(self):
  t=SW.read_text();self.assertLess(t.index("topaz_fwt_snapshot_state()"),t.index("fwt_ipmac_uc_init()",t.index("static int __init fwt_sw_init")));self.assertLess(t.index("fwt_ipmac_uc_init()",t.index("static int __init fwt_sw_init")),t.index("topaz_fwt_init()",t.index("static int __init fwt_sw_init")))
 def test_snapshot_restore_controls_and_full_readback(self):
  t=FWT.read_text();self.assertIn("TOPAZ_FWT_HW_TOTAL_ENTRIES",t);self.assertIn("TOPAZ_FWT_HASH_CTRL",t);self.assertIn("TOPAZ_FWT_TIME_STAMP_CTRL",t);self.assertIn("fwt_hw_snapshot",t);self.assertIn("memcmp(&readback",t);self.assertIn("OMFWT stage=restore-readback",t)
  arb=(ROOT/"work/sources/Quantenna-GPL/include/qtn/topaz_fwt_cpuif.h").read_text();self.assertIn("OMFWTARB stage=pre",arb);self.assertIn("timeouts == 999",arb);self.assertIn("OMFWTARB stage=timeout",arb);self.assertNotIn("irq_get_default_host",arb)
 def test_exit_cleans_hooks_before_restore_and_no_live_timer(self):
  t=SW.read_text();start=t.index("static void __exit fwt_sw_exit");end=t.index("static int __init fwt_ipmac_uc_init");body=t[start:end];self.assertLess(body.index("tqe_register_fwt_cbk(NULL"),body.index("fwt_sw_reset()"));self.assertLess(body.index("fwt_sw_reset()"),body.index("topaz_fwt_restore_state()"));self.assertIn("restore_ret",t);self.assertIn("init_rc=%d restore_rc=%d",t);self.assertEqual((FWT.read_text()+t).count("topaz_fwt_maintenance_timer"),1)
 def test_remote_and_runner_are_fail_closed(self):
  t=REMOTE.read_text();active=re.findall(r"(?:^|;)load (hbm|topaz_congest_queue|switch_tqe|fwt_ctrl|qdrv|wlan)\.ko",t,re.M);self.assertEqual(active,["hbm","topaz_congest_queue","switch_tqe","fwt_ctrl"]);self.assertIn("w3_fwt_ctrl_only_enable=1",t);self.assertNotRegex(t,re.compile(r"(?:^|;)load (qdrv|wlan)\.ko",re.M));runner=RUN.read_text();self.assertIn("APPROVED_GATE if x.execute else CLOSED_GATE",runner);self.assertIn("08503e290dbe84ed",runner);self.assertIn("restore_product(x.host)",runner);self.assertIn("uart_sysrq_reboot.ps1",runner);self.assertIn("hardware_rollback=PASS product_restore=PASS",runner);r=subprocess.run(["python",str(RUN)],cwd=ROOT,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr);self.assertIn("'approved': '0'",r.stdout);self.assertIn("W3_FWT_CTRL_ONLY_DRY_RUN_PASS=1",r.stdout)
if __name__=="__main__":unittest.main(verbosity=2)
