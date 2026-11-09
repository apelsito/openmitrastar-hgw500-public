"""Create an owner-requested local technical handoff, excluding device secrets.

The exported rootfs is a sanitized file reference, never a flash/boot artifact.
Original firmware, protected partitions and source files are never modified.
"""
from datetime import datetime, timezone
import argparse,csv,hashlib,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f367r9-f365-transition-observation-device-bound'
LINEAGE=ROOT/'outputs/handoff/source-lineage-20261022T124550Z/SOURCE_LINEAGE.json'
ROOTFS_SHA='465c413d5f08c8a422e09dc1a942e4a7b89042fb684c80281ca776c4b419852e'
PRIVATE_PREFIXES=('root/','etc/power_tables/','usr/share/openmitrastar/device-identity/',
 'usr/share/openmitrastar/factory-config/','usr/share/openmitrastar/config-schema/v1/defaults',
 'usr/share/openmitrastar/origin-mtd5/','usr/share/openmitrastar/qtn/',
 'usr/share/openmitrastar/keys/factory-authorized_keys')
PRIVATE_EXACT={'etc/shadow','etc/passwd','etc/hostname','etc/qtn_regulatory_db.bin',
 'usr/share/openmitrastar/bootenv-wifiaddr-producer.json'}
TEXT_EXT={'.py','.ps1','.sh','.c','.h','.dts','.md','.json','.env','.conf','.txt','.csv','.patch','.cmd','.symvers'}
MAC=re.compile(rb'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')
SECRET_LINE=re.compile(rb'(?im)^\s*(?:wpa_passphrase|wpa_psk|psk|password|wifi_password|ssid|ssid2g|ssid5g)\s*=\s*[^$\n\r]+')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):
 p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def secret_path(name):return name in PRIVATE_EXACT or name.startswith(PRIVATE_PREFIXES)

def export_rootfs(a):
 import sys
 sys.path.insert(0,str(ROOT/'tools'))
 from lyoko_web_rootfs_worker import inventory
 assert os.name=='posix' and sha(a.rootfs)==ROOTFS_SHA
 reference=json.loads(a.inventory.read_text())['after']
 with tempfile.TemporaryDirectory(prefix='hgw-handoff-rootfs-') as td:
  root=Path(td)/'root'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.rootfs)],check=True,stdout=subprocess.DEVNULL)
  actual=inventory(root);assert actual==reference,'rootfs inventory mismatch'
  omitted=[];exported=[]
  for name,row in sorted(actual.items()):
   if row['type']!='file':continue
   src=root/name
   if secret_path(name):omitted.append({'path':name,'reason':'device identity, credentials, configuration or calibration excluded'});continue
   data=src.read_bytes()
   if not data.startswith(b'\x7fELF') and (MAC.search(data) or SECRET_LINE.search(data)):
    omitted.append({'path':name,'reason':'literal device/network settings excluded'});continue
   dest=a.destination/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(row['mode'])
   exported.append({'path':name,'bytes':len(data),'sha256':sha(dest),'mode':row['mode']})
  links=[{'path':n,'target':r['target'],'mode':r['mode']} for n,r in actual.items() if r['type']=='symlink']
  (a.destination/'SYMLINKS.json').write_text(json.dumps(links,indent=2)+'\n')
  # Store links as metadata; no extraction-time link traversal or hidden files.
  a.report.write_text(json.dumps({'status':'PASS_SANITIZED_FILE_REFERENCE_NOT_BOOTABLE',
    'original_rootfs_sha256':ROOTFS_SHA,'original_entries_verified':len(actual),
    'exported_files':exported,'symlinks_as_metadata':links,'excluded':omitted,
    'not_flashable':True,'credentials_present':False},indent=2)+'\n')

