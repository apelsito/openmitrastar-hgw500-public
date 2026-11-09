"""Correct explicit CGI newline bytes and recover previous uncompleted shell."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 target=ROOT/'prepare_secure_ram_assets_generated_v31.py'
 if target.exists():raise RuntimeError('Version exists')
 code=(ROOT/'prepare_secure_ram_assets_v30.py').read_text()
 code=code.replace('linux73-https-assets-v30','linux73-https-assets-v31').replace('linux-7.3-radioeth-assets-v30','linux-7.3-radioeth-assets-v31')
 code=code.replace("script='''#!/bin/sh", "script=r'''#!/bin/sh",1)
 code=code.replace("script+='''*)", "script+=r'''*)",1)
 code=code.replace("(OUT/'upload.cgi').write_text(script)","(OUT/'upload.cgi').write_bytes(script.encode())")
 # v30 refused on exact hash before any asset execution; its shell was left.
 anchor=' (NEW/\'executor.py\').write_text(code)'
 addition='''
 start=code.index("  status=self.synchronize_nonce(m.KERNEL);")
 end=code.index("  for name in SCRIPTS:",start)
 recovery=r"""  prior=json.loads((ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-assets-stage-v30/result.json').read_text())
  m.BASE.require(prior['artifact']['sha256']==self.config['sha256'] and prior['error_reason']=='Exact asset CGI drift' and prior['flash_writes']==prior['bootenv_writes']==0,'Prior exact stopped shell absent')
  self.safe();self.fresh();self.s.write(b'\\x03\\x15\\n',timeout=3);time.sleep(.2)
  gates={}
 """
 code=code[:start]+recovery+code[end:]
'''
 assert anchor in code
 code=code.replace(anchor,addition+anchor,1)
 target.write_text(code);print(str(target))
if __name__=='__main__':main()
