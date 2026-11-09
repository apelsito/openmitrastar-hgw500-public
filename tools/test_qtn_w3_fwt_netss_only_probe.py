from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/'work/linux510-radio-port/quantenna/platform/ruby/board_compat.c').read_text()
REMOTE=(ROOT/'tools/qtn_w3_fwt_netss_only_probe_remote.sh').read_text()
RUN=(ROOT/'tools/run_qtn_w3_fwt_netss_only_probe.py').read_text()
class T(unittest.TestCase):
 def test_exact_mask_and_no_ioss_enet(self):
  self.assertIn('OMFWT_NETSS_ONLY_MASK != 0x00000080U',SRC);self.assertIn('target=%s stage=complete',SRC)
  self.assertIn('W3_IOSS_WRITE_ALLOWED=0',(ROOT/'work/mission-state/w3-offline/W3_FWT_NETSS_ONLY_PROBE_GATE.env').read_text())
 def test_remote_scope(self):
  self.assertIn('w3_fwt_netss_only_probe_enable=1',REMOTE);self.assertNotIn('w3_fwt_ioss_only_probe_enable=1',REMOTE);self.assertNotIn('fwt_ctrl.ko',REMOTE)
 def test_runner(self):
  r=subprocess.run([sys.executable,str(ROOT/'tools/run_qtn_w3_fwt_netss_only_probe.py')],cwd=ROOT,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr);self.assertIn('W3_FWT_NETSS_ONLY_PROBE_DRY_RUN_PASS=1',r.stdout);self.assertIn("'logical_date':'2026-08-18'",RUN.replace(' ',''))
if __name__=='__main__':unittest.main(verbosity=2)
