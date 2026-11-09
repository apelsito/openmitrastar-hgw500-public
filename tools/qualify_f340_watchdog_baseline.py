"""Qualify F340 local image, identity, sources and unchanged F321 runtime."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,lzma,re
import f340_watchdog_contract as c
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args()
 built=json.loads(a.result.read_text());final=Path(built['output']);manifest=json.loads((final/'manifest.json').read_text());image=Path(built['artifact']['path'])
 base=image.name.removesuffix('.webformat.bin');kernel_result=Path(built['kernel_result']);kernel=json.loads(kernel_result.read_text());k=kernel_result.parent
 supervisor_result=c.ROOT/built['supervisor_result'];supervisor=json.loads(supervisor_result.read_text());inventory=json.loads((final/'rootfs-inventory.json').read_text())
 raw=(final/(base+'.kernel.raw.bin')).read_bytes();dt=c.node_map(final/(base+'.dtb'));config=(final/(base+'.config')).read_text();banner=re.search(rb'Linux version [^\x00\n]+',raw)
 changed=set(inventory['checks']['changed_files']);expected={'etc/openmitrastar/release','usr/sbin/om-watchdog-supervisor','usr/share/openmitrastar/watchdog/profile.json','usr/share/openmitrastar/watchdog/artifacts.sha256'}
 checks={
  'fullimage_build_pass':built['status']=='PASS_OFFLINE_REPRODUCIBLE_FULL_IMAGE_UNARMED',
  'exact_image_and_manifest':sha(image)==built['artifact']['sha256'] and sha(final/'manifest.json')==built['manifest_sha256'],
  'rootfs_bound_at_original_offset':image.read_bytes()[0x180000:]==(final/(base+'.rootfs.squashfs')).read_bytes(),
  'before_store_boundary':image.stat().st_size<0x5e0000,
  'bootbase_and_slot_pass':manifest['contracts']['bootbase']=='PASS' and manifest['contracts']['slot_fit'],
  'f340_banner':bool(banner and b'#340 ' in banner.group() and b'#336 ' not in banner.group()),
  'f340_dt_identity':dt['/'].get('openmitrastar,f340-watchdog-baseline')==c.MARKER and 'openmitrastar,f336-wdt-ram' not in dt['/'],
  'no_old_ram_marker_in_kernel':b'F336_WDT_RAM_ONLY' not in raw,
  'watchdog_no_autoarm_config':all(x in config for x in ['CONFIG_WATCHDOG_NOWAYOUT=y','CONFIG_WATCHDOG_SYSFS=y','# CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED is not set','# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set','# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set','CONFIG_INITRAMFS_SOURCE=""']),
  'f336_config_preserved':(final/(base+'.config')).read_bytes()==(c.F336/'a/f336.config').read_bytes(),
  'rootfs_exact_four_changes':changed==expected,
  'all_original_init_scripts_preserved':all(inventory['after'][p]==v for p,v in inventory['before'].items() if p.startswith('etc/init.d/')),
  'all_radio_modules_preserved':all(inventory['after'][p]==v for p,v in inventory['before'].items() if p.startswith('lib/modules/')),
  'protected_helpers_preserved':all(inventory['before'][p]==inventory['after'][p] for p in ['usr/sbin/om-radio5-start','usr/sbin/om-radioctl','usr/libexec/openmitrastar/om-api-v1','usr/share/openmitrastar/radio5g/driver-contract.env']),
  'known_host_unchanged':(final/'known_hosts.f340').read_bytes()==(c.F321/'known_hosts.f321').read_bytes(),
  'all_flash_windows_rom':all(n.get('compatible')==b'mtd-rom\0' for n in dt.values() if 'linux,mtd-name' in n),
  'rootfs_and_store_windows_unchanged':dt['/soc/flash@90960000']['reg']==c.cells(0x90960000,0x460000) and dt['/soc/flash@90dc0000']['reg']==c.cells(0x90dc0000,0x1c0000),
  'supervisor_native_tests_pass':supervisor['status']=='PASS_OFFLINE_SUPERVISOR' and supervisor['process_tests']['passed'],
  'supervisor_sources_match_tested':all(sha(c.ROOT/p)==h for p,h in supervisor['sources'].items()),
  'supervisor_binary_bound':inventory['after']['usr/sbin/om-watchdog-supervisor']['sha256']==supervisor['artifact']['sha256'],
  'kernel_reproduction':all(sha(k/'a'/name)==sha(k/'b'/name) for name in ['f340.vmlinux','f340.raw.bin','f340.dtb','f340.config','Module.symvers']),
  'kernel_lzma_roundtrip':lzma.decompress((final/(base+'.kernel.lzma')).read_bytes(),format=lzma.FORMAT_ALONE)==raw,
  'no_unrelated_features':not any(manifest['change_scope'][name] for name in ['dfs_f338_included','wps_f335_included','sensor_f339_included']),
  'no_hardware_claim':not built['hardware_actions'] and not built['watchdog_automatic_arm'] and manifest['physical_validation']['status']=='NOT_RUN',
 }
 out=c.ROOT/'outputs/preflight'/('f340-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 sources=[c.ROOT/'tools'/name for name in ['build_f340_watchdog_kernel.py','f340_watchdog_contract.py','build_f340_supervisor.py','test_f340_supervisor.py','f340_watchdog_rootfs_worker.py','build_f340_watchdog_baseline.py','qualify_f340_watchdog_baseline.py','f336_wdt_ram_contract.py']]
 result={'schema':'openmitrastar.f340-qualified/v1','status':'PASS_OFFLINE_FULLIMAGE_AND_SUPERVISOR' if all(checks.values()) else 'FAIL',
  'checks':checks,'image':built['artifact'],'manifest_sha256':sha(final/'manifest.json'),'kernel_banner':banner.group().decode() if banner else None,
  'kernel_source':kernel['isolated_build']+'/linux','kernel_build_directory':(k/'a/build-directory.txt').read_text().strip(),
  'kernel_config':str(k/'a/f340.config'),'kernel_module_symvers':str(k/'a/Module.symvers'),'kernel_module_symvers_sha256':sha(k/'a/Module.symvers'),
  'supervisor':supervisor['artifact'],'source_hashes':{str(p.relative_to(c.ROOT)):sha(p) for p in sources},
  'source_metadata_note':'The preserved kernel-stage report describes F336 reference-node names; the actual parsed DT here proves the F340 identity/clock node.',
  'hardware_actions':False,'physical_gate':'F336 hardware qualification and a separate current-device executor required; no Wi-Fi/client acceptance claimed'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'passed':sum(checks.values()),'total':len(checks),'result':str(out/'result.json'),'failed':[n for n,v in checks.items() if not v]},indent=2));return 0 if all(checks.values()) else 1
if __name__=='__main__':raise SystemExit(main())
