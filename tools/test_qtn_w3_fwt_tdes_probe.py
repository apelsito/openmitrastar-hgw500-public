#!/usr/bin/env python3
from __future__ import annotations
import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SW=ROOT/"work/linux510-radio-port/quantenna/platform/fwt/fwt_sw.c";REMOTE=ROOT/"tools/qtn_w3_fwt_tdes_probe_remote.sh";RUN=ROOT/"tools/run_qtn_w3_fwt_tdes_probe.py";G=ROOT/"work/mission-state/w3-offline/W3_FWT_TDES_PROBE_GATE.env";A=ROOT/"work/mission-state/w3-offline/W3_FWT_TDES_PROBE_GATE.approved.env"
class TdesProbeTests(unittest.TestCase):
 def test_gates_split(self):
  self.assertIn("W3_FWT_TDES_PROBE_APPROVED=0",G.read_text());self.assertIn("W3_FWT_TDES_PROBE_APPROVED=1",A.read_text())
 def test_single_reversible_register_write(self):
  t=SW.read_text();self.assertIn("const u32 expected = 0x000100e2",t);self.assertIn("TOPAZ_TQE_EMAC_TDES_1_CNTL, expected",t);self.assertIn("TOPAZ_TQE_EMAC_TDES_1_CNTL, before",t);self.assertIn("restored == before",t);self.assertIn("topaz_fwt_discard_snapshot",t)
 def test_remote_probe_forbids_full_init(self):
  t=REMOTE.read_text();self.assertIn("w3_fwt_tdes_probe_only=1",t);self.assertIn("unexpected_fwt_write",t);self.assertIn("unexpected_hooks",t);self.assertNotRegex(t,re.compile(r"(?:^|;)load (qdrv|wlan)\.ko",re.M))
 def test_runner_dry_and_product_restore(self):
  t=RUN.read_text();self.assertIn("APPROVED if x.execute else CLOSED",t);self.assertIn("08503e290dbe84ed",t);self.assertIn("restore(x.host)",t);r=subprocess.run(["python",str(RUN)],cwd=ROOT,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr);self.assertIn("'approved': '0'",r.stdout);self.assertIn("W3_FWT_TDES_PROBE_DRY_RUN_PASS=1",r.stdout)
if __name__=="__main__":unittest.main(verbosity=2)
