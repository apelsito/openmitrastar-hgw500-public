#!/usr/bin/env python3
"""Resolve the six reviewed overlap regions while preserving upstream7.3 fixes.
Reads initial merge candidate and writes a new candidate. No runtime access.
"""
import argparse,hashlib,json,re,shutil
from pathlib import Path
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists();shutil.copytree(a.input,a.output)
 root=a.output/'overlay/drivers/net/wireless/realtek/rtlwifi'
 pattern=r'<<<<<<< linux7\.3\n(.*?)\|\|\|\|\|\|\| upstream5\.10\n(.*?)=======\n(.*?)>>>>>>> HGW5\.10\n'
 decisions=[]
 for name in ['pci.c','rtl8192ee/trx.c']:
  f=root/name;text=f.read_text();matches=list(re.finditer(pattern,text,re.S));assert len(matches)==(4 if name=='pci.c' else 2)
  def resolve(m):
   upstream,old,hgw=m.groups()
   if name=='pci.c':
    if 'rtl_aspm_quirks' in upstream:
     decisions.append('Preserve upstream ASPM quirks and HGW helper additions');return upstream+hgw
    if 'rtl_init_sw_leds(hw)' in upstream:
     decisions.append('Preserve new LED API and HGW stage log');return '\tpr_info("OMRTL stage=sw-vars-exit dev=%s\\n", pci_name(pdev));\n'+upstream
    if 'goto fail6' in upstream:
     decisions.append('Use upstream fail6 label, retain HGW registered-state cleanup');return upstream
    if 'fail6:' in upstream:
     decisions.append('Merge upstream IRQ unwind with HGW registration-state guard');return hgw.replace('fail_irq:','fail6:')
   else:
    if 'static unsigned int close_diag_count' in hgw:
     decisions.append('Preserve diagnostic counters, discard removed unused stop_report_cnt');return hgw.replace('\tstatic u8 stop_report_cnt;\n','')
    if 'hgw500_tx_close_diag' in hgw:
     decisions.append('Keep HGW closure diagnosis, do not reintroduce unused upstream-removed counter')
     start=hgw.index('\tif (hgw500_tx_close_diag');return hgw[start:]
   raise ValueError('Unreviewed conflict')
  f.write_text(re.sub(pattern,resolve,text,flags=re.S),newline='\n')
 for f in root.rglob('*'):
  if f.is_file():assert not re.search(rb'(?m)^(?:<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)',f.read_bytes()),f
 report={'schema':'openmitrastar.radio2g73-conflict-resolution/v1','hardware_accessed':False,'decisions':decisions,
         'files':[{'path':f.relative_to(a.output).as_posix(),'sha256':digest(f),'bytes':f.stat().st_size} for f in sorted((a.output/'overlay').rglob('*')) if f.is_file()],
         'build':'UNRUN','physical':'UNRUN'}
 (a.output/'RESOLUTION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'resolved':len(decisions),'files':len(report['files'])}))
if __name__=='__main__':main()
