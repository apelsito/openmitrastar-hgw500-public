"""Create versioned actual-image RAM loader from the qualified receiver flow.

Only prepares files. Run.ps1 defaults to file-only. No generic flash vocabulary
is admitted by this RAM gate. Exact candidate, source pins and local UART lease.
"""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-events-powercycle-v15'
NEW=ROOT/'work/kernel-port/linux-7.3-2g-autostart-ram-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Immutable gate exists')
 NEW.mkdir()
 code=(OLD/'executor.py').read_text(encoding='utf8')
 start=code.index("  previous=ROOT/");end=code.index("  print('RADIOETH73_V15",start)
 code=code[:start]+r'''  self.synchronize_nonce(m.KERNEL)
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','artifact_sha256':self.config['sha256'],'flash_writes':0,'bootenv_writes':0,'fresh_current_kernel_nonce':True})+'\\n')
'''+code[end:]
 code=code.replace('RADIOETH73_V15_CAPTURE_READY_POWER_CYCLE_NOW','RADIO73_AUTOSTART_CAPTURE_READY_POWER_CYCLE_NOW')
 start=code.index("  m.BASE.require(b'ETHLOAD=0'");end=code.index("\n\ndef main():",start)
 code=code[:start]+r'''  m.BASE.require(b'OPENMITRASTAR_RADIOETH73_FLASH2G_R1' in boot and b'AUTOSTART_END' in boot,'new autostart image marker absent')
  m.BASE.require(b'AUTOSTART_ETH_FAILURE' not in boot and b'RADIOLOAD_STOP' not in boot,'automatic device startup failed')
  count=len(re.findall(rb'RADIO_MODULE_RESULT=0\\r?\\n',boot))
  m.BASE.require(count==19,'automatic radio module count incomplete')
  results={'kernel_status':status.decode(errors='replace'),'userland':userland.decode(errors='replace'),'radio_module_successes':count,'autostart_end':True}
  for name in ['modules','eth0state','eth1state','pcistatus']:
   results[name]=self.command(name,seconds=45).decode(errors='replace')
  (self.output/'gates.json').write_text(json.dumps(results,indent=2)+'\\n')
  return {'status':'PASS_EXACT_2G_AUTOSTART_RAM_BOOT_19MODULES','bootm':self.boots,'reboots':0,'flash_writes':0,'bootenv_writes':0,'steps':self.steps,'gates':results,'ethernet_https_traffic':'UNRUN','wifi_client':'UNRUN','persistent':'UNRUN'}
'''+code[end:]
 code=code.replace('artifact=m.preflight(config)','artifact=preflight(config)')
 # Local preflight does not modify the historical parent's pinned function.
 at=code.index('class Flow(')
 functions=r'''
def preflight(config):
 image=Path(config['image']).read_bytes()
 m.BASE.require(len(image)==config['bytes'] and m.sha(config['image'])==config['sha256'],'exact image changed')
 import zlib,lzma
 m.BASE.require(f'{zlib.crc32(image)&0xffffffff:08x}'==config['crc32'],'image CRC changed')
 sys.path.insert(0,str(ROOT/'tools'))
 from bootbase_contract_emulator import validate_bootbase_slot
 contract=validate_bootbase_slot('AUTOSTART2G-RAM-test',image,0x5e0000)
 m.BASE.require(contract.accepted_by_contract and contract.header['entry']==config['entry'] and contract.header['load']=='0x8493a000' and contract.header['compression']==3,'Bootbase contract changed')
 decoded=lzma.decompress(image[8192:],format=lzma.FORMAT_ALONE)
 m.BASE.require(len(decoded)==config['raw_bytes'] and hashlib.sha256(decoded).hexdigest()==config['raw_sha256'],'decoded kernel drift')
 m.BASE.require(0x83000000+len(image)<0x84000000 and 0x8493a000+len(decoded)<0x88000000,'RAM interval contract')
 m.BASE.require(config['classification']=='FLASH_CANDIDATE_NEEDS_RAM_BOOT_READBACK_ROLLBACK','wrong scope')
 m.BASE.require(config['kernel_release']==m.KERNEL.decode(),'kernel release changed')
 for key in ['receipt','qualification','tls_cert']:
  m.BASE.require(m.sha(config[key])==config[key+'_sha256'],'proof/trust input changed')
 build=json.loads(Path(config['receipt']).read_text())
 qualification=json.loads(Path(config['qualification']).read_text())
 m.BASE.require(build['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN' and build['lanes'][0]['image_sha256']==config['sha256'],'paired build does not bind image')
 m.BASE.require(qualification['status']=='PASS_INDEPENDENT_2G_FLATCPIO_LZMA_ENTRY_PREFIX_ROOT_CONTRACTS' and qualification['build_result_sha256']==config['receipt_sha256'],'qualification mismatch')
 return {'path':config['image'],'bytes':config['bytes'],'sha256':config['sha256'],'crc32':config['crc32']}

'''
 code=code[:at]+functions+code[at:]
 code=code.replace('m.preflight(self.config)','preflight(self.config)')
 at=code.index(' def run(self):')
 verify=r'''
 def verify_ram(self):
  size=self.command('printenv filesize',m.BASE.PROMPT)
  rows=re.findall(rb'(?mi)^filesize=([0-9a-f]+)\r?$',size)
  m.BASE.require(len(rows)==1 and int(rows[0],16)==self.config['bytes'],'physical filesize differs')
  info=self.command('iminfo 83000000',m.BASE.PROMPT,60)
  m.BASE.require(b'Verifying Checksum ... OK' in info and not re.search(rb'(?i)bad.*crc|bad.*checksum',info),'iminfo checksum refused')
  for label,value in [('Load Address','8493a000'),('Entry Point',self.config['entry'][2:])]:
   m.BASE.require(re.search(label.encode()+rb':\s*(?:0x)?'+value.encode()+rb'(?:\s|$)',info,re.I),'physical load/entry differs')
  m.BASE.require(re.search(rb'Data Size:\s*'+str(self.config['payload_bytes']).encode()+rb'(?:\s|$)',info),'payload size differs')
  m.BASE.require(re.search(rb'Image Type:[^\r\n]*lzma',info,re.I),'physical compression differs')
  self.command(f"crc32 83000000 {self.config['bytes']:08x} 84000000",m.BASE.PROMPT,90)
  m.BASE.require(m.BASE.parse_word(self.command('md.l 84000000 1',m.BASE.PROMPT),'84000000')==self.config['crc32'],'physical RAM CRC mismatch')
'''
 code=code[:at]+verify+code[at:]
 (NEW/'executor.py').write_text(code,encoding='utf8')
 run=(OLD/'run.ps1').read_text(encoding='utf8').replace(".AddMinutes(28)",".AddMinutes(35)")
 # Validate finite actual-new-flow fake fixture as well as retained parser/writer.
 run=run.replace("'test_executor.py'","'test_executor.py'")
 (NEW/'run.ps1').write_text(run,encoding='utf8')
 (NEW/'test_executor.py').write_text('from pathlib import Path\nimport subprocess,sys\np=Path(__file__).resolve().parent.parent/"linux-7.3-radioeth-ram-v1"\nfor name in ["test_executor.py","test_bounded_serial.py"]:\n subprocess.run([sys.executable,str(p/name)],check=True)\nsubprocess.run([sys.executable,str(Path(__file__).resolve().parent/"test_new_flow.py")],check=True)\n',encoding='utf8')
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:
  pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('PREPARED_EXACT_AUTOSTART_RAM_GATE_NO_HARDWARE')
if __name__=='__main__':main()
