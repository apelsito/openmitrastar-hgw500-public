"""Package the exact F350 kernel for RAM-only F356 OBSERVE. No kernel rebuild or hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,lzma,shlex,shutil,struct,subprocess,zlib
from elftools.elf.elffile import ELFFile
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict
from build_f340_watchdog_kernel import extract_embedded
import f336_wdt_ram_contract as base
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
KERNEL=DEVICE/'analysis/f350-flash-arbitration-20260921T155949Z'
F340=DEVICE/'firmware/f340-f321-watchdog-baseline-device-bound'
F340_BASE='openmitrastar-linux510-f340-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
CLI=ROOT/'outputs/userspace/f351-journal-cli-20260921T162420Z'
LOADER=ROOT/'outputs/preflight/f354-loader-20260921T164208Z/ram-insmod-qtn'
BOOTARGS='earlycon=uart8250,mmio32,0xf0000000 console=ttyS0,115200n8 root=31:3 rootfstype=squashfs ro rootwait init=/sbin/init panic=10'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--provider',type=Path,required=True);ap.add_argument('--supervisor',type=Path,required=True);ap.add_argument('--provider-tests',type=Path,required=True);args=ap.parse_args()
 assert shutil.disk_usage('C:/').free>500*1024*1024
 kernel=json.loads((KERNEL/'result.json').read_text());provider=json.loads((args.provider/'result.json').read_text());supervisor=json.loads((args.supervisor/'result.json').read_text());tests=json.loads((args.provider_tests/'result.json').read_text())
 assert sha(KERNEL/'result.json')=='7f74022f4085bfa53acbbaf5e64a5b238d586410a095504d8cf73dbb75eded07'
 assert kernel['kernel_build_identity']==350 and kernel['reproducible']
 for value in kernel['artifacts'].values():assert sha(value['path'])==value['sha256']
 assert provider['status']=='PASS_OFFLINE_KERNEL_MODULE' and provider['reproducible'] and provider['id_checked_before_vendor_writes']
 assert supervisor['status']=='PASS_OFFLINE_SUPERVISOR' and supervisor['reproducible']
 assert tests['status']=='PASS' and provider['sources']==tests['sources']
 assert 'F356_ID_GATE_PASS initial_ids=5 changed_during_cleanup=1 unknown_id_writes=0' in tests['logs']['model.log']
 assert 'F356_KERNEL_ADAPTER_PASS cases=11 id_before_write=1' in tests['logs']['adapter.log']
 assert tests['logs']['analyzer.log']==''
 for r in (provider,supervisor):
  assert sha(r['artifact']['path'])==r['artifact']['sha256']
  for p,h in r['sources'].items():assert sha(ROOT/p)==h
 assert sha(LOADER)=='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
 cli=json.loads((CLI/'result.json').read_text());assert sha(cli['artifact']['path'])=='dee84fd30d41734e52d4627418028a1d15cd64db87cca1bc3eef261aacb0edef'
 assert sha(F340/'manifest.json')=='91804168356f540401efb25abaa71e38f81f2de5c356b764d8b0b3f851369bed'
 f340=json.loads((F340/'manifest.json').read_text());rootfs=F340/(F340_BASE+'.rootfs.squashfs')
 assert sha(rootfs)==f340['artifacts']['rootfs_squashfs']['sha256']
 assert (F340/(F340_BASE+'.webformat.bin')).read_bytes()[0x180000:]==rootfs.read_bytes()
 raw=KERNEL/'a/f350.raw.bin';source_uimage=KERNEL/'a/f350.uncompressed.uImage'
 assert source_uimage.read_bytes()[64:]==raw.read_bytes()
 dt,address=extract_embedded(KERNEL/'a/f350.vmlinux');assert dt==(KERNEL/'a/f350.dtb').read_bytes()
 assert dt==(F340/(F340_BASE+'.dtb')).read_bytes()
 with (KERNEL/'a/f350.vmlinux').open('rb') as stream:
  elf=ELFFile(stream);sym=elf.get_section_by_name('.symtab');end=int(sym.get_symbol_by_name('_end')[0]['st_value']);entry=int(elf.header['e_entry'])
 assert entry==base.ENTRY and end<base.DDR_END
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f356-observe-ram-'+stamp);out.mkdir(parents=True,exist_ok=False)
 compressor=ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'
 assert sha(compressor)=='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18'
 template=ROOT/'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'
 q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
for lane in a b; do
 mkdir "$out/$lane"
 {q(linux(compressor))} --keep --best {q(linux(raw))} -c > "$out/$lane/f356.lzma"
 python3 {q(linux(ROOT/'tools/make_q1_lzma_uimage.py'))} {q(linux(source_uimage))} "$out/$lane/f356.lzma" "$out/$lane/F356-OBSERVE-RAM-ONLY.uImage" > "$out/uimage-$lane.log"
 python3 {q(linux(ROOT/'tools/pack_topaz_webformat.py'))} "$out/$lane/F356-OBSERVE-RAM-ONLY.uImage" {q(linux(template))} "$out/$lane/F356-OBSERVE-RAM-ONLY.ras.bin" > "$out/ras-$lane.log"
done
cmp "$out/a/f356.lzma" "$out/b/f356.lzma"
cmp "$out/a/F356-OBSERVE-RAM-ONLY.uImage" "$out/b/F356-OBSERVE-RAM-ONLY.uImage"
cmp "$out/a/F356-OBSERVE-RAM-ONLY.ras.bin" "$out/b/F356-OBSERVE-RAM-ONLY.ras.bin"
'''
 (out/'pack.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'pack.sh')],capture_output=True)
 (out/'pack.stdout').write_bytes(run.stdout);(out/'pack.stderr').write_bytes(run.stderr);assert not run.returncode,run.stderr.decode(errors='replace')
 image=out/'a/F356-OBSERVE-RAM-ONLY.ras.bin';encoded=(out/'a/f356.lzma').read_bytes()
 assert lzma.decompress(encoded,format=lzma.FORMAT_ALONE)==raw.read_bytes()
 assert int.from_bytes(encoded[5:13],'little')==raw.stat().st_size
 assert base.STAGING+image.stat().st_size<base.CRC_SCRATCH<base.LOAD
 contract=image_to_dict(validate_bootbase_slot('F356-RAM-format-only',image.read_bytes(),base.CRC_SCRATCH-base.STAGING))
 assert contract['accepted_by_contract'] and int(contract['header']['load'],16)==base.LOAD and int(contract['header']['entry'],16)==entry
 (out/'bootbase-contract.json').write_text(json.dumps(contract,indent=2)+'\n')
 components={}
 for name,src,dst in [('provider',provider['artifact']['path'],'qtn_f356_journal.ko'),('supervisor_ram',supervisor['artifact']['path'],'om-watchdog-supervisor-f356'),('cli',cli['artifact']['path'],'om-journal-cli'),('loader',LOADER,'ram-insmod-qtn')]:
  dst=out/dst;shutil.copyfile(src,dst);components[name]=item(dst)
 components['provider'].update(module_name='qtn_f356_journal',device='/dev/om-f350-journal',parameters='allow_hw=1 allow_program=0',uapi_bytes=4180)
 components['supervisor_ram'].update(kernel_version='#350 @1790006400',kernel_release='5.10.260-openmitrastar-radiohw',ipc_schema='openmitrastar.f340-supervisor-state/v1',automatic_arm=False)
 passive=ROOT/'outputs/handoff-live/f354-passive-20260921T164639Z-3afe11b8/root-acceptance.json';proof=json.loads(passive.read_text())
 assert proof['status']=='PASS_F354_PASSIVE_READ_AND_F340_RETURN' and all(proof['checks'].values()) and proof['observed_spi_control']=='00000004'
 result={'schema':'openmitrastar.f356-observe-ram-bundle/v1','status':'PASS_OFFLINE_RAM_OBSERVE_BUNDLE',
  'hardware_actions':False,'kernel_recompiled':False,'dt_or_config_modified':False,'rootfs_bundled':False,'firmware_flash_image':False,'flash_eligible':False,
  'allowed_operation':'OBSERVE_ONLY','allow_program':False,'save_allowed':False,'physical_id_security_observation':'UNRUN',
  'kernel':dict(item(image),crc32=f'{zlib.crc32(image.read_bytes())&0xffffffff:08x}',kernel_version='#350 @1790006400',format='QTN_RAS_payload_0x2000',ram_only=True),
  **components,'uimage':item(out/'a/F356-OBSERVE-RAM-ONLY.uImage'),
  'exact_kernel_inputs':{'vmlinux':item(KERNEL/'a/f350.vmlinux'),'raw':item(raw),'config':item(KERNEL/'a/f350.config'),'dtb':item(KERNEL/'a/f350.dtb'),'module_symvers':item(KERNEL/'a/Module.symvers')},
  'memory':{'staging':hex(base.STAGING),'crc_scratch':hex(base.CRC_SCRATCH),'load':hex(base.LOAD),'entry':hex(entry),'kernel_end':hex(end),'ddr_end':hex(base.DDR_END),'embedded_dtb_address':hex(address)},
  'rootfs':dict(item(rootfs),physical_address='0x90960000',window='0x460000',access='unchanged persistent F340 read-only rootfs'),'bootargs':BOOTARGS,
  'bootbase_contract':item(out/'bootbase-contract.json'),'reproducible':True,
  'evidence':{'provider':item(args.provider/'result.json'),'provider_tests':item(args.provider_tests/'result.json'),'supervisor':item(args.supervisor/'result.json'),'kernel':item(KERNEL/'result.json'),'passive_control':item(passive)},
  'observed_passive_control':'00000004','supervisor_inspect_required':{'kernel_profile_verified':1,'required_kernel_version':'#350 @1790006400','device_opened':0},
  'diagnostic_uart':'OMF356 observe rc=<int> id=<hex6> control=<hex8> status=<hex2> security=<hex2> valid=<hex2> claimed=<uint> quarantined=<uint>',
  'failure_policy':'Any failed/partial observation: no rmmod; CEASE/reset; exact read-only F340 return. No retry or SAVE.',
  'sources':{str(p):sha(p) for p in [Path(__file__),ROOT/'tools/make_q1_lzma_uimage.py',ROOT/'tools/pack_topaz_webformat.py',ROOT/'tools/bootbase_contract_emulator.py',compressor,template]}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'kernel':result['kernel'],'provider':result['provider'],'supervisor_ram':result['supervisor_ram']},indent=2))
if __name__=='__main__':main()
