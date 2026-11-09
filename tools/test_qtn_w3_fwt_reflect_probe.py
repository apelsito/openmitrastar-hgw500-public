#!/usr/bin/env python3
from __future__ import annotations
import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SW=ROOT/"work/linux510-radio-port/quantenna/platform/fwt/fwt_sw.c";REMOTE=ROOT/"tools/qtn_w3_fwt_reflect_probe_remote.sh";RUN=ROOT/"tools/run_qtn_w3_fwt_reflect_probe.py";G=ROOT/"work/mission-state/w3-offline/W3_FWT_REFLECT_PROBE_GATE.env";A=ROOT/"work/mission-state/w3-offline/W3_FWT_REFLECT_PROBE_GATE.approved.env"
class ReflectProbeTests(unittest.TestCase):
 def test_gates_split_and_tdes_rejected(self):
  self.assertIn("W3_FWT_REFLECT_PROBE_APPROVED=0",G.read_text());self.assertIn("W3_FWT_REFLECT_PROBE_APPROVED=1",A.read_text());self.assertIn("W3_FWT_TDES_PROBE_REJECTED=1",G.read_text())
 def test_single_register_snapshot_restore(self):
  t=SW.read_text();self.assertIn("before = qtn_mproc_sync_mem_read(TOPAZ_TQE_MISC)",t);self.assertIn("TOPAZ_TQE_MISC_RFLCT_OUT_PORT_ENABLE",t);self.assertIn("TOPAZ_TQE_MISC, before",t);self.assertIn("restored == before",t);self.assertIn("bonding=0",t)
 def test_remote_forbids_full_emac_and_fwt_init(self):
  t=REMOTE.read_text();self.assertIn("w3_fwt_reflect_probe_only=1",t);self.assertIn("unexpected_fwt_write",t);self.assertNotRegex(t,re.compile(r"(?:^|;)load (switch_emac|qdrv|wlan)\.ko",re.M))
 def test_runner_dry_and_restore(self):
  t=RUN.read_text();self.assertIn("TOPAZ_TQE_MISC reflect-to-LHOST",t);r=subprocess.run(["python",str(RUN)],cwd=ROOT,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr);self.assertIn("'approved': '0'",r.stdout);self.assertIn("full_fwt_writes': False",r.stdout)
if __name__=="__main__":unittest.main(verbosity=2)
