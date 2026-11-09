#!/usr/bin/env python3
from __future__ import annotations
import re,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];G=ROOT/"work/mission-state/w3-offline/W3_SWITCH_TQE_DRAMLAB_GATE.env";A=ROOT/"work/mission-state/w3-offline/W3_SWITCH_TQE_DRAMLAB_GATE.approved.env";R=ROOT/"tools/qtn_w3_switch_tqe_dramlab_remote.sh";RUN=ROOT/"tools/run_qtn_w3_switch_tqe_dramlab.py";DMA=ROOT/"work/linux510-radio-port/quantenna/platform/ruby/dmautil.c";BOARD=ROOT/"work/linux510-radio-port/quantenna/platform/ruby/board_compat.c";TQE=ROOT/"work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
class DramLabTests(unittest.TestCase):
 def test_gate_closed_and_lab_only(self):
  t=G.read_text();self.assertIn("W3_SWITCH_TQE_DRAMLAB_APPROVED=0",t);self.assertIn("W3_PRODUCTION_SRAM_READY=0",t);self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0",t);self.assertIn("8eb902dcc5e1bdab",t);a=A.read_text();self.assertIn("W3_SWITCH_TQE_DRAMLAB_APPROVED=1",a);self.assertIn("W3_PRODUCTION_SRAM_READY=0",a)
 def test_instrumentation_covers_allocation_mapping_cleanup(self):
  text=BOARD.read_text()+DMA.read_text()+TQE.read_text()
  for marker in ("OMSRAM stage=request","backend=dram-lab","OMDMA stage=request","OMDMA stage=aligned","OMDMA stage=ioremap-ok","OMDMA stage=iounmap","OMDMA stage=free","OMTQE stage=desc-allocated","OMTQE stage=desc-cleanup-complete"):self.assertIn(marker,text)
  self.assertIn('of_find_compatible_node(NULL, NULL, "snps,arc700-intc")',text);self.assertIn("irq_find_host(node)",text);self.assertIn("irq_create_mapping(domain, TOPAZ_IRQ_TQE)",text);self.assertIn("request_irq(dev->irq",text);self.assertIn("irq_dispose_mapping",text);self.assertNotIn("irq_get_default_host",text)
 def test_remote_uses_verified_loader_and_fallback_one(self):
  t=R.read_text();self.assertIn('"$root/ram_insmod"',t);self.assertIn("allow_dram_sram_fallback=1",t);self.assertNotIn("allow_dram_sram_fallback=0",t);self.assertIn("'backend=dram'",t);self.assertNotIn("OMSRAM stage=free backend=dram-lab",t);active=re.findall(r"^load_module (hbm|topaz_congest_queue|switch_tqe|fwt_ctrl|qdrv|wlan)\.ko",t,re.M);self.assertEqual(active,["hbm","topaz_congest_queue","switch_tqe"])
 def test_runner_dry_run(self):
  t=RUN.read_text();self.assertIn("DRAM laboratory probe only",t);self.assertIn("RAM_INSMOD_SHA",t);self.assertIn("uart_sysrq_reboot.ps1",t);self.assertIn("run_product_rootfs_ram_candidate.ps1",t);self.assertNotRegex(t,re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"));r=subprocess.run(["python",str(RUN)],cwd=ROOT,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr);self.assertIn("W3_SWITCH_TQE_DRAMLAB_DRY_RUN_PASS=1",r.stdout)
if __name__=="__main__":unittest.main(verbosity=2)