def main(a):
 now=datetime.now(timezone.utc);out=ROOT/'outputs/handoffs'/('hgw500-linux510-complete-'+now.strftime('%Y%m%dT%H%M%S%fZ'))
 out.mkdir(parents=True,exist_ok=False);stage=out/'package';stage.mkdir()
 mapping={};exclusions=[]
 def add(src,dst=None,role='reference'):
  src=Path(src)
  if not src.is_file() or src.is_symlink():raise ValueError('missing/nonregular '+str(src))
  if dst is None:dst=src.resolve().relative_to(ROOT.resolve()).as_posix()
  assert not dst.startswith('/') and '..' not in Path(dst).parts
  target=stage/dst;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():assert sha(target)==sha(src);return
  shutil.copyfile(src,target);mapping[dst]={'source':str(src),'sha256':sha(src),'bytes':src.stat().st_size,'role':role}
 def tree(src,dst=None,predicate=None):
  src=Path(src)
  for p in sorted(src.rglob('*')):
   if p.is_symlink():continue
   if p.is_file() and (predicate is None or predicate(p)):
    add(p,(Path(dst)/p.relative_to(src)).as_posix() if dst else None)
 add(LINEAGE,'SOURCE_LINEAGE.json')
 lineage=json.loads(LINEAGE.read_text())
 for t in lineage['trees']:
  for r in t['entries']:
   p=ROOT/r['path'];assert sha(p)==r['sha256'];add(p,role=t['role'])
 for r in lineage['kernel_generated_context']:
  p=Path(r['source_path']);assert sha(p)==r['sha256'];add(p,'build-context/f363/kernel/'+r['relative_context_path'],role='generated kernel context')
 for r in lineage['files']:
  if r['path'].startswith('\\'):
   p=Path(r['path']);dst='dependencies/linux-5.10.260.tar.xz'
  else:p=ROOT/r['path'];dst=r['path']
  assert sha(p)==r['sha256'];add(p,dst,role=r.get('role','dependency'))
 # Retain exact objects/metadata needed to audit compiled QDRV, without making
 # historic absolute-path commands into a runnable flash launcher.
 for p in (ROOT/'work/linux510-radio-port/quantenna/qdrv').glob('.*.o.cmd'):add(p)
 for directory in ['work/kernel-port/f367r9-transition-observation','work/kernel-port/versions/f364-lifetime-integration']:
  tree(ROOT/directory,predicate=lambda p:p.suffix in TEXT_EXT or p.name=='Makefile')
 build=ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2'
 tree(build,predicate=lambda p:p.suffix in ('.json','.py','.symvers','.asm') or p.name in ('qdrv.ko','qdrv.mod.c'))
 for directory in ['outputs/rea/arc700-20261021-r2/f368r2-module','outputs/rea/arc700-20261021-r2/f368r2-fault-path-r3',
  'outputs/rea/arc700-20261021-r2/f368r2-fault-path-r2','outputs/rea/arc700-20261021-r2/tqe-current',
  'outputs/rea/arc700-20261021-r2/tqe-rea-tx','outputs/rea/arc700-20261021-r2/f365-rea-auc-tx',
  'outputs/rea/arc700-20261021-r2/tqe-bounded-admission-20261022-r2','outputs/rea/arc700-20261021-r2/tqe-bounded-admission-tests-20261022-r5']:
  tree(ROOT/directory,predicate=lambda p:p.suffix in TEXT_EXT or p.name=='qdrv.ko' or p.name=='switch_tqe.ko')
 # Tool closure is selected by ownership and local imports/referenced filenames.
 names=set()
 seeds=('f36','f37','doom','tqe_bounded','hgw_boot','hgw_led','hgw_storage','router_component','installed_versions',
  'audit_f337','bootbase_contract','compose_f164','f334_shadow','f346_install','f319_uart','f319_recovery','f321_ssh','f325_')
 for p in (ROOT/'tools').iterdir():
  if p.is_file() and p.suffix in TEXT_EXT and any(s in p.name for s in seeds):names.add(p.name)
 names|={'ssh_openmitrastar_510.ps1','ramssh_exec.py','lyoko_web_rootfs_worker.py','build_f71_qcsapi_interp_from_f70.py','init_lyoko_device_host_key.py','lyoko_frontend_identity.py'}
 changed=True
 while changed:
  changed=False
  for n in list(names):
   p=ROOT/'tools'/n
   if not p.exists():continue
   text=p.read_text(encoding='utf-8',errors='replace')
   imports=re.findall(r'(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)',text)
   refs=re.findall(r'([A-Za-z0-9_-]+\.(?:py|ps1|sh))',text)
   for candidate in [x+'.py' for x in imports]+refs:
    if (ROOT/'tools'/candidate).is_file() and candidate not in names:names.add(candidate);changed=True
 for n in sorted(names):
  if (ROOT/'tools'/n).exists():add(ROOT/'tools'/n)
 add(Path(__file__))
 for p in (ROOT/'docs').glob('*.md'):
  if any(s in p.name for s in ('F36','F37','F337','REA_RADIO','LED','STORAGE','TQE','INSTALLED','AGENT_CURRENT','AGENT_REFERENCE','HGW500_OPS','LYOKO_CHANNEL')):add(p)
 add(ROOT/'AGENTS.md')
 for d in ['outputs/inventory/installed-final-20261022T093747859049Z','outputs/inventory/router-components-20261022T092048336196Z',
  'outputs/inventory/tls-size-20261022T092507734208Z','outputs/doom/music-http-20261022-r1',
  'outputs/client-readonly/aelita-reachability-20261022T091851674868Z','outputs/storage/requested-memory-20261022T123457230588Z',
  'outputs/storage/slab-sysfs-20261022T123526225719Z','outputs/storage/hgw-readonly-20261022T124211552741Z',
  'outputs/rea/arc700-20261021-r2/led-boot-readonly-20261022T124210317515Z']:
  tree(ROOT/d,predicate=lambda p:p.suffix in TEXT_EXT or p.suffix=='.png')
 # No monolithic personalized images, raw partitions, calibration or keys.
 rootfs=next(SOURCE.glob('*.rootfs.squashfs'));assert sha(rootfs)==ROOTFS_SHA
 runtime=stage/'installed-rootfs-reference';report=stage/'ROOTFS_EXPORT.json'
 cmd=['wsl.exe','-d','REA-Linux','-u','root','-e','python3',linux(Path(__file__)),
  '--export-rootfs','--rootfs',linux(rootfs),'--inventory',linux(SOURCE/'rootfs-inventory.json'),
  '--destination',linux(runtime),'--report',linux(report)]
 proc=subprocess.run(cmd,capture_output=True,timeout=90)
 (out/'rootfs-export.stdout').write_bytes(proc.stdout);(out/'rootfs-export.stderr').write_bytes(proc.stderr)
 assert proc.returncode==0,proc.stderr.decode(errors='replace')
 exclusions+=json.loads(report.read_text())['excluded']
 for suffix in ['.config','.kernel.lzma','.kernel.raw.bin','.vmlinux']:
  p=next(SOURCE.glob('*'+suffix));add(p,'installed-kernel/'+p.name)
 # RAM radio package excludes personalized donor rootfs, archive and original plan.
 ram=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3'
 for n in ['qdrv.ko','wlan.ko']:add(ram/'payload/modules'/n,'active-radio5g/'+n,role='active F365 RAM binary')
 for n in ['guard','head','tail','om-radio5-start','om-radio5-stop']:add(ram/'payload/bin'/n,'active-radio5g/bin/'+n)
 for n in ['artifacts.sha256','driver-contract.env']:add(ram/'payload/share'/n,'active-radio5g/share/'+n)
 add(ram/'manifest.json','active-radio5g/manifest.json')
 game=ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom'
 music=ROOT/'outputs/doom/music-opl-qualified-20261022-r3-sourcepatch'
 for p in game.iterdir():
  chosen=music/p.name if p.name in ('index.html','chocolate-doom.wasm') else p
  add(chosen,'runtime-overlays/www/Doom/'+p.name)
 add(music/'source-equivalent.patch','runtime-overlays/www/Doom/source-equivalent.patch')
 tree(music,'music-source-and-qualification',predicate=lambda p:p.suffix in TEXT_EXT or p.name=='original-delay.wat')
 led=ROOT/'outputs/rea/arc700-20261021-r2/led-cli-candidate-r2-20261021T215300Z/om-ledctl'
 add(led,'runtime-overlays/usr/sbin/om-ledctl')
 add(ROOT/'outputs/rea/arc700-20261021-r2/boot-timing-candidate-20261021T215129281623Z/rcS','offline-boot-timing/rcS')
 exclusions.extend([{'path':str(DEVICE),'reason':'personalized firmware/rootfs images, keys, raw protected partitions and store are not exported'},
  {'path':'historical F358 patched kernel source','reason':'missing in current WSL distributions; exact full 2.4 GHz/kernel rebuild unproven'}])
 (stage/'EXCLUSIONS.json').write_text(json.dumps(exclusions,indent=2)+'\n')
 (stage/'ORIGINAL_SOURCE_MAP.json').write_text(json.dumps(mapping,indent=2)+'\n')
 (stage/'README_HANDOFF.md').write_text(README,encoding='utf-8')
 (stage/'verify_handoff.py').write_text(VERIFY,encoding='utf-8')
 # Confirm excluded device values do not occur in readable export files. Match
 # known actual private-key bytes across all files, not vague word heuristics.
 forbidden=[]
 pem=re.compile(rb'(?m)^-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{20,}')
 for p in stage.rglob('*'):
  if p.is_file() and p.suffix not in ('.xz','.gz','.zip','.wasm','.ko','.lzma','.bin','.vmlinux'):
   b=p.read_bytes()
   if pem.search(b):forbidden.append(p.relative_to(stage).as_posix())
 assert not forbidden,forbidden
 files={p.relative_to(stage).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(stage.rglob('*')) if p.is_file()}
 (stage/'MANIFEST.json').write_text(json.dumps({'schema':'openmitrastar.technical-handoff/v1','created_utc':now.isoformat(),
   'classification':'LOCAL_HANDOFF_SANITIZED_NOT_FLASH_IMAGE','files':files,'hardware_actions':False,'sent_to_anyone':False,
   'scope':'Both radio binary/source lineages, sanitized installed files, current RAM overlays, build tools/context, inventories and retained evidence',
   'limits':['Not bootable or flashable','Original device identity/calibration excluded','Original full patched 2.4 GHz kernel source missing','Offline candidates are not installed','Portable relocation needs review']},indent=2)+'\n')
 (stage/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+k+'\n' for k,v in files.items()),encoding='ascii')
 archive=out/'OpenMitraStar-HGW500-Linux510-Handoff.zip'
 with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p in sorted(stage.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(stage).as_posix())
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name,spec in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==spec['sha256']
  assert 'MANIFEST.json' in z.namelist()
 for name,spec in mapping.items():assert sha(spec['source'])==spec['sha256'],'input changed '+name
 result={'status':'PASS_LOCAL_SANITIZED_HANDOFF_ZIP','zip':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive),
   'verified_manifest_files':len(files),'source_inputs_unchanged':True,'zip_crc_verified':True,'sha256_payload_verified':True,
   'hardware_actions':False,'sent_to_anyone':False,'full_kernel_source_rebuild_ready':False,'excluded_files':len(exclusions)}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

