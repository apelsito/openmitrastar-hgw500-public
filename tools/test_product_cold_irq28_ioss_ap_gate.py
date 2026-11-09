from pathlib import Path
import subprocess,sys
p=Path(__file__).with_name('run_product_cold_irq28_ioss_ap_gate.ps1')
t=p.read_text()
for x in ('logical_date = "2026-08-18"','IRQ_SYSFS=28','w3_fwt_ioss_only_probe_enable=1','post_state=3','state=ENABLED','IRQ28_AFTER','flash = $false'):
 assert x in t,x
r=subprocess.run(['pwsh.exe','-NoProfile','-File',str(p),'-PskFile','work/mission-state/.openmitrastar-lab.psk'],cwd=p.parents[1],capture_output=True,text=True,timeout=30)
assert r.returncode==0,r.stderr
assert 'OM_COLD_IRQ28_IOSS_AP_DRY_RUN_PASS=1' in r.stdout
print('OM_COLD_IRQ28_IOSS_AP_TEST_PASS=1')