README='''# OpenMitraStar HGW-500BNA-QCv2 A2 — engineering handoff

This ZIP contains the two radio ports, available source and build context,
installed software, current RAM overlays, test evidence and recovery limits.
It is a technical handoff, not a flashable image or a completed release.

## Start here

Read docs/OPENMITRASTAR_INSTALLED_VERSIONS_STORAGE_20261022.md and
SOURCE_LINEAGE.json. Run `python verify_handoff.py` after extracting the ZIP.
The manifest identifies every file by SHA-256; originals were not modified.
Use the versions table and CSV for source dates, installation evidence and size.

## Current physical state — 22 October 2026

Persistent firmware: F367r9, Linux 5.10.260-openmitrastar-radiohw, build #358.
Management IP: 192.168.1.90; PC source: 192.168.1.49. Windows Ethernet interface
is now 16 and the original FTDI UART is COM4. Historical interface18/COM3 plans
must not be executed unchanged. The latest read-only captures are included.
Boot ID: 5f513265-a294-4366-9567-e1d8af704b6b. Both AP controls respond,
watchdog control is 00000000 and the bounded fatal check is zero.
Real-client visibility, association and useful traffic are not accepted.

The active 2.4 GHz modules are the files in installed-rootfs-reference under
lib/modules/.../radio2g. The 5 GHz AP runs the exact F365 qdrv/wlan pair in
active-radio5g from RAM, with installed platform dependencies. Stored F367r9
QDRV, active F365 QDRV and the offline F370 candidate are different artifacts.
Reboot loses the F365 RAM activation. QDRV retains its lifetime pin after
mutation and is not safe to unload; no hot-reload instruction is supplied.

Doom episode 1, English controls and original OPL music run at /Doom. The
corrected LED CLI and Doom are RAM overlays. runtime-overlays contains current
files; installed-rootfs-reference contains original F367r9 files with sensitive
material excluded. The OPL source patch, source archive and licences are included.

## Contents

- installed-rootfs-reference: nonsecret files from the exact installed rootfs.
  SYMLINKS.json preserves link metadata without extraction-time link traversal.
  ROOTFS_EXPORT.json identifies exclusions. This tree cannot boot as supplied.
- installed-kernel: exact kernel/config/vmlinux artifacts, without a full
  personalized firmware image.
- active-radio5g: the exact active F365 module pair and its startup helpers.
- work: radio source lineages, compatibility layers, patches and candidate trees.
- dependencies/linux-5.10.260.tar.xz and work/toolchains/...tar.xz: pinned upstream
  Linux and the ARC 2026.03 compiler. The upstream archive is not the missing
  complete patched F358 kernel source.
- build-context/f363/kernel: generated headers, config, symbol versions and
  retained host tools. Original .o.cmd files preserve actual compilation flags.
- tools: selected builders, verifiers and tests plus discovered local imports.
- outputs: module artifacts, REA analyses, fixture results and runtime evidence.
- docs: component contracts, storage layout, installed versions and limitations.
- MANIFEST.json, SHA256SUMS and verify_handoff.py: payload integrity checks.

## Implemented work and acceptance boundaries

F368 is NO_GO: a reproduced late STORE38 ACK falsely completed a later command.
F368r2 fixes descriptor quarantine; its module and fault fixtures pass offline,
but it has not been installed. F370 adds observation counters and has a complete
baseline reconstruction and repeated builds; it has not been loaded.
F371/F372 full images are prepared offline, not installed.
F373 combines Doom, LEDs and boot timing but its 7,782,400-byte rootfs exceeds
the 4,587,520-byte window by 3,194,880 bytes; no flash image was created.
The wolfSSL TLS trial saves 352 KiB in a measured F372 repack, without physical
HTTPS qualification or installation.
The TQE bounded-admission prototype passes 38 cases and 245 assertions, but
universal writer arbitration and full-module equivalence are unproven. It is
NO_GO_MODULE and must not be packaged as a qualified replacement driver.
Slab usage around 21 MiB, including 20 MiB unreclaimable, was observed. The
missing /proc/slabinfo and zero sysfs object counters do not establish a leak.

## Building and testing

The builders retain original absolute Windows/WSL paths and source pins.
Relocate them deliberately in a clean Linux workspace, with new recorded pins;
do not blindly rewrite paths and claim reproducibility. GCC host fixtures,
Python3, pyelftools, SquashFS tools and the supplied ARC toolchain are separate
prerequisites. REA ARC700 used an isolated project adaptation and Ghidra; the
installed REA release did not natively support these ARC artifacts. Derived
linked ELFs use synthetic externals and must never be loaded on hardware.

The patched F358 kernel source referenced by 2.4 GHz compilation commands is
absent from both currently registered WSL distributions. Exact module binaries,
current Realtek overlays, upstream Linux and retained flags are provided as
reconstruction inputs. A complete identical 2.4 GHz/kernel source rebuild has
not been demonstrated. SOURCE_LINEAGE.json records the exact distinction.
Use the F370 module document and TQE prototype document for reproducible local
fixtures. Every run needs a new output directory. Inspect each CLI before use;
possessing this ZIP does not authorize hardware operations or flash wrappers.

## Hardware and recovery

The physical NOR is 16 MiB. linux_live starts at 0x7e0000 and is 0x7a0000 bytes.
Normal iteration may write only its 0x5e0000-byte prefix, preserving the store
at 0xdc0000 + 0x1c0000. OEM physical mtd0/1/2/3/5 remain protected.
Current Linux mtd3 is rootfs_live and mtd4 is lyoko_store; these ROM views are
not the same numbered physical partitions. Never append logical mtd6 to SPI.
Do not change boot environment while SSH is healthy.

AGENTS historically calls ATGO a proven rollback. Primary evidence contradicts
independent management recovery: preserved OEM mtd3 boot failed rootfs selection.
F337 direct read-only OEM root mapping is an offline proposal, without a
physical executor or acceptance. Fresh recovery, current readbacks, exact-image
owner authority and reviewed lease/UART/transport binding are required before
any firmware write. Never silently promote kernel Bootbase PASS to recovery PASS.

Private keys, credentials, factory network settings, calibration, raw MTD/store
and full personalized firmware images are excluded. They remain on the owner's
machine; a separate explicit private-transfer authorization would be required.
Without the unit's calibration, do not activate RF on another router.
No message or file was sent to another person; this package remains local.

## Next steps for the receiving engineer

1. Validate this package and read branch roles and current physical evidence.
2. Recover a pinned Wi-Fi client and prove SSID visibility, AUTH/ASSOC/AUTHORIZED
   and useful bidirectional traffic without disrupting Ethernet management.
3. Reconstruct the missing 2.4 GHz baseline and qualify the complete source build.
4. Close TQE/HBM ownership and arbitration before deployment of a new driver.
5. Resolve storage fit and real recoverability, then qualify an immutable image.
6. Verify persistent cold boots, protected/calibration/regulatory preservation,
   stable management, fatal-free soak and rollback; issue final release evidence.
'''
VERIFY='''import hashlib,json,sys\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nm=json.loads((r/'MANIFEST.json').read_text(encoding='utf-8'))\nerrors=[]\nfor name,row in m['files'].items():\n p=r/name\n if not p.is_file() or p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:errors.append(name)\nprint('PASS' if not errors else 'FAIL',len(m['files']),'payload files')\nif errors:print(*errors,sep='\\n')\nsys.exit(bool(errors))\n'''

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--export-rootfs',action='store_true')
 for n in ('rootfs','inventory','destination','report'):p.add_argument('--'+n,type=Path)
 a=p.parse_args()
 if a.export_rootfs:export_rootfs(a)
 else:main(a)
